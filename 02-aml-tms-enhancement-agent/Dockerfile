FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Streamlit config
RUN mkdir -p /root/.streamlit && cat > /root/.streamlit/config.toml << 'EOF'
[server]
headless = true
enableCORS = false
enableXsrfProtection = false

[theme]
base = "dark"
EOF

EXPOSE 8501

# Railway injects $PORT — the sh wrapper ensures variable expansion at runtime
CMD sh -c 'streamlit run app.py --server.port "${PORT:-8501}" --server.address 0.0.0.0'
