FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Pasang Deno resmi untuk JS challenge solver yt-dlp
RUN curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt yt-dlp edge-tts

COPY app ./app
COPY web ./web

# Port Web Player (8000) & Healthcheck (8080)
EXPOSE 8000 8080
VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
