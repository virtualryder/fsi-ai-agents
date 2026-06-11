"""
Prompt version registry — Rec 6.

Prompts ARE model configuration under SR 11-7: a prompt change can move SAR
narrative content, adverse-action reasons, or dispute analysis without any
code diff standing out in review. This registry makes prompt changes
deliberate and auditable:

  * `build_manifest()` hashes every agent's prompts.py (SHA-256 of the
    normalized file) into governance/prompt_manifest.json.
  * tests/test_prompt_manifest.py FAILS CI when any prompts.py differs from
    the recorded hash — the change must ship with a manifest update
    (`python -m governance.prompt_registry --update`), which makes the
    version bump explicit in the diff and reviewable as a model change.

This is the same pattern as a lockfile: the gate isn't that prompts can't
change, it's that they can't change silently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).resolve().parent / "prompt_manifest.json"


def _normalize(text: str) -> bytes:
    # Hash content, not line endings
    return text.replace("\r\n", "\n").encode("utf-8")


def discover_prompt_files() -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for p in sorted(REPO_ROOT.glob("[01][0-9]-*/agent/prompts.py")):
        out[p.parent.parent.name] = p
    return out


def build_manifest() -> Dict[str, Dict[str, str]]:
    entries: Dict[str, Dict[str, str]] = {}
    for agent, path in discover_prompt_files().items():
        digest = hashlib.sha256(_normalize(path.read_text())).hexdigest()
        entries[agent] = {"file": str(path.relative_to(REPO_ROOT)), "sha256": digest}
    return entries


def load_manifest() -> Dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text())


def write_manifest() -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Prompt content hashes. A CI failure against this file means a prompt "
            "changed without an explicit version bump — update via "
            "`python -m governance.prompt_registry --update` IN THE SAME PR, so the "
            "prompt change is visible and reviewable as a model-configuration change."
        ),
        "prompts": build_manifest(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")


def diff_against_manifest() -> Dict[str, str]:
    """Return {agent: reason} for every drifted/missing entry. Empty == clean."""
    recorded = load_manifest().get("prompts", {})
    current = build_manifest()
    problems: Dict[str, str] = {}
    for agent, entry in current.items():
        if agent not in recorded:
            problems[agent] = "not in manifest (new prompt file — run --update)"
        elif recorded[agent]["sha256"] != entry["sha256"]:
            problems[agent] = "prompt content changed without manifest update"
    for agent in recorded:
        if agent not in current:
            problems[agent] = "in manifest but prompts.py missing"
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="re-record all prompt hashes")
    args = parser.parse_args()
    if args.update:
        write_manifest()
        print(f"manifest updated: {MANIFEST_PATH}")
    else:
        problems = diff_against_manifest()
        if problems:
            for agent, why in sorted(problems.items()):
                print(f"DRIFT {agent}: {why}")
            raise SystemExit(1)
        print("prompt manifest clean")
