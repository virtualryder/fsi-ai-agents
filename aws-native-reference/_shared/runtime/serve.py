"""
AgentCore Runtime / Fargate HTTP server (Phase 3 deploy kit).

Implements the Amazon Bedrock AgentCore Runtime container contract:
  * POST /invocations  — JSON in, JSON out; runs the selected agent's graph.
  * GET  /ping         — health; returns {"status": "Healthy"}.
  * listens on port 8080.

The same container also runs on Amazon ECS Fargate or locally (it is a plain
HTTP server). The agent this container serves is chosen by the AGENT env var
(e.g. AGENT=01-financial-crime-investigation), so one image + one config per
agent folder under aws-native-reference/.

Run locally:   AGENT=09-document-intelligence uvicorn serve:app --host 0.0.0.0 --port 8080
Health:        curl http://localhost:8080/ping
Invoke:        curl -XPOST http://localhost:8080/invocations -H 'content-type: application/json' -d '{...}'
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request

import handler

app = FastAPI(title=f"FSI Agent Runtime [{os.getenv('AGENT', 'unset')}]")


@app.get("/ping")
def ping():
    return handler.ping()


@app.post("/invocations")
async def invocations(request: Request):
    payload = await request.json()
    # AGENT env selects the agent; a request may override via {"agent": "..."}.
    agent_key = payload.get("agent") or handler.current_agent_key()
    body = payload.get("input", payload)
    return handler.handle_invocation(body, agent_key=agent_key)
