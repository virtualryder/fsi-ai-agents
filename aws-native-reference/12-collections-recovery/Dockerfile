# Collections & Recovery — AWS-native runtime container (lift the LangGraph agent onto AWS).
# Implements the Amazon Bedrock AgentCore Runtime contract (/invocations, /ping,
# port 8080) and also runs on ECS Fargate or locally. Build from the REPO ROOT:
#   docker buildx build --platform linux/arm64 \
#     -f aws-native-reference/12-collections-recovery/Dockerfile -t <ecr-repo>:12-collections-recovery .
FROM --platform=linux/arm64 python:3.12-slim

ENV PYTHONUNBUFFERED=1 PORT=8080 \
    AGENT=12-collections-recovery \
    FSI_REPO_ROOT=/app/agents \
    LLM_PROVIDER=bedrock

WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29"

# Shared runtime (handler + server)
COPY aws-native-reference/_shared/runtime/handler.py aws-native-reference/_shared/runtime/serve.py /app/

# Shared platform (LLM factory w/ Bedrock+Guardrails, auth, PII, connectors, gateway)
COPY platform_core/ /app/platform_core/
RUN pip install --no-cache-dir /app/platform_core

# This agent's package + its dependencies
COPY 12-collections-recovery-agent/ /app/agents/12-collections-recovery-agent/
RUN pip install --no-cache-dir -r /app/agents/12-collections-recovery-agent/requirements.txt

EXPOSE 8080
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
