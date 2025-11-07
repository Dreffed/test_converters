# Optional Extras and Sidecar Services

This project splits dependencies into core and extras to keep the base image slim and reliable.

## Installing Extras Locally
- Core only:
  - `pip install -r requirements.base.txt`
- Core + Extras:
  - `pip install -r requirements.base.txt -r requirements.extras.txt`

Extras include: markitdown, textract, unstructured, tika, pypandoc, and `requests` for sidecar HTTP calls.

## Docker Images
- Base image (recommended): installs only `requirements.base.txt` (see Dockerfile). This avoids fragile native deps.
- Extras can be layered or run as separate containers.

### Build an Extras Layer (optional)
Example `Dockerfile.extras`:
```dockerfile
FROM your/base:image
COPY requirements.extras.txt /app/
RUN pip install --no-cache-dir -r requirements.extras.txt
```
Build and run:
```bash
docker build -f Dockerfile.extras -t converter-suite:extras .
```

## Textract as a Sidecar Container
Textract often requires many system tools. Running it as a sidecar service keeps the main app small.

### Sidecar API (expected)
- HTTP POST `/extract` with multipart file field `file`
- Response JSON: `{ "text": "...extracted text..." }`
- Optional fields may include `{ "meta": { ... } }`

### Example Service (FastAPI sketch)
```python
from fastapi import FastAPI, UploadFile, File
import textract

app = FastAPI()

@app.post('/extract')
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    # Save to temp file or pass bytes to textract if supported
    text = textract.process(file.filename, input_stream=data).decode('utf-8', 'ignore')
    return { 'text': text }
```

### Example Sidecar Dockerfile
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev swig \
    libxml2-dev libxslt1-dev zlib1g-dev libjpeg-dev libpng-dev libmagic1 \
    antiword unrtf poppler-utils tesseract-ocr pstotext \
    sox libsox-fmt-mp3 ffmpeg flac ghostscript \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn textract requests
COPY sidecar_textract.py /app/sidecar_textract.py
WORKDIR /app
EXPOSE 8090
CMD ["uvicorn", "sidecar_textract:app", "--host", "0.0.0.0", "--port", "8090"]
```

## Using Sidecar from the Benchmark
- Enable the `textract_http` converter and point it at the sidecar URL.
- Two ways:
  - CLI flag (to be passed to converter kwargs): `--textract-url http://textract:8090/extract`
  - Environment variable: `TEXTRACT_URL=http://textract:8090/extract`

When enabled, the `textract_http` converter uploads the PDF and reads `text` back from JSON.

## docker-compose Example with Sidecar
```yaml
services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      - APP_DATA_DIR=/data
      - TEXTRACT_URL=http://textract:8090/extract
    volumes:
      - ./data:/data
    depends_on:
      - textract

  textract:
    build:
      context: ./extras/textract
      dockerfile: Dockerfile
    ports:
      - "8090:8090"
```

## Notes
- Sidecar approach isolates heavy native dependencies.
- If you don’t need a given extra, simply don’t install it.
- For `markitdown` on Windows, ensure pandas/numpy wheels match your Python.

