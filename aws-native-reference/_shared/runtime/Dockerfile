# Shared base image for any FSI agent — Amazon Bedrock AgentCore Runtime contract.
# AgentCore Runtime REQUIRES linux/arm64 (AWS Graviton). Build with:
#   docker buildx build --platform linux/arm64 ...
# The per-agent Dockerfile (aws-native-reference/<agent>/Dockerfile) builds FROM
# this base, copies its agent package, installs that agent's requirements, and
# sets the AGENT env var.
FROM --platform=linux/arm64 python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Server deps (the agent's own requirements are added by the per-agent Dockerfile)
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29"

# Shared runtime (handler + server). The platform library and the agent package
# are layered in by the per-agent Dockerfile.
COPY _shared/runtime/handler.py _shared/runtime/serve.py /app/

EXPOSE 8080
# AGENT is set by the per-agent image. LLM_PROVIDER=bedrock keeps inference in-account.
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
