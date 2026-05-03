#!/usr/bin/env python
"""
Deploy to AWS Lambda - Optimized for 500MB limit
Usage: python deploy_lambda.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

def deploy():
    print("🚀 Building Lambda deployment package...")
    
    # Directories
    project_root = Path(__file__).parent
    build_dir = project_root / "lambda_build"
    package_dir = build_dir / "package"
    
    # Clean previous builds
    if build_dir.exists():
        shutil.rmtree(build_dir)
    
    build_dir.mkdir()
    package_dir.mkdir()
    
    # Step 1: Install dependencies with --no-cache-dir for smaller size
    print("📦 Installing dependencies (requirements-lambda.txt)...")
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "-r", str(project_root / "requirements-lambda.txt"),
        "-t", str(package_dir),
        "--no-cache-dir",
        "--compile"
    ], check=True)
    
    # Step 2: Copy source code
    print("📂 Adding source files...")
    shutil.copytree(
        project_root / "backend",
        package_dir / "backend",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "chroma_db")
    )
    shutil.copytree(
        project_root / "data",
        package_dir / "data"
    )
    shutil.copy(project_root / "app.py", package_dir / "app.py")
    shutil.copy(project_root / "lambda_handler.py", package_dir / "lambda_handler.py")
    
    # Step 3: Remove unnecessary files
    print("🧹 Cleaning up unnecessary files...")
    for pattern in ["*.dist-info", "__pycache__", "*.pyc", ".git"]:
        for p in package_dir.rglob(pattern):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
    
    # Step 4: Get size
    total_size = sum(f.stat().st_size for f in package_dir.rglob('*') if f.is_file())
    size_mb = total_size / (1024 * 1024)
    
    print(f"📊 Package size: {size_mb:.1f} MB")
    
    if size_mb > 500:
        print(f"❌ ERROR: Package exceeds 500MB ({size_mb:.1f} MB)")
        print("   Try: pip uninstall sentence-transformers chromadb")
        return False
    
    # Step 5: Create zip
    print("📦 Creating deployment package...")
    zip_path = build_dir / "lambda-deployment.zip"
    shutil.make_archive(
        str(zip_path).replace(".zip", ""),
        "zip",
        package_dir
    )
    
    zip_size = zip_path.stat().st_size / (1024 * 1024)
    print(f"✅ Deployment package ready: {zip_path}")
    print(f"   Zip size: {zip_size:.1f} MB")
    
    # Step 6: Print deployment command
    print("\n" + "="*70)
    print("NEXT: Deploy to AWS Lambda")
    print("="*70)
    print(f"""
aws lambda create-function \\
  --function-name ambulance-rag \\
  --runtime python3.12 \\
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-exec-role \\
  --handler lambda_handler.handler \\
  --zip-file fileb://{zip_path} \\
  --timeout 60 \\
  --memory-size 3008 \\
  --environment Variables="{{OPENAI_API_KEY=sk-...,GROQ_API_KEY=...}}"

Or update an existing function:

aws lambda update-function-code \\
  --function-name ambulance-rag \\
  --zip-file fileb://{zip_path}
""")
    
    return True


if __name__ == "__main__":
    success = deploy()
    sys.exit(0 if success else 1)
