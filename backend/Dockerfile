# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

# No system dependencies: DOCX (python-docx) and PDF (reportlab) rendering are both pure
# Python wheels, so the image stays small and builds fast. (This used to install Tectonic
# and pre-warm a LaTeX package cache — the reportlab renderer removed all of that.)

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SIMPLYAPPLY_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
