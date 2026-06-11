"""Platform layer tests — these run in CI (job: platform) without API keys or AWS."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from fsi_agent_platform import auth, llm_factory, pii, secrets, tracing


# ── llm_factory ───────────────────────────────────────────────────────────────
class TestLLMFactory:
    def test_default_provider_is_anthropic(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        assert llm_factory.provider() == "anthropic"

    def test_anthropic_models_tiering(self):
        assert "sonnet" in llm_factory.ANTHROPIC_MODELS["narrative"]
        assert "haiku" in llm_factory.ANTHROPIC_MODELS["fast"]

    def test_anthropic_path_constructs_chat_anthropic(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        with patch("langchain_anthropic.ChatAnthropic") as mock_cls:
            llm_factory.get_llm("fast", temperature=0.2)
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["model"] == llm_factory.ANTHROPIC_MODELS["fast"]
            assert kwargs["temperature"] == 0.2

    def test_bedrock_path_includes_guardrail_when_configured(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-abc123")
        fake_mod = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": fake_mod}):
            llm_factory.get_llm("narrative")
            kwargs = fake_mod.ChatBedrockConverse.call_args.kwargs
            assert kwargs["guardrail_config"]["guardrailIdentifier"] == "gr-abc123"
            assert kwargs["model"] == llm_factory.BEDROCK_MODELS["narrative"]

    def test_bedrock_without_guardrail_warns_but_works(self, monkeypatch, caplog):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
        fake_mod = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": fake_mod}):
            with caplog.at_level("WARNING"):
                llm_factory.get_llm("fast")
        assert any("Guardrails" in r.message for r in caplog.records)
        assert "guardrail_config" not in fake_mod.ChatBedrockConverse.call_args.kwargs


# ── auth ──────────────────────────────────────────────────────────────────────
class TestAuth:
    def test_missing_token_fails_closed(self):
        @auth.require_role("BSA_OFFICER")
        def approve(case_id, *, claims):
            return "approved"

        with pytest.raises(auth.AuthError, match="missing bearer token"):
            approve("CASE-1")

    def test_unconfigured_issuer_fails_closed(self, monkeypatch):
        monkeypatch.delenv("AUTH_ISSUER", raising=False)
        monkeypatch.delenv("AUTH_DISABLED", raising=False)
        with pytest.raises(auth.AuthError):
            auth.verify_jwt("any.jwt.token")

    def test_insufficient_role_denied(self, monkeypatch):
        monkeypatch.delenv("AUTH_DISABLED", raising=False)

        @auth.require_role("BSA_OFFICER")
        def approve(case_id, *, claims):  # pragma: no cover — must not run
            return "approved"

        with patch.object(auth, "verify_jwt", return_value={"sub": "u1", "custom:bsa_role": "READ_ONLY"}):
            with pytest.raises(auth.AuthError, match="insufficient role"):
                approve("CASE-1", token="x.y.z")

    def test_matching_role_allowed_and_claims_injected(self, monkeypatch):
        @auth.require_role("BSA_OFFICER", "SENIOR_ANALYST")
        def approve(case_id, *, claims):
            return claims["sub"]

        with patch.object(auth, "verify_jwt", return_value={"sub": "officer-9", "custom:bsa_role": "BSA_OFFICER"}):
            assert approve("CASE-1", token="x.y.z") == "officer-9"

    def test_roles_from_comma_separated_claim(self):
        roles = auth.roles_from_claims({"custom:bsa_role": "BSA_OFFICER, AUDITOR"})
        assert set(roles) == {"BSA_OFFICER", "AUDITOR"}

    def test_reviewer_identity_binding(self):
        state = {"case_id": "C-1"}
        out = auth.record_reviewer_identity(
            state, {"sub": "okta|u42", "email": "officer@bank.example", "custom:bsa_role": "BSA_OFFICER"}
        )
        assert out["reviewer_id"] == "okta|u42"
        assert out["reviewer_identity_verified"] is True
        assert "BSA_OFFICER" in out["reviewer_roles"]

    def test_demo_mode_is_loud_but_permitted(self, monkeypatch, caplog):
        monkeypatch.setenv("AUTH_DISABLED", "true")
        with caplog.at_level("WARNING"):
            claims = auth.verify_jwt("anything")
        assert claims["demo_mode"] is True
        assert any("BYPASSED" in r.message for r in caplog.records)


# ── pii ───────────────────────────────────────────────────────────────────────
class TestPII:
    def test_ssn_masked(self):
        masked, types = pii.mask("Borrower SSN: 123-45-6789.")
        assert "123-45-6789" not in masked and "SSN" in types

    def test_itin_masked(self):
        masked, types = pii.mask("Taxpayer ID 912-93-1234 on file.")
        assert "912-93-1234" not in masked and "SSN" in types

    def test_luhn_valid_card_masked(self):
        masked, types = pii.mask("Card: 4111 1111 1111 1111 charged.")
        assert "4111" not in masked and "CREDIT_CARD" in types

    def test_luhn_invalid_digits_left_alone(self):
        ref = "4111111111111112"  # fails Luhn — a reference number, not a PAN
        masked, types = pii.mask(f"Wire ref {ref} received.")
        assert ref in masked and "CREDIT_CARD" not in types

    def test_email_phone_iban(self):
        masked, types = pii.mask("Contact a@b.com / 617-555-1212, IBAN DE89370400440532013000.")
        for t in ("EMAIL", "PHONE_US", "IBAN"):
            assert t in types
        assert "a@b.com" not in masked and "DE8937" not in masked

    def test_labeled_account_and_routing(self):
        masked, types = pii.mask("Account #12345678 routing 021000021.")
        assert "12345678" not in masked and "ACCOUNT_NUMBER" in types

    def test_empty_text(self):
        assert pii.mask("") == ("", [])


# ── secrets ───────────────────────────────────────────────────────────────────
class TestSecrets:
    def test_env_fallback(self, monkeypatch):
        monkeypatch.delenv("SECRETS_MANAGER_PREFIX", raising=False)
        monkeypatch.setenv("MY_TEST_SECRET", "from-env")
        assert secrets.get_secret("MY_TEST_SECRET") == "from-env"

    def test_default_when_absent(self, monkeypatch):
        monkeypatch.delenv("SECRETS_MANAGER_PREFIX", raising=False)
        monkeypatch.delenv("NOPE_SECRET", raising=False)
        assert secrets.get_secret("NOPE_SECRET", default="dflt") == "dflt"

    def test_secrets_manager_failure_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("SECRETS_MANAGER_PREFIX", "fsi/agents")
        monkeypatch.setenv("FALLBACK_KEY", "env-value")
        secrets._cache.clear()
        fake_boto = MagicMock()
        fake_boto.client.return_value.get_secret_value.side_effect = RuntimeError("no creds")
        with patch.dict("sys.modules", {"boto3": fake_boto}):
            assert secrets.get_secret("FALLBACK_KEY") == "env-value"


# ── tracing ───────────────────────────────────────────────────────────────────
class TestTracing:
    def test_noop_passthrough_without_otel(self, monkeypatch):
        monkeypatch.setenv("OTEL_DISABLED", "true")

        def node(state):
            return {"ok": True, "errors": []}

        wrapped = tracing.traced_node(node)
        assert wrapped is node  # zero-cost when disabled
        assert wrapped({"case_id": "C-1"}) == {"ok": True, "errors": []}

    def test_case_id_extraction_priority(self):
        assert tracing._case_id({"alert_id": "A-7"}) == "A-7"
        assert tracing._case_id({}) == "unknown"


# ── PII boundary enforcement (Phase 1.4) ──────────────────────────────────────
class TestPIIBoundary:
    def test_mask_obj_masks_nested_strings(self):
        record = {
            "case_id": "C-1",
            "subject": {"name_note": "SSN 123-45-6789", "age": 41, "flagged": True},
            "events": ["wire to a@b.com", "ref 9999"],
        }
        masked, types = pii.mask_obj(record)
        flat = repr(masked)
        assert "123-45-6789" not in flat and "a@b.com" not in flat
        assert "SSN" in types and "EMAIL" in types
        # structure + non-string scalars preserved
        assert masked["subject"]["age"] == 41 and masked["subject"]["flagged"] is True
        assert masked["case_id"] == "C-1"

    def test_scrub_for_persistence_blocks_raw_pii(self):
        audit_entry = {
            "action": "SUPPRESS",
            "details": {"narrative": "Customer SSN 987-65-4321, card 4111 1111 1111 1111"},
        }
        safe = pii.scrub_for_persistence(audit_entry)
        blob = repr(safe)
        assert "987-65-4321" not in blob
        assert "4111 1111 1111 1111" not in blob and "4111111111111111" not in blob

    def test_scrub_is_idempotent_and_lossless_for_clean_records(self):
        clean = {"x": 1, "y": ["ok", "fine"], "z": None}
        assert pii.scrub_for_persistence(clean) == clean


# ── secrets: fail-closed (Phase 1.5) ──────────────────────────────────────────
class TestSecretsFailClosed:
    def _failing_boto(self):
        fake_boto = MagicMock()
        fake_boto.client.return_value.get_secret_value.side_effect = RuntimeError("no creds")
        return fake_boto

    def test_fail_closed_flag_raises_instead_of_env_fallback(self, monkeypatch):
        monkeypatch.setenv("SECRETS_MANAGER_PREFIX", "fsi/agents")
        monkeypatch.setenv("SECRETS_FAIL_CLOSED", "true")
        monkeypatch.setenv("FALLBACK_KEY", "env-value")
        secrets._cache.clear()
        with patch.dict("sys.modules", {"boto3": self._failing_boto()}):
            with pytest.raises(secrets.SecretsUnavailableError):
                secrets.get_secret("FALLBACK_KEY")

    def test_production_environment_fails_closed(self, monkeypatch):
        monkeypatch.setenv("SECRETS_MANAGER_PREFIX", "fsi/agents")
        monkeypatch.delenv("SECRETS_FAIL_CLOSED", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("FALLBACK_KEY", "env-value")
        secrets._cache.clear()
        with patch.dict("sys.modules", {"boto3": self._failing_boto()}):
            with pytest.raises(secrets.SecretsUnavailableError):
                secrets.get_secret("FALLBACK_KEY")

    def test_dev_still_falls_back(self, monkeypatch):
        monkeypatch.setenv("SECRETS_MANAGER_PREFIX", "fsi/agents")
        monkeypatch.delenv("SECRETS_FAIL_CLOSED", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("FALLBACK_KEY", "env-value")
        secrets._cache.clear()
        with patch.dict("sys.modules", {"boto3": self._failing_boto()}):
            assert secrets.get_secret("FALLBACK_KEY") == "env-value"


# ── llm_factory: guardrail required in production (Phase 1.5) ──────────────────
class TestGuardrailRequiredInProd:
    def test_production_without_guardrail_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        fake_mod = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": fake_mod}):
            with pytest.raises(RuntimeError):
                llm_factory.get_llm("narrative")

    def test_require_flag_without_guardrail_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("REQUIRE_BEDROCK_GUARDRAIL", "true")
        fake_mod = MagicMock()
        with patch.dict("sys.modules", {"langchain_aws": fake_mod}):
            with pytest.raises(RuntimeError):
                llm_factory.get_llm("fast")
