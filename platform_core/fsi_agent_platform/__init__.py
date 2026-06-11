"""FSI Agent Platform — shared production primitives for all 12 agents.

Modules:
    llm_factory   get_llm(role) — Anthropic (default) / Bedrock+Guardrails
    auth          verify_jwt, require_role, record_reviewer_identity
    secrets       get_secret — Secrets Manager with env fallback
    pii           mask(text) — layered regex + Luhn + optional ML engine
    tracing       traced_node — OTel span per graph node, no-op fallback

Vendored persistence (agent/persistence.py in each agent) is the durability
layer; this package is the shared everything-else. Roadmap: fold persistence
in here once agents adopt a shared-install deployment model.
"""
from fsi_agent_platform.llm_factory import get_llm  # noqa: F401
from fsi_agent_platform.pii import luhn_valid, mask  # noqa: F401
from fsi_agent_platform.secrets import get_secret  # noqa: F401
from fsi_agent_platform.tracing import traced_node  # noqa: F401
