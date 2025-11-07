# Web UI + Dockerization Plan

## Goals
- Provide a simple web UI to control and observe the benchmark suite.
- Package the app in Docker for easy relocation and reproducibility.
- Persist inputs and results across restarts via mounted volumes.

## Core Pages
- Main Page
  - Upload one or more documents (PDFs) to a managed data folder.
  - List prior runs with status, date, selected converters, and quick links to reports/visuals.
  - Action buttons: Start New Run, Re-run, View Results.
- Setup Page
  - Configure defaults: converters, baseline, output dir, visualization flags (renderer, dpi, iou, match), OCR/Tesseract options, poppler path (container path), verbosity.
  - Detect available converters and show their status.
  - Save as server-side config (JSON) and environment variables.
- Test Run Page
  - Form inputs: document(s), converters, baseline, output dir, visualization options, pages range, tesseract dpi, poppler path, verbose.
  - Show live status/progress (queued, running, finished, failed), logs tail, and final artifacts.
  - Links to: summary markdown, benchmark report JSON, detailed results JSON, visual metrics, visual images.

## Architecture Overview
- Backend: Python FastAPI
  - Reasons: small footprint, async endpoints, easy file upload, docs via OpenAPI.
  - Executes benchmarks by spawning subprocesses (or in-process calls) using existing modules.
  - Provides a jobs registry for runs.
- Frontend: Lightweight React or Server-rendered HTML + htmx
  - Prefer minimal JS (htmx/Alpine.js) to simplify packaging.
  - Initial version can be server-rendered templates + htmx polling for job status.
- Storage
  - Inputs: `/data/uploads/`
  - Outputs: `/data/results/` (maps to `benchmark_results/` inside app)
  - Metadata DB: SQLite `/data/app.db` (track runs, files, options, status, artifacts)
- Job Runner
  - Simple in-process queue (async task manager) for MVP.
  - Optional: move to Celery/RQ + Redis for concurrency in Phase 2.

## Data Model (SQLite)
- tables
  - runs(id, created_at, status[pending|running|done|failed], label, baseline, converters_json, options_json, input_files_json, output_dir, summary_path, report_path, details_path, visual_dir, error_text)
  - files(id, run_id, path, size, page_count, type)
- indexing by created_at and status for quick lists

## API (FastAPI)
- Health & Config
  - GET `/api/health`
  - GET `/api/config` → current defaults
  - POST `/api/config` → update defaults
  - GET `/api/converters` → probe and list available converters with status
- Files
  - GET `/api/files` → list uploaded files
  - POST `/api/files` (multipart) → upload PDF(s) to `/data/uploads`
  - DELETE `/api/files/{id}`
- Runs
  - GET `/api/runs` → list runs (filters: status)
  - POST `/api/runs` → create a run with body: files[], converters[], baseline, viz opts, output dir
  - GET `/api/runs/{id}` → run details incl. artifacts
  - GET `/api/runs/{id}/logs` → last N lines from live log
  - POST `/api/runs/{id}/cancel` (best-effort)
- Artifacts
  - GET `/api/artifacts/{path}` → serve files from results dir (summary.md, jsons, images)

## Backend Implementation Notes
- Running a benchmark
  - Prefer in-process invocation of `DocumentConverterBenchmark` with constructed args and converter functions (no separate process needed).
  - For isolation, you can call `python run_benchmark.py` as a subprocess and stream stdout for logs. Choose based on simplicity vs. control.
  - Respect `--poppler-path` mounted inside container; do not expose host paths.
- Visualization integration
  - Pass UI-selected options to the benchmark constructor.
  - Persist artifacts paths in the run record for quick linking.
- Discovery of prior results
  - Periodic sweep of `/data/results` to associate orphaned artifacts with runs if needed.

## Frontend UX (Server-rendered + htmx)
- Main Page (`/`)
  - Upload widget (drag-drop), list of files with size/date.
  - Table of runs (id, label, created, status, files count, converters, links: summary, visuals).
  - Button: New Run → `/runs/new`
- Setup Page (`/settings`)
  - Converters availability panel.
  - Form for defaults (with validation) and save.
- New Run (`/runs/new`)
  - Multi-select files (from uploaded list).
  - Converters checkboxes (disabled if unavailable), baseline select.
  - Visualization options: renderer, dpi, iou threshold, match mode, export blocks.
  - OCR options: tesseract dpi, poppler path.
  - Submit creates run and redirects to `/runs/{id}`.
- Run Details (`/runs/{id}`)
  - Live status + log tail (htmx poll or WebSocket in Phase 2).
  - On complete: links to artifacts, visual image gallery (page thumbnails), metrics table.

## Dockerization
- Structure
  - Base image: `python:3.12-slim`
  - Install system packages as needed (tesseract, poppler optional or mount externally).
  - Install Python deps from `requirements.txt` plus: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `sqlalchemy`, `alembic` (optional), `htmx` served statically.
  - Copy app code under `/app`.
- Volumes
  - `/data` (host bind mount) for persistence of uploads, results, and DB.
  - Optional: mount tesseract/poppler binaries if not installing inside image.
- Ports
  - Expose `8080` (internal) → map to host `8080`.
- Example Dockerfile (sketch)
  ```dockerfile
  FROM python:3.12-slim
  RUN apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils tesseract-ocr && rm -rf /var/lib/apt/lists/*
  WORKDIR /app
  COPY requirements.txt /app/
  RUN pip install -r requirements.txt \
      && pip install fastapi uvicorn[standard] jinja2 python-multipart sqlalchemy
  COPY . /app
  ENV APP_DATA_DIR=/data \
      APP_PORT=8080
  VOLUME ["/data"]
  EXPOSE 8080
  CMD ["uvicorn", "ui_server:app", "--host", "0.0.0.0", "--port", "8080"]
  ```
- docker-compose.yml (sketch)
  ```yaml
  services:
    app:
      build: .
      ports:
        - "8080:8080"
      volumes:
        - ./data:/data
      environment:
        - APP_DATA_DIR=/data
        - POPPLER_PATH=/usr/bin
        - TESSERACT_PATH=/usr/bin/tesseract
  ```

## Security & Ops
- Intended for local/LAN usage by trusted users.
- Restrict file access to `/data/uploads` and `/data/results`; reject absolute host paths.
- Validate MIME type and extension on upload.
- Limit concurrent jobs (configurable) to prevent resource exhaustion.
- Log to rotating files under `/data/logs`.

## Migration & Relocation
- All user inputs, results, and DB live under `/data` volume → copy/move this folder to relocate.
- Image rebuilds are stateless; config defaults can also be provided via environment variables.

## Phase Plan
- Phase A (MVP)
  - Backend FastAPI with endpoints above.
  - Server-rendered templates + htmx polling for status.
  - In-process job runner; SQLite persistence.
  - File upload/listing; create run; view results.
- Phase B
  - WebSocket live logs and progress.
  - Concurrency control and queued runs.
  - Filters/sorting for runs; pagination.
- Phase C
  - Pluggable auth (basic or OAuth proxy).
  - Export/import of run configs; presets.
  - Optional Celery/RQ worker for distributed runs.

## Implementation Checklist
- [ ] Define DB models and migrations (alembic optional)
- [ ] Implement converter availability probe endpoint
- [ ] Implement upload/list/delete files
- [ ] Implement create/run job and status tracking
- [ ] Implement artifacts indexing and serving
- [ ] Implement settings persistence and defaults
- [ ] Build templates for main/settings/run details
- [ ] Containerize with Dockerfile and compose
- [ ] Document deployment and volume usage

