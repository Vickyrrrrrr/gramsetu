FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     PIP_NO_CACHE_DIR=1     HEADLESS_BROWSER=true     HOST=0.0.0.0     PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     curl     ca-certificates     ffmpeg     libasound2     libatk-bridge2.0-0     libatk1.0-0     libcairo2     libcups2     libdbus-1-3     libdrm2     libgbm1     libglib2.0-0     libgtk-3-0     libnss3     libnspr4     libpango-1.0-0     libx11-6     libx11-xcb1     libxcb1     libxcomposite1     libxdamage1     libxext6     libxfixes3     libxkbcommon0     libxrandr2     libxshmfence1     libsndfile1     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .
RUN mkdir -p /app/data/screenshots /app/data/voice_cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3   CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)"

CMD ["uvicorn", "whatsapp_bot.main:app", "--host", "0.0.0.0", "--port", "8000"]
