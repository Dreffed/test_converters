FROM python:3.12-slim

ENV APP_DATA_DIR=/data \
    APP_PORT=8080 \
    POPPLER_PATH=/usr/bin

WORKDIR /app

COPY requirements.base.txt /app/
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.base.txt

COPY . /app

VOLUME ["/data"]
EXPOSE 8080

CMD ["uvicorn", "ui_server:app", "--host", "0.0.0.0", "--port", "8080"]
