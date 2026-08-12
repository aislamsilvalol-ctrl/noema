FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# psycopg/asyncpg build headers. Tesseract joins this list in Phase 2, when the
# OCR fallback that needs it actually exists.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The whole context is copied before installing because an editable install needs
# the package directory and the readme to exist. Splitting this to cache the
# dependency layer would mean listing the sources twice and getting it wrong.
COPY . .
RUN pip install --upgrade pip && pip install -e ".[dev]"

# Document parsing runs in this image against untrusted files, so it does not run
# as root. The uploads directory is created here rather than at first write, so a
# permission problem surfaces at build time.
RUN useradd --create-home --uid 10001 noema \
    && mkdir -p /var/lib/noema/uploads \
    && chown -R noema:noema /app /var/lib/noema \
    && chmod +x /app/docker-entrypoint.sh

# The container starts as root and the entrypoint drops to `noema` immediately —
# it stays root only long enough to chown a mounted volume, which always arrives
# owned by root no matter what the image did at build time. Compose has no volume
# on this path and takes the same path with nothing to fix.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "noema.main:app", "--host", "0.0.0.0", "--port", "8000"]
