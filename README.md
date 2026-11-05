# VideoMind AI

**VideoMind AI** is a multilingual video understanding workspace. It turns uploaded videos and supported public YouTube caption URLs into timestamped transcripts, translated transcript segments, summaries, subtitles, chapter outlines, study material, semantic search results, and RAG-grounded chat answers.

This repository is a runnable MVP with an extensible architecture. It uses real speech recognition, sentence-transformer embeddings, a vector-backed retrieval pipeline, and an OpenAI-compatible LLM endpoint. It does not use prefilled or simulated AI responses.

## Features in this build

| Feature | Current implementation |
|---|---|
| User registration and login | JWT bearer authentication |
| Upload video | MP4, MOV, AVI, MKV, WebM, MPEG; configurable size limit |
| Speech transcription | faster-whisper + FFmpeg; background task |
| Public video URL | YouTube caption retrieval through `youtube-transcript-api`; caption availability required |
| Transcript | Timestamped segments, edit and re-index |
| Multilingual translation | LLM-based segment translation with original timestamps |
| RAG | Segment-aware chunking, multilingual embeddings, per-video retrieval, timestamped source chunks |
| Vector persistence | pgvector column on PostgreSQL; JSON vector storage for local SQLite mode |
| Video Q&A | RAG retrieval + LLM answer + source time ranges |
| Summaries | Short, detailed, bullet, key-takeaway, technical, revision, etc. |
| Study assistant | Notes, MCQs, flashcards, viva prompts |
| Chapters | LLM-generated topic chapters with time ranges |
| Semantic search | Multilingual query embeddings and transcript chunk retrieval |
| Subtitles | SRT and WebVTT downloads, original or translated |
| Export | TXT, Markdown, PDF, DOCX |
| Video workspace | React UI with video player, transcript editor, chat, translation, study tools, chapters, and export |
| Docker | Compose setup with PostgreSQL + pgvector |

## Architecture

```text
Video upload / YouTube captions
            |
            v
      FFmpeg audio extraction (uploaded files)
            |
            v
   faster-whisper transcription / caption segments
            |
            v
  Timestamped transcript segments (SQL database)
            |
            v
  Transcript chunking + overlap + timestamp metadata
            |
            v
    multilingual SentenceTransformer embeddings
            |
            v
      PostgreSQL + pgvector (or SQLite dev mode)
            |
User question -> query embedding -> per-video retrieval
            |                          |
            +------ relevant chunks ---+
                           |
                           v
             OpenAI-compatible LLM endpoint
                           |
                           v
        Grounded answer + source timestamp references
```

### Main technology choices

- **Frontend:** React, TypeScript, Vite, Lucide icons, custom responsive CSS.
- **Backend:** FastAPI, SQLAlchemy, Pydantic, JWT, BackgroundTasks.
- **Speech:** FFmpeg and faster-whisper.
- **Embeddings:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dimensional multilingual vectors; selected as a comparatively compact default).
- **Vector store:** PostgreSQL + pgvector in Docker; SQLite + JSON vectors for simple local development.
- **LLM:** Any configured OpenAI-compatible API. A local Ollama OpenAI-compatible endpoint can also be used.
- **Video captions:** `youtube-transcript-api` for available YouTube captions. The app does not bypass restrictions or download arbitrary videos.

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- FFmpeg installed and available on `PATH` for uploaded video processing.
- Internet access on first model use so faster-whisper and SentenceTransformer model weights can be downloaded, unless you have already cached them.
- An LLM API key, or an OpenAI-compatible local model server such as Ollama, for chat, translation, summaries, study material, and chapter generation.

A computer with 16 GB RAM can run the default CPU configuration, but first model downloads and long videos will take time. For a lower-memory laptop, use `WHISPER_MODEL=tiny` or `small` only after testing quality, and process shorter videos first.

## Option 1: Run locally on Windows

### 1. Install FFmpeg

Install FFmpeg and make sure this command works in a new terminal:

```powershell
ffmpeg -version
```

### 2. Configure the backend

Open a terminal in the project folder:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env`:

```env
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=sqlite:///./videomind.db
UPLOADS_DIR=../storage/uploads
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSIONS=384
LLM_API_KEY=your-api-key
LLM_BASE_URL=
LLM_MODEL=gpt-4o-mini
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

If you use Ollama instead of a hosted API, configure its OpenAI-compatible endpoint. For example:

```env
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1:8b
```

Make sure the selected model is actually available in Ollama. Do not commit `.env` or API keys to GitHub.

### 3. Start the backend

From the `backend` directory, with the virtual environment active:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check the API at:

- Health: <http://localhost:8000/api/health>
- API documentation: <http://localhost:8000/docs>

### 4. Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open <http://localhost:5173>.

Create an account, upload a short video, and wait for processing. The first transcription and embedding runs download model weights and can take longer than subsequent runs.

## Option 2: Run with Docker Compose

1. Install Docker Desktop and start it.
2. In the project root, create a `.env` file if you want to configure an LLM key:

```env
LLM_API_KEY=your-api-key
LLM_BASE_URL=
LLM_MODEL=gpt-4o-mini
```

3. Start the services:

```bash
docker compose up --build
```

4. Open:

- Frontend: <http://localhost:5173>
- Backend docs: <http://localhost:8000/docs>

Docker Compose uses PostgreSQL with pgvector. Persistent database, uploaded media, and model caches are stored in Docker volumes or the project `storage` directory.

**Before any public deployment:** change the database password and `SECRET_KEY`, configure HTTPS and private object storage, set strict CORS origins, add rate limiting and quotas, and review the media access-token approach. The Compose credentials are for local development only.

## Using the application

1. Register or sign in.
2. Upload a supported video, or paste a YouTube URL with accessible captions.
3. Wait until video status becomes `ready`.
4. Confirm that `RAG indexed` appears before using semantic search or video chat.
5. Open **Transcript** to search, edit, and save the transcript. Saving rebuilds the chunk index.
6. Open **Translate** to choose a target language.
7. Open **Summary** to generate an AI summary.
8. Open **Ask video** to ask a question. The response includes retrieved transcript source ranges; select a source to seek to that time in an uploaded video.
9. Use **Study tools**, **Chapters**, **Subtitles**, and **Export** for the remaining workflows.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQL database connection | `sqlite:///./videomind.db` |
| `SECRET_KEY` | JWT signing secret | development placeholder (replace it) |
| `UPLOADS_DIR` | Upload storage path | `../storage/uploads` |
| `MAX_UPLOAD_MB` | Maximum upload size | `500` |
| `WHISPER_MODEL` | faster-whisper model size/name | `base` |
| `WHISPER_DEVICE` | `cpu` or `cuda` | `cpu` |
| `WHISPER_COMPUTE_TYPE` | CTranslate2 compute type | `int8` |
| `EMBEDDING_MODEL` | SentenceTransformer model | multilingual MiniLM L12 v2 |
| `EMBEDDING_DIMENSIONS` | Vector width; must match selected model | `384` |
| `LLM_API_KEY` | Hosted LLM API key | empty |
| `LLM_BASE_URL` | Optional OpenAI-compatible endpoint | empty |
| `LLM_MODEL` | Chat model name | `gpt-4o-mini` |
| `CORS_ORIGINS` | Allowed frontend origins | local Vite origins |

## API overview

FastAPI interactive docs at `/docs` list all endpoints. Main routes include:

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `POST /api/videos/upload`, `POST /api/videos/process-url`, `GET /api/videos`
- `GET /api/videos/{id}/status`, `GET /api/videos/{id}/transcript`, `PUT /api/videos/{id}/transcript`
- `POST /api/videos/{id}/translate`, `GET /api/videos/{id}/translations`
- `POST /api/videos/{id}/summarize`, `POST /api/videos/{id}/chat`
- `POST /api/videos/{id}/study`, `POST /api/videos/{id}/chapters`
- `POST /api/videos/{id}/search`, `GET /api/videos/{id}/subtitles/{language}`
- `GET /api/videos/{id}/export`, `DELETE /api/videos/{id}`

All video routes require a Bearer token except health. The video element uses a JWT query parameter because native media elements cannot attach a Bearer header; for a public production deployment, replace this with signed object-storage URLs or authenticated cookie streaming.

## Tests

From `backend`:

```bash
python -m pytest
```

The included tests cover semantic chunk timestamp handling, SRT/VTT time formatting, and YouTube URL allow-list validation. Add integration tests with small sample videos and a test LLM endpoint before production use.

## Known limitations and next engineering steps

This is an integrated starter/MVP, not a claim of production readiness. The following items need further work for a full production release:

- **Speaker diarization:** transcript schema supports speaker metadata, but a diarization model (for example, a compatible pyannote pipeline with its access requirements) is not wired in yet.
- **Public URLs:** this build supports YouTube caption retrieval. It does not download media from arbitrary public URLs or bypass unavailable/private captions. A compliant provider adapter can be added per platform.
- **Translation and generative features:** require a configured LLM endpoint. Translation is processed in batches and keeps segment time ranges, but human review is advised for technical and subtitle use.
- **RAG quality:** the MVP uses semantic embeddings and cosine retrieval. Hybrid BM25/vector retrieval, a cross-encoder reranker, ANN tuning, multilingual benchmark evaluation, and query rewriting are natural upgrades.
- **Long-video jobs:** FastAPI BackgroundTasks are used for the starter. For concurrent production workloads, move processing to Celery/RQ with Redis, job leases, retries, and worker isolation.
- **Video playback:** uploaded videos have a protected development stream route; YouTube player embedding is provided. Timestamp seeking through the embedded YouTube player can be upgraded to the YouTube IFrame Player API.
- **Storage and operations:** use private object storage, retention policies, virus scanning, content quotas, observability, and automated database migrations for deployment.
- **PDF/DOCX:** implemented through ReportLab and python-docx; formatting can be improved for complex Markdown and multilingual fonts.

## Suggested next enhancements

1. Add speaker diarization and speaker-aware retrieval.
2. Add hybrid retrieval (BM25 + multilingual vector search) and a cross-encoder reranker.
3. Move background jobs to Celery + Redis.
4. Add live progress updates using WebSockets or Server-Sent Events.
5. Add a model evaluation dashboard for WER, Recall@K, MRR, NDCG, faithfulness, and citation accuracy.
6. Add a production object-storage adapter and signed media URLs.
