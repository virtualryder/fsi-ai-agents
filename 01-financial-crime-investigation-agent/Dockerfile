# Dockerfile
# Financial Crime Investigation Agent
# Python 3.11-slim, non-root user, Railway-compatible

FROM python:3.11-slim

# Set metadata labels
LABEL maintainer="compliance-ai@yourbank.com"
LABEL description="Financial Crime Investigation Agent — AI-Powered AML Platform"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Install system dependencies
# libpq-dev: required for psycopg2-binary (PostgreSQL)
# curl: for healthcheck
RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
# Running as root in production is a security vulnerability
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

# Copy requirements first to leverage Docker layer caching
# This means pip install only reruns if requirements.txt changes
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Create Streamlit config directory and configure for production
RUN mkdir -p /app/.streamlit && chown -R appuser:appuser /app/.streamlit

# Streamlit configuration for headless server operation
RUN cat > /app/.streamlit/config.toml << EOF
[server]
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false

[logger]
level = "info"
EOF

# Switch to non-root user
USER appuser

# Expose port (Railway overrides this with $PORT env var)
EXPOSE 8501

# Health check — Streamlit's built-in health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8501}/_stcore/health || exit 1

# Start command
# Railway passes $PORT env var — we use it directly
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true"]
