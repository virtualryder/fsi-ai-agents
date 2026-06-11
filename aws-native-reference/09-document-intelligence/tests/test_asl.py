"""Structural validation of the Step Functions state machine."""
import json
import os

ASL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "stepfunctions", "document_intelligence.asl.json")


def _load():
    with open(ASL_PATH) as f:
        return json.load(f)


def test_asl_is_valid_json_with_states():
    d = _load()
    assert d["StartAt"] in d["States"]


def test_all_transitions_reference_defined_states():
    d = _load()
    names = set(d["States"])
    for name, s in d["States"].items():
        if "Next" in s:
            assert s["Next"] in names, f"{name}.Next -> {s['Next']} undefined"
        for ch in s.get("Choices", []):
            assert ch["Next"] in names, f"{name} choice -> {ch['Next']} undefined"
        if s.get("Default"):
            assert s["Default"] in names


def test_choice_has_default():
    d = _load()
    choice = d["States"]["DispositionChoice"]
    assert choice["Type"] == "Choice" and "Default" in choice


def test_hitl_gate_uses_wait_for_task_token():
    d = _load()
    gate = d["States"]["HumanReviewGate"]
    assert gate["Resource"].endswith(".waitForTaskToken")
    # The task token must be passed from the context object.
    assert gate["Parameters"]["Payload"]["task_token.$"] == "$$.Task.Token"


def test_exactly_one_terminal_state():
    d = _load()
    ends = [n for n, s in d["States"].items() if s.get("End")]
    assert ends == ["Finalize"]


def test_lambda_task_states_unwrap_payload():
    d = _load()
    for name, s in d["States"].items():
        if s.get("Resource") == "arn:aws:states:::lambda:invoke":
            assert s.get("OutputPath") == "$.Payload", f"{name} should unwrap $.Payload"
