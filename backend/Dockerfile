FROM python:3.11-slim

WORKDIR /app

# Install system deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation fonts-indic libx11-6 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from root (contains all dependencies)
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (--with-deps handles system libs)
RUN playwright install chromium

# Copy app
COPY . .

# Create data dir
RUN mkdir -p data/screenshots data/voice_cache

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "server.py"]