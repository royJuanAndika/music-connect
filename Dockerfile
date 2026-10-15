FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt yt-dlp

COPY app ./app
COPY web ./web

# Port Web Player (8000) & Healthcheck (8080)
EXPOSE 8000 8080
VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
