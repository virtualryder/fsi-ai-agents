# Document Intelligence Agent — Dockerfile
# ============================================================
# Multi-stage build:
#   Stage 1 (builder): Install Python dependencies and compile wheels.
#   Stage 2 (runtime): Minimal runtime image — no build tools, no caches.
#
# SECURITY DESIGN DECISIONS
# --------------------------
# 1. Non-root user: The agent runs as uid=1000 (agent09 user), not root.
#    Container breakout with root privileges would give an attacker host
#    root access. Non-root limits the blast radius of a container escape.
#
# 2. No ANTHROPIC_API_KEY in image: API keys are injected at runtime via
#    ECS task definition environment variables sourced from AWS Secrets
#    Manager. Baking secrets into Docker images is a critical security flaw
#    (images may be pushed to registries, stored in CI caches, etc.).
#
# 3. Minimal base image: python:3.11-slim (Debian slim) rather than full
#    Debian or Ubuntu. Fewer packages = smaller attack surface = fewer CVEs.
#
# 4. LOG_LEVEL=WARNING: Suppresses verbose LangGraph INFO logs that may
#    inadvertently include extracted text fragments in CloudWatch Logs.
#
# 5. Tesseract OCR is installed from system packages, not pip, to use the
#    OS-managed version with security updates from Debian package repos.
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for packages with C extensions (pdfplumber, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc6-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a prefix directory.
# This allows Stage 2 to copy only the installed packages, not the build tools.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

# Install runtime system dependencies:
# - tesseract-ocr: OCR engine for scanned documents (TIFF, JPG, PNG)
# - libglib2.0-0, libsm6, libxext6: Required by PyMuPDF/Pillow for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Create non-root user (uid=1000) to run the application.
# Running as root in a container is a security anti-pattern — if the container
# is compromised, non-root limits what an attacker can do on the host.
RUN useradd --uid 1000 --create-home --shell /bin/bash agent09
WORKDIR /app

# Copy application code
COPY --chown=agent09:agent09 . .

# Create the data directory for any runtime-generated files
RUN mkdir -p /app/data/uploads && chown agent09:agent09 /app/data/uploads

# Switch to non-root user
USER agent09

# ── Environment Defaults ──────────────────────────────────────────────────────
# These are non-secret configuration defaults.
# Sensitive values (ANTHROPIC_API_KEY, DATABASE_URL) are injected at runtime
# by ECS task definition from AWS Secrets Manager.
ENV LOG_LEVEL=WARNING
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV STREAMLIT_SERVER_PORT=8509
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true

# ── Health Check ──────────────────────────────────────────────────────────────
# ECS uses this to determine if the container is healthy.
# Streamlit's health endpoint returns 200 when the app is running.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8509/_stcore/health')" || exit 1

# ── Expose Port ───────────────────────────────────────────────────────────────
EXPOSE 8509

# ── Entry Point ───────────────────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", "--server.port=8509", "--server.address=0.0.0.0"]
