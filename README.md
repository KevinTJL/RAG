# Local RAG Knowledge Assistant

This project is a local Retrieval-Augmented Generation (RAG) knowledge assistant for learning and document Q&A.

It uses:

- Ollama for local chat and embedding models
- DeepSeek/OpenAI-compatible chat models as an optional chat backend
- ChromaDB for persistent vector search
- FastAPI for the backend API
- Vue 3 + Vite + TypeScript frontend under `frontend/`
- pypdf for PDF text extraction

The current query pipeline includes question rewriting, core-term extraction, vector retrieval, user long-term memory, answer generation, follow-up question buttons, and a per-user learning profile for knowledge-gap diagnosis.

## Project Layout

```text
/Users/apple/Documents/php/RAG
├── app/
│   ├── api.py              # FastAPI API and main query workflow
│   ├── config.py           # Environment-based settings
│   ├── ingest.py           # Document loading, chunking, embedding, indexing
│   ├── loaders.py          # TXT/MD/PDF loaders
│   ├── ollama_client.py    # Ollama chat/embed client
│   ├── query.py            # Prompt and context builder
│   ├── text_utils.py       # Text cleaning and chunk splitting
│   ├── vector_store.py     # ChromaDB collections
│   ├── graph_extractor.py  # Optional graph triplet extraction helper
│   └── graph_store.py      # Optional NetworkX graph persistence helper
├── data/raw/               # System knowledge documents, read-only for users
├── data/users/             # Per-user personal knowledge documents
├── db/chroma/              # ChromaDB persistent vector database
├── db/profiles/            # Per-user learning profiles
├── frontend/               # Vue 3 + Vite + TypeScript frontend
├── index.html              # Legacy launcher / startup note
├── requirements.txt
└── .env.example
```

`data/` and `db/` are runtime knowledge-base directories and are not source code.

## Features

- Upload `.txt`, `.md`, and `.pdf` files from the web UI.
- Use separated pages for chat, knowledge-base management, and review plans.
- Preview knowledge-base files online; PDF files are rendered with page navigation.
- Rebuild the ChromaDB vector index after upload or deletion.
- Ask questions against local documents.
- Rewrite follow-up questions into standalone search queries.
- Extract core knowledge terms before vector search to strengthen retrieval.
- Search both the shared document knowledge base and per-user long-term memory.
- Diagnose possible knowledge gaps using the current Q&A, retrieved chunks, previous long-term memories, and the existing learning profile.
- Persist a per-user learning profile with concept weakness scores, misconceptions, and review suggestions.
- Show retrieved source chunks under each answer.
- Open retrieved citations in a source viewer and inspect the original document or PDF page.
- Generate three clickable follow-up questions after each answer.
- Generate review plans for weak concepts, judge answers, save review history, and update weakness scores after review.
- Render Markdown and math formulas in the frontend.

Note: graph-related files are present for future/optional knowledge-graph work, but the default query path currently uses vector RAG. Graph extraction is not enabled in `app/ingest.py`.

## Requirements

- Python 3.11 or newer is recommended.
- Ollama must be installed and running locally.
- Required Ollama models:

```bash
ollama pull qwen2.5:3b
ollama pull bge-m3
```

The default `.env.example` and `app/config.py` use `bge-m3` for embeddings.
If you choose `deepseek-v4-pro` or `deepseek-v4-flash` in the chat UI, Ollama is still used for embeddings and DeepSeek is used for chat generation.

## Setup

```bash
cd /Users/apple/Documents/php/RAG
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Optional: create your local `.env`.

```bash
cp .env.example .env
```

## Run

Start the backend API:

```bash
cd /Users/apple/Documents/php/RAG
source .venv/bin/activate
uvicorn app.api:app --host 0.0.0.0 --port 8000
```


Install and start the frontend in another terminal:

```bash
cd /Users/apple/Documents/php/RAG
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```
(这里改成自己的IP地址)


## Add Knowledge Files

Put system-wide files into:

```text
/Users/apple/Documents/php/RAG/data/raw
```

Supported formats:

- `.txt`
- `.md`
- `.pdf`

Files in `data/raw` are the shared system knowledge base. Every user can read and retrieve from it, but regular users cannot upload or delete these files from the web UI.

Users can upload personal files directly in the web UI. Personal files are stored under:

```text
/Users/apple/Documents/php/RAG/data/users/<user_id>
```

## Manual Index Rebuild

```bash
cd /Users/apple/Documents/php/RAG
source .venv/bin/activate
python -m app.ingest
```

This scans `data/raw`, extracts text, cleans and chunks it, creates embeddings with Ollama, and writes the vectors into the shared system ChromaDB collection.

The public collection is reset during ingest, so the document index is rebuilt from the current files in `data/raw`.

## Query Workflow

When a user asks a question, `POST /api/query` runs this flow:

```text
user question
-> rewrite with chat history into a standalone query
-> extract core knowledge terms with the chat model
-> build an enhanced retrieval query
-> embed the enhanced query
-> retrieve top-k document chunks from ChromaDB
-> retrieve up to 2 user long-term memory items
-> build the final context
-> generate the answer with Ollama
-> generate three follow-up questions
-> save useful user facts into long-term memory
-> analyze the user's knowledge gaps using Q&A + retrieved chunks + long-term memory + existing profile
-> update the user's learning profile
```

The enhanced retrieval query looks like:

```text
原始/改写后的问题
核心知识点：术语1、术语2、术语3
```

This gives vector search more explicit semantic anchors.

## Main API Endpoints

- `GET /api/files`  
  List uploaded knowledge files.

- `POST /api/upload`  
  Upload one personal knowledge file into `data/users/<user_id>`.

- `DELETE /api/files/{filename}`  
  Delete one knowledge file and rebuild the index.

- `POST /api/ingest`  
  Rebuild the authenticated user's personal vector index from `data/users/<user_id>`.

- `POST /api/query`  
  Ask a question. The response includes:

```json
{
  "answer": "assistant answer",
  "chunks": [],
  "followups": [],
  "core_terms": [],
  "learning_insight": {},
  "profile": {}
}
```

- `GET /api/profile/{user_id}`  
  Read the current learning profile for one user.

- `GET /api/files/{filename}/preview`  
  Preview a knowledge-base file. TXT/MD return text; PDF returns a raw URL for PDF.js.

- `GET /api/files/{filename}/raw`  
  Read the original file bytes for preview.

- `POST /api/review/plan`  
  Generate a review plan for a weak concept.

- `POST /api/review/answer`  
  Judge a review question or quiz answer.

- `POST /api/review/complete`  
  Complete a review session and update concept weakness.

- `GET /api/review/history/{user_id}`  
  Read saved review sessions.

## Configuration

Configuration is read from `.env` if present.

Important variables:

```env
APP_ENV=development
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
OLLAMA_HOST=http://localhost:11434
CHAT_MODEL=qwen2.5:3b
EMBED_MODEL=bge-m3
AVAILABLE_CHAT_MODELS=qwen2.5:3b,deepseek-v4-pro,deepseek-v4-flash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_THINKING_ENABLED=true
CHROMA_PATH=/Users/apple/Documents/php/RAG/db/chroma
COLLECTION_NAME=rag_demo
CHUNK_SIZE=500
CHUNK_OVERLAP=100
TOP_K=4
TEMPERATURE=0.2
TOP_P=0.9
NUM_CTX=4096
```

## Production Prep

This repository now includes the first deployment preparation layer:

- `GET /api/health` for load balancer and uptime checks.
- `.env.production.example` for server-side production configuration.
- `frontend/.env.production.example` for the production API URL used at build time.
- `deploy/nginx.conf` for serving the built frontend and proxying `/api/` to FastAPI.
- `deploy/rag-api.service` for running the backend with systemd.
- `scripts/run-production.sh` for a local production-style backend start.

Minimal single-server flow:

```bash
cd /opt/rag
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.production.example .env.production
# edit .env.production: set domain, paths, and DEEPSEEK_API_KEY

cd frontend
npm install
cp .env.production.example .env.production
# edit frontend/.env.production: set VITE_API_URL=https://your-domain.com
npm run build
```

Then install `deploy/rag-api.service` into systemd and copy `deploy/nginx.conf` into your Nginx sites configuration. Replace `your-domain.com` and `/opt/rag` before enabling them.

## Auth And User Isolation

The web UI requires email/password login before using the app. The backend exposes:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Authenticated requests use a bearer token:

```text
Authorization: Bearer <token>
```

The current lightweight auth store is file based:

```text
db/users.json
```

Passwords are stored as PBKDF2-SHA256 hashes. `db/users.json` is ignored by Git and should be treated as runtime data. For production, set a stable `AUTH_SECRET` in `.env.production`; changing it invalidates existing login tokens.

Per-user runtime data is separated by authenticated `user_id`:

- Shared system files: `data/raw/`
- Uploaded personal files: `data/users/<user_id>/`
- Shared system vector collection: `<COLLECTION_NAME>`
- Personal document vector collections: `<COLLECTION_NAME>_<user_id>`
- Long-term memory collections: `user_memory_<user_id>`
- Learning profiles: `db/profiles/<user_id>.json`
- Review history: `db/reviews/<user_id>.json`

This is suitable for an invitation-only beta. Before opening public registration widely, migrate users and sessions to PostgreSQL and add rate limits, quotas, password reset, email verification, and admin controls.

## Notes

- Restart the backend after changing Python files.
- Refresh the browser after changing `index.html`.
- If follow-up buttons or frontend behavior look stale, clear the browser cache or localStorage for `127.0.0.1:8080`.
- If Ollama is not running, `/api/query` returns a 503 error.
- User long-term memory is stored in separate ChromaDB collections named `user_memory_{user_id}`.
- User learning profiles are stored as JSON files under `db/profiles/`.
- In `concept_mastery`, the `score` field is used as a weakness score: higher means weaker, and `0` means the concept can be cleared from the active weak-concept view.
