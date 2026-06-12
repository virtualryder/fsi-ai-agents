"""Structural validation of the Step Functions state machine."""
import json, os
ASL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "stepfunctions", "financial_crime_investigation.asl.json")


def _load():
    return json.load(open(ASL))


def test_valid_json_startat():
    d = _load(); assert d["StartAt"] in d["States"]


def test_all_transitions_resolve():
    d = _load(); names = set(d["States"])
    for n, s in d["States"].items():
        if "Next" in s: assert s["Next"] in names
        for c in s.get("Choices", []): assert c["Next"] in names
        if s.get("Default"): assert s["Default"] in names


def test_hitl_gate_waitfortasktoken():
    g = _load()["States"]["HumanReviewGate"]
    assert g["Resource"].endswith(".waitForTaskToken")
    assert g["Parameters"]["Payload"]["task_token.$"] == "$$.Task.Token"


def test_choice_has_default_and_sar_path():
    c = _load()["States"]["DispositionChoice"]
    assert c["Default"] == "CloseCase"
    targets = {ch["Next"] for ch in c["Choices"]}
    assert {"GenerateSAR", "HumanReviewGate"} <= targets


def test_sar_path_passes_through_human_gate():
    assert _load()["States"]["GenerateSAR"]["Next"] == "HumanReviewGate"


def test_one_terminal_state():
    d = _load(); assert [n for n, s in d["States"].items() if s.get("End")] == ["Finalize"]
