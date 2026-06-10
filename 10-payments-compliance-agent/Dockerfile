# ── Payments Compliance Agent — Dockerfile ────────────────────────────────────
#
# Multi-stage build for production deployment.
#
# SECURITY DESIGN DECISIONS:
#
# 1. Multi-stage build: Builder stage installs dependencies. Final stage
#    copies only the installed packages — no build tools, no pip, no
#    package cache in the final image. Reduces attack surface.
#
# 2. Non-root user (uid=1000): The application runs as user 'appuser',
#    not root. If the container is compromised, the attacker does not
#    have root privileges inside the container.
#
# 3. Read-only filesystem: --read-only flag in docker run prevents the
#    container process from writing to the filesystem. The application
#    does not need filesystem write access at runtime.
#    Note: /tmp must be a tmpfs mount if the app needs temporary files.
#
# 4. No secrets in image: API keys and database credentials are injected
#    at runtime via environment variables from AWS Secrets Manager.
#    Never bake secrets into the image layer.
#
# 5. Minimal base image: python:3.11-slim (Debian slim) vs. full Python
#    image reduces the number of packages that could have vulnerabilities.

# ── Stage 1: Builder ──────────────────────────────────────────────────────────

FROM python:3.11-slim AS builder

WORKDIR /app

# Copy only requirements first (layer caching — only re-installs if requirements change)
COPY requirements.txt .

# Install dependencies to a custom location for clean copy to final stage
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Final Image ──────────────────────────────────────────────────────

FROM python:3.11-slim

# Create non-root user
# uid=1000 matches common Linux user IDs — avoids permission conflicts
# with mounted volumes in development
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application code
# Note: .dockerignore should exclude .env, __pycache__, .git, tests/
COPY --chown=appuser:appuser . .

# Create directories needed at runtime (Streamlit cache)
RUN mkdir -p /tmp/streamlit && chown appuser:appuser /tmp/streamlit

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8510

# Health check: verify Streamlit is responding
# Adjust the path if your deployment uses a reverse proxy prefix
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8510/_stcore/health')" || exit 1

# Run the Streamlit dashboard
# --server.port: listen on 8510
# --server.address=0.0.0.0: accept connections from outside the container
# --server.headless=true: required for containerized deployment (no browser launch)
# --browser.gatherUsageStats=false: disable telemetry
CMD ["streamlit", "run", "app.py", \
     "--server.port=8510", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
