FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# PyMuPDF and OCR fallback need these at runtime, not just at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

# Parsers process untrusted documents, so the process does not run as root.
RUN useradd --create-home --uid 10001 noema \
    && mkdir -p /var/lib/noema/uploads \
    && chown -R noema:noema /app /var/lib/noema
USER noema

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "noema.main:app", "--host", "0.0.0.0", "--port", "8000"]
