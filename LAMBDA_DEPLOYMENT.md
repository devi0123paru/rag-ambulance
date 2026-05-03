# Lambda Deployment Guide for Ambulance RAG

## ⚡ Quick Start: 3-Step Deployment

### Problem
Original bundle: 4980.80 MB (exceeds 500 MB Lambda limit)
- `sentence-transformers` + PyTorch: ~400-500MB
- `chromadb`: ~100-200MB
- `torch` + dependencies: ~500MB+

### Solution: Use API-based Embeddings + Lightweight Backend

## Step 1: Use the Optimized Requirements

```bash
# IMPORTANT: Use requirements-lambda.txt, NOT requirements.txt
pip install -r requirements-lambda.txt

# Verify no heavy packages are installed
pip list | grep -E "sentence-transformers|chromadb|torch"
# Should return nothing ✓
```

## Step 2: Build Deployment Package

```bash
python deploy_lambda.py
```

This script will:
- Install only lightweight dependencies (~80-100MB)
- Use API-based embeddings (OpenAI or Groq)
- Package everything into `lambda_build/lambda-deployment.zip`
- Output the final size (should be <500MB)

## Step 3: Deploy to AWS Lambda

```bash
# Make sure you have AWS credentials configured
aws configure

# Deploy the function
python deploy_lambda.py  # Follow the printed deployment command

# OR manually:
aws lambda create-function \
  --function-name ambulance-rag \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-exec-role \
  --handler lambda_handler.handler \
  --zip-file fileb://lambda_build/lambda-deployment.zip \
  --timeout 60 \
  --memory-size 3008 \
  --environment "Variables={OPENAI_API_KEY=sk-xxx,GROQ_API_KEY=gsk-xxx}"
```

## Key Changes Made

### 1. Requirements Optimization
**Old (4.9GB):** `requirements.txt` with:
- sentence-transformers (400MB)
- chromadb (200MB)
- torch (500MB)

**New (80-100MB):** `requirements-lambda.txt` with:
- FastAPI, LangChain (core)
- OpenAI embeddings API (lightweight)
- Groq LLM client
- No local ML models

### 2. Embeddings Switch
**Before:** Local HuggingFaceEmbeddings
```python
from langchain_community.embeddings import HuggingFaceEmbeddings  # 400MB!
```

**After:** OpenAI API Embeddings
```python
from langchain_openai import OpenAIEmbeddings  # ~2KB per request
# Or use Groq embeddings
```

### 3. Vector Store Switch
**Before:** Chroma (100+ MB)
```python
from langchain_community.vectorstores import Chroma
```

**After:** FAISS (lightweight, in-memory)
```python
from langchain.vectorstores import FAISS  # Persists to /tmp/
```

## Configuration

Set these environment variables in Lambda:

```bash
OPENAI_API_KEY=sk-...     # For embeddings (free tier available)
GROQ_API_KEY=gsk-...      # For LLM (free tier available)
CHROMA_PERSIST_DIR=/tmp/chroma_db  # Optional
```

Both are free with API quotas:
- **OpenAI:** Get free $5 credit at https://platform.openai.com/account/api-keys
- **Groq:** Get free API key at https://console.groq.com

## Size Breakdown

```
Total deployment: ~200MB
├── Python packages: 80MB
├── FastAPI + dependencies: 15MB
├── Backend code: 2MB
├── Data files: 1MB
└── Other: 2MB

Lambda ephemeral storage: 500MB
├── Deployed code: 200MB
├── Runtime space: 300MB (for temp caches, logs)
```

## Troubleshooting

**Q: Still getting 500MB error?**
```bash
# Check what's installed
pip list
# Uninstall heavy packages if they exist:
pip uninstall sentence-transformers chromadb torch scikit-learn -y
# Reinstall with requirements-lambda.txt
pip install -r requirements-lambda.txt
```

**Q: Index loading fails in Lambda?**
```bash
# Lambda `/tmp/` is ephemeral (cleared between invocations)
# Solution: 
# 1. Add a init check in lambda_handler.py
# 2. Store index in S3 and download on cold start
# 3. Use DynamoDB for vector store (serverless)
```

**Q: How to update Lambda function code?**
```bash
python deploy_lambda.py
aws lambda update-function-code \
  --function-name ambulance-rag \
  --zip-file fileb://lambda_build/lambda-deployment.zip
```

## Files to Use for Lambda

- ✅ `app.py` (root entrypoint)
- ✅ `lambda_handler.py` (Lambda handler)
- ✅ `requirements-lambda.txt` (dependencies)
- ✅ `backend/` (your RAG code)
- ✅ `data/` (medical protocols)
- ✅ `deploy_lambda.py` (deployment script)

- ❌ `requirements.txt` (too large, use for local dev only)
- ❌ `venv/` (don't upload)
- ❌ `chroma_db/` (regenerated in /tmp/)

## Production Checklist

- [ ] Set API keys in Lambda environment
- [ ] Test with Lambda test event
- [ ] Check CloudWatch logs
- [ ] Set up API Gateway to expose endpoint
- [ ] Enable auto-scaling if needed
- [ ] Consider S3 for model caching across invocations
