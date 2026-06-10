# Agent 12 — Collections & Recovery Agent
# Multi-stage Docker build. Non-root user, read-only filesystem.
# Consumer PII (account numbers, SSNs) masked at intake — never written to container FS.

FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

# Non-root user (UID 1000) — principle of least privilege
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --no-create-home appuser

# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appgroup . .

# Run as non-root
USER appuser

# Streamlit port
EXPOSE 8512

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8512/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.port=8512", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
