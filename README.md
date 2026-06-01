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
<项目根目录>
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
- Ask questions against local documents with dual-scope retrieval (system + personal).
- Rewrite follow-up questions into standalone search queries.
- Extract core knowledge terms before vector search to strengthen retrieval.
- Search both the shared document knowledge base and per-user long-term memory.
- Diagnose possible knowledge gaps using the current Q&A, retrieved chunks, previous long-term memories, and the existing learning profile.
- Persist a per-user learning profile with concept weakness scores, misconceptions, and review suggestions.
- Show retrieved source chunks under each answer.
- Open retrieved citations in a source viewer and inspect the original document or PDF page.
- Generate three clickable follow-up questions after each answer.
- Generate review plans for weak concepts, judge answers, save review history, and update weakness scores after review.
- Per-model DeepSeek thinking mode toggles (settings page): enable/disable deep reasoning individually for `deepseek-v4-flash` and `deepseek-v4-pro`.
- Custom OpenAI-compatible API model support.
- Render Markdown and math formulas in the frontend.

Note: graph-related files are present for future/optional knowledge-graph work, but the default query path currently uses vector RAG. Graph extraction is not enabled in `app/ingest.py`.

## Requirements

- Python 3.11+ is recommended.
- **Anaconda / Miniconda** (required — ChromaDB on Windows has C-extension ABI issues when installed via pip, conda-forge provides compatible native dependencies).
- Ollama must be installed and running locally.
- Node.js 18+ (for the frontend).
- Required Ollama models:

```bash
ollama pull qwen2.5:3b
ollama pull bge-m3
```

The default `.env.example` and `app/config.py` use `bge-m3` for embeddings.
If you choose `deepseek-v4-pro` or `deepseek-v4-flash` in the chat UI, Ollama is still used for embeddings and DeepSeek is used for chat generation.

## Setup

```bash
# 进入项目根目录
cd <项目根目录>

# 创建 conda 环境（推荐，避免 ChromaDB C 扩展 ABI 冲突）
conda env create -f environment.yml
conda activate rag

# 如果因网络原因 conda 较慢，可先用 environment.yml 安装 chromadb，
# 其余依赖再用 pip 补装：
#   conda install -c conda-forge chromadb
#   pip install -r requirements.txt
```

创建你的本地 `.env` 配置文件：

```bash
cp .env.example .env
# 编辑 .env：只需设置 AUTH_SECRET 和 DEEPSEEK_API_KEY，
# 路径变量均自动推导，一般无需修改。
```

## Run

**确保 Ollama 已运行**，且所需模型已拉取。

启动后端 API：

```bash
conda activate rag
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

打开另一个终端，安装并启动前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173
```


## Add Knowledge Files

Put system-wide files into项目根目录下的 `data/raw` 目录。

Supported formats:

- `.txt`
- `.md`
- `.pdf`

Files in `data/raw` are the shared system knowledge base. Every user can read and retrieve from it, but regular users cannot upload or delete these files from the web UI.

Users can upload personal files directly in the web UI. Personal files are stored under `data/users/<user_id>`。

## Manual Index Rebuild

```bash
# 确保已激活虚拟环境
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

Configuration is read from `.env` if present. Copy `.env.example` to `.env` and edit.

### 必须配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AUTH_SECRET` | JWT 签名密钥 | 自动生成（生产环境建议固定一个长随机串） |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 无（使用 DeepSeek 模型则必须配置） |

### 路径配置（自动推导，一般不需要改）

以下路径变量无需手动设置，程序会自动使用项目根目录下的相对路径：

- `CHROMA_PATH` → 自动使用 `<项目根目录>/db/chroma`
- `DATA_DIR` → 自动使用 `<项目根目录>/data/raw`
- `USER_DATA_ROOT` → 自动使用 `<项目根目录>/data/users`

如需自定义路径，可在 `.env` 中设置。

### DeepSeek Thinking 模式

`DEEPSEEK_THINKING_ENABLED`（`.env`）是系统级默认值。用户可在前端的**设置页面**按模型单独开启/关闭 thinking：

- `deepseek-v4-flash` 和 `deepseek-v4-pro` 均支持 thinking 模式
- 开启后模型会先深度推理再作答，质量更高但耗时更长
- 优先级：按模型设置 > 用户全局设置 > `.env` 系统默认

### 其他可选配置

```env
APP_ENV=development
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
OLLAMA_HOST=http://localhost:11434
CHAT_MODEL=qwen2.5:3b
EMBED_MODEL=bge-m3
AVAILABLE_CHAT_MODELS=qwen2.5:3b,deepseek-v4-pro,deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_REASONING_EFFORT=high
DEEPSEEK_THINKING_ENABLED=true
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
conda env create -f environment.yml
conda activate rag

cp .env.production.example .env.production
# edit .env.production: set domain and DEEPSEEK_API_KEY

cd frontend
npm install
cp .env.production.example .env.production
# edit frontend/.env.production: set VITE_API_URL=https://your-domain.com
npm run build
```

Then install `deploy/rag-api.service` into systemd and copy `deploy/nginx.conf` into your Nginx sites configuration. Replace `your-domain.com` and `/opt/rag` with your actual domain and deployment path before enabling them.

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

## 换机部署 / 新机器首次启动 Checklist

项目已做路径自动推导，换机器后大多无需修改配置。按以下步骤操作：

### 1. 前置依赖

- Python 3.11+
- **Anaconda / Miniconda**（ChromaDB 必须通过 conda 安装，pip 版本在 Windows 上会崩溃）
- [Ollama](https://ollama.com/) 已安装并在后台运行
- Node.js 18+（仅前端需要）

### 2. 拉取 Ollama 模型

```bash
ollama pull qwen2.5:3b
ollama pull bge-m3
```

### 3. 项目初始化

```bash
# 克隆项目到任意目录
cd <项目根目录>

# 创建 conda 环境并安装依赖
conda env create -f environment.yml
conda activate rag

# 创建 .env 配置文件
cp .env.example .env
```

### 4. 编辑 `.env`（只需改两项）

```env
# 生产部署时建议设置一个固定长随机串
AUTH_SECRET=你的固定密钥

# 如果使用 DeepSeek 模型则必须填写
DEEPSEEK_API_KEY=sk-你的key
```

**不需要修改任何路径变量**——`CHROMA_PATH`、`DATA_DIR`、`USER_DATA_ROOT` 均自动推导。

### 5. 启动

```bash
# 后端
conda activate rag
uvicorn app.api:app --host 0.0.0.0 --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`，注册账号后即可使用。

### 6. （可选）导入系统知识库

将 `.txt` / `.md` / `.pdf` 文件放入 `data/raw/`，然后：

```bash
python -m app.ingest
```

---

## Security & Privacy

### `.gitignore` 保护的敏感数据

以下文件和目录**不会被提交到 Git**（详见 `.gitignore`）：

| 文件/目录 | 包含内容 | 风险 |
|-----------|----------|------|
| `.env` | API keys、密钥 | 明文凭据泄露 |
| `db/users.json` | 用户邮箱 + PBKDF2 密码哈希 | 账户信息泄露 |
| `db/user_settings/` | 加密的 OpenAI API key | 可被离线破解 |
| `db/profiles/` | 用户学习画像 | 隐私数据 |
| `data/users/` | 用户上传的个人文档 | 隐私数据 |

### 给开发者的建议

- **永远不要** 将 `.env` 提交到仓库。`.env.example` 是安全的模板文件。
- 如果项目曾被提交过凭据（有 Git 历史），请立即轮换 API key 并考虑 `git filter-branch` 清理历史。
- `AUTH_SECRET` 变更会使所有已签发 token 失效，用户需重新登录。

---

## Notes

- Restart the backend after changing Python files.
- Refresh the browser after changing `index.html`.
- If follow-up buttons or frontend behavior look stale, clear the browser cache or localStorage for `127.0.0.1:8080`.
- If Ollama is not running, `/api/query` returns a 503 error.
- User long-term memory is stored in separate ChromaDB collections named `user_memory_{user_id}`.
- User learning profiles are stored as JSON files under `db/profiles/`.
- In `concept_mastery`, the `score` field is used as a weakness score: higher means weaker, and `0` means the concept can be cleared from the active weak-concept view.
