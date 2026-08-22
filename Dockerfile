FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 moolias \
    && install -d -o moolias -g moolias /data

COPY pyproject.toml README.md LICENSE ./
COPY moolias ./moolias
RUN pip install --no-cache-dir .

USER moolias
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.parse, urllib.request; host=urllib.parse.urlparse(os.environ['MOOLIAS_BASE_URL']).hostname; req=urllib.request.Request('http://127.0.0.1:8000/healthz', headers={'Host': host}); urllib.request.urlopen(req, timeout=3)"]

CMD ["uvicorn", "moolias.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
