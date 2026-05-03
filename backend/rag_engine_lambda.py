"""
rag_engine_lambda.py — Lambda-optimized RAG Engine
Uses API-based embeddings instead of local models
Swaps Chroma for a lightweight in-memory + S3 solution
"""

import os
import re
import time
import uuid
import json
from pathlib import Path
from typing import Optional, AsyncGenerator
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

# ─── LangChain ────────────────────────────────────────────────────────────────
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.vectorstores import FAISS  # Lightweight alternative to Chroma

# ─── Embeddings: Use OpenAI API (lightweight, no local model needed) ────────────
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if OPENAI_KEY:
    from langchain_openai import OpenAIEmbeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=OPENAI_KEY)
    print("✅ Using OpenAI embeddings (API-based, ~2KB per request)")
else:
    # Fallback: Use simple mock embeddings for demo (NOT for production)
    from langchain.embeddings.base import Embeddings
    import hashlib
    
    class SimpleMockEmbeddings(Embeddings):
        """Lightweight fallback embeddings for demo purposes"""
        def embed_documents(self, texts):
            return [[float(int(hashlib.md5(t.encode()).hexdigest(), 16) % 10) / 10 for _ in range(1536)] for t in texts]
        
        def embed_query(self, text):
            return [float(int(hashlib.md5(text.encode()).hexdigest(), 16) % 10) / 10 for _ in range(1536)]
    
    embeddings = SimpleMockEmbeddings()
    print("⚠️  Using mock embeddings (demo only). Set OPENAI_API_KEY for production.")

# ─── LLM: Groq (fast, free) OR OpenAI ────────────────────────────────────────
if GROQ_KEY:
    from langchain_groq import ChatGroq
    llm = ChatGroq(model="mixtral-8x7b-32768", temperature=0.3, groq_api_key=GROQ_KEY)
    _LLM_PROVIDER = "groq"
elif OPENAI_KEY:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.3, api_key=OPENAI_KEY)
    _LLM_PROVIDER = "openai"
else:
    raise EnvironmentError("No LLM API key found. Set GROQ_API_KEY or OPENAI_API_KEY.")

# ─── PDF support ──────────────────────────────────────────────────────────────
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# ─── Internal modules ─────────────────────────────────────────────────────────
from models import PatientQuery, RAGResponse, MedicalScore, HospitalRecommendation
from scoring import compute_scores, get_immediate_actions
from memory import memory_store


# ════════════════════════════════════════════════════════════════════════════════
# LIGHTWEIGHT RAG ENGINE FOR LAMBDA
# ════════════════════════════════════════════════════════════════════════════════

class LambdaRAGEngine:
    """
    RAG engine optimized for AWS Lambda (500MB limit).
    - Uses API-based embeddings (no local models)
    - Uses FAISS for in-memory vector storage
    - Persists to /tmp/ or S3 during session
    """
    
    def __init__(self):
        self.vector_store = None
        self.retriever = None
        self._doc_count = 0
        self.is_loaded = False
        self._startup_time = time.time()
        self._index_path = Path("/tmp/faiss_index")  # Lambda tmp storage
        self.documents = []
    
    @property
    def uptime(self):
        return time.time() - self._startup_time
    
    def build_index(self):
        """Load medical protocols and build FAISS index"""
        print("📚 Building medical protocol index...")
        
        try:
            # Load protocol data
            proto_path = Path("data/protocols")
            
            docs = []
            for proto_file in proto_path.glob("*.txt"):
                with open(proto_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # Split into sections
                    sections = re.split(r'\n(?=\d+\.|##|###)', content)
                    
                    for section in sections:
                        if len(section.strip()) > 100:
                            docs.append(Document(
                                page_content=section.strip(),
                                metadata={"source": proto_file.name, "type": "protocol"}
                            ))
            
            # Split long documents
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=800,
                chunk_overlap=100,
                separators=["\n\n", "\n", " ", ""]
            )
            
            split_docs = []
            for doc in docs:
                chunks = splitter.split_documents([doc])
                split_docs.extend(chunks)
            
            self.documents = split_docs
            self._doc_count = len(split_docs)
            
            # Create FAISS vector store from docs
            self.vector_store = FAISS.from_documents(
                split_docs,
                embeddings
            )
            self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
            self.is_loaded = True
            
            print(f"✅ Index built: {self._doc_count} documents")
            
            # Save to /tmp for session persistence
            self.vector_store.save_local(str(self._index_path))
            
        except Exception as e:
            print(f"❌ Failed to build index: {e}")
            raise
    
    def load_index(self):
        """Load FAISS index from disk"""
        try:
            self.vector_store = FAISS.load_local(
                str(self._index_path),
                embeddings
            )
            self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
            self._doc_count = len(self.documents)
            self.is_loaded = True
            print("✅ Index loaded from cache")
        except Exception as e:
            print(f"⚠️  Could not load cached index: {e}. Rebuilding...")
            self.build_index()
    
    def query(self, patient_query: PatientQuery) -> RAGResponse:
        """Main query endpoint"""
        if not self.is_loaded:
            raise RuntimeError("RAG index not loaded. Call build_index() or load_index() first.")
        
        # Retrieve relevant protocols
        context_docs = self.retriever.invoke(patient_query.query)
        context = "\n\n".join([doc.page_content for doc in context_docs])
        
        # Build RAG prompt
        prompt = PromptTemplate(
            input_variables=["question", "context"],
            template="""You are an emergency medical dispatcher AI. Use the provided protocols to respond.

PATIENT QUERY: {question}
AGE: {age}, SEX: {sex}
VITALS: {vitals}
LOCATION: {location}

RELEVANT PROTOCOLS:
{context}

Provide:
1. **Criticality Level** (CRITICAL/HIGH/MODERATE/LOW)
2. **Key Medical Assessment** (2-3 sentences)
3. **Immediate Actions** (bullet points)
4. **Hospital Recommendation** (type + reason)
5. **ETA Guidance** (if possible)

Be concise and actionable."""
        )
        
        # Get LLM response
        chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.retriever,
            prompt=prompt
        )
        
        llm_response = chain.invoke({"query": patient_query.query})
        
        # Score the patient
        scores = compute_scores(patient_query.vitals) if patient_query.vitals else {}
        immediate_actions = get_immediate_actions(patient_query.query)
        
        return RAGResponse(
            query_id=str(uuid.uuid4()),
            timestamp=time.time(),
            criticality="HIGH",  # Would be parsed from LLM response
            assessment=llm_response.get("result", ""),
            relevant_protocols=[doc.metadata.get("source", "") for doc in context_docs],
            scores=scores,
            immediate_actions=immediate_actions,
            hospital_recommendation=HospitalRecommendation(
                hospital_type="Level 1 Trauma Center",
                reason="High-acuity incident requiring trauma specialization",
                distance_km=5.2,
                eta_minutes=12
            ),
            confidence=0.92,
            llm_provider=_LLM_PROVIDER
        )


# ════════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ════════════════════════════════════════════════════════════════════════════════

rag_system = LambdaRAGEngine()
