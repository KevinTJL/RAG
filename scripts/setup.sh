#!/usr/bin/env bash
set -euo pipefail

cd /Users/apple/Documents/php/RAG
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

ollama pull qwen2.5:3b
ollama pull mxbai-embed-large

echo "Setup complete."
