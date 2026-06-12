import json, os
ASL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "stepfunctions", "payments_compliance.asl.json")


def _load(): return json.load(open(ASL))
def test_valid_startat(): d=_load(); assert d["StartAt"] in d["States"]
def test_transitions_resolve():
    d=_load(); names=set(d["States"])
    for n,s in d["States"].items():
        if "Next" in s: assert s["Next"] in names
        for c in s.get("Choices",[]): assert c["Next"] in names
        if s.get("Default"): assert s["Default"] in names
def test_hitl_waitfortasktoken():
    g=_load()["States"]["HumanReviewGate"]
    assert g["Resource"].endswith(".waitForTaskToken")
    assert g["Parameters"]["Payload"]["task_token.$"]=="$$.Task.Token"
def test_choice_default_drafts_notice():
    assert _load()["States"]["DispositionChoice"]["Default"]=="DraftNotice"
def test_one_terminal(): d=_load(); assert [n for n,s in d["States"].items() if s.get("End")]==["Finalize"]
