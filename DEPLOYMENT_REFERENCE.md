# Deployment Quick Reference

## LOCAL DEVELOPMENT (Your Computer)
```bash
# Full requirements with all dependencies
pip install -r requirements.txt

# Run locally
python -m uvicorn app:app --reload

# Files used:
# - requirements.txt (includes sentence-transformers, chromadb)
# - backend/rag_engine.py (original)
# - Data: data/chroma_db/

# Bundle size: ~5GB (fine for local)
```

## AWS LAMBDA DEPLOYMENT (Serverless)
```bash
# IMPORTANT: Use requirements-lambda.txt instead!
pip install -r requirements-lambda.txt

# Deploy
python deploy_lambda.py

# Files used:
# - requirements-lambda.txt (lightweight, NO sentence-transformers/chromadb)
# - backend/rag_engine_lambda.py (API-based embeddings)
# - lambda_handler.py (ASGI adapter)

# Bundle size: ~200MB (fits in 500MB limit)
```

## KEY DIFFERENCES

| Aspect | Local | Lambda |
|--------|-------|--------|
| **Embeddings** | HuggingFaceEmbeddings (local) | OpenAI/Groq API |
| **Vector Store** | Chroma (disk-based) | FAISS (in-memory, /tmp/) |
| **Storage** | `chroma_db/` folder | `/tmp/` ephemeral |
| **Dependencies** | ~5GB (all) | ~200MB (lightweight) |
| **API Keys** | Optional | **Required** (OPENAI_API_KEY, GROQ_API_KEY) |
| **Cost** | Free | Pay per request (~$0.10-1/1000 requests) |
| **Setup Time** | ~2 mins | ~5 mins (first cold start slower) |

## STEP-BY-STEP TO FIX YOUR ERROR

1. **Uninstall heavy packages** (if installed)
   ```bash
   pip uninstall sentence-transformers chromadb torch scikit-learn -y
   ```

2. **Install lightweight requirements**
   ```bash
   pip install -r requirements-lambda.txt
   ```

3. **Update your main.py** to use lambda-optimized engine
   ```python
   # OLD (won't work on Lambda):
   from rag_engine import rag_system
   
   # NEW:
   from rag_engine_lambda import rag_system
   ```

4. **Build and deploy**
   ```bash
   python deploy_lambda.py
   # Follow the printed AWS CLI commands
   ```

## API KEY SETUP

### OpenAI (for embeddings)
1. Get free key: https://platform.openai.com/api-keys
2. Set in Lambda environment:
   ```bash
   --environment "Variables={OPENAI_API_KEY=sk-...}"
   ```

### Groq (for LLM)
1. Get free key: https://console.groq.com
2. Set in Lambda environment:
   ```bash
   --environment "Variables={GROQ_API_KEY=gsk-...}"
   ```

## VERIFY BEFORE UPLOADING

```bash
# Check installation
python -c "import sentence_transformers; print('ERROR: sentence-transformers is installed!')" || echo "✓ Clean"
python -c "import chromadb; print('ERROR: chromadb is installed!')" || echo "✓ Clean"

# Check file sizes
ls -lh lambda_build/lambda-deployment.zip
# Should be <500MB

# Test locally first
python -m uvicorn lambda_handler:app --port 8000
# Visit http://localhost:8000/docs
```

## TROUBLESHOOTING

**Q: "No module named 'sentence_transformers'"**
- ✓ This is expected on Lambda! Use API embeddings instead.
- Use `rag_engine_lambda.py` not `rag_engine.py`

**Q: "Bundle size exceeds 500MB"**
- Check: `pip list | wc -l` (should be <50 packages)
- Run: `pip uninstall sentence-transformers chromadb torch -y`
- Reinstall: `pip install -r requirements-lambda.txt`

**Q: "OPENAI_API_KEY not set"**
- Lambda won't load your `.env` file
- Must set via: `aws lambda update-function-configuration --environment Variables="{OPENAI_API_KEY=...}"`

**Q: "Index doesn't persist between Lambda invocations"**
- Normal behavior: `/tmp/` is cleared between cold starts
- Solution: Store index in S3 or DynamoDB between requests

## FILE CHECKLIST

**✅ Upload to GitHub & AWS:**
- backend/
- frontend/
- data/protocols/
- app.py
- lambda_handler.py
- requirements-lambda.txt ← IMPORTANT!
- LAMBDA_DEPLOYMENT.md
- deploy_lambda.py

**❌ Don't upload:**
- requirements.txt (too large, local dev only)
- venv/ (recreated from requirements)
- chroma_db/ (regenerated automatically)
- .env (contains secrets)
