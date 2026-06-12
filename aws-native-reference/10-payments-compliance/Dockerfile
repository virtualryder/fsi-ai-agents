# Payments Compliance — AWS-native runtime container (lift the LangGraph agent onto AWS).
# Implements the Amazon Bedrock AgentCore Runtime contract (/invocations, /ping,
# port 8080) and also runs on ECS Fargate or locally. Build from the REPO ROOT:
#   docker buildx build --platform linux/arm64 \
#     -f aws-native-reference/10-payments-compliance/Dockerfile -t <ecr-repo>:10-payments-compliance .
FROM --platform=linux/arm64 python:3.12-slim

ENV PYTHONUNBUFFERED=1 PORT=8080 \
    AGENT=10-payments-compliance \
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
COPY 10-payments-compliance-agent/ /app/agents/10-payments-compliance-agent/
RUN pip install --no-cache-dir -r /app/agents/10-payments-compliance-agent/requirements.txt

EXPOSE 8080
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
