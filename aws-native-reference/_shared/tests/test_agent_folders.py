"""
Structural test: every agent in the registry has a complete, consistent
per-agent deployment folder under aws-native-reference/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import handler

ANR = Path(__file__).resolve().parents[2]          # aws-native-reference/
REQUIRED = ["Dockerfile", "DEPLOY.md", "deploy.auto.tfvars", "sample_input.json"]


@pytest.mark.parametrize("key", list(handler.AGENT_REGISTRY))
def test_folder_exists_with_required_files(key):
    folder = ANR / key
    assert folder.is_dir(), f"missing folder {folder}"
    for f in REQUIRED:
        assert (folder / f).is_file(), f"{key} missing {f}"


@pytest.mark.parametrize("key", list(handler.AGENT_REGISTRY))
def test_dockerfile_targets_this_agent(key):
    df = (ANR / key / "Dockerfile").read_text()
    assert f"AGENT={key}" in df, f"{key} Dockerfile does not set AGENT={key}"
    assert "linux/arm64" in df, f"{key} Dockerfile is not ARM64 (AgentCore requires it)"
    src_dir = handler.AGENT_REGISTRY[key][0]
    assert src_dir in df, f"{key} Dockerfile does not copy its source dir {src_dir}"


@pytest.mark.parametrize("key", list(handler.AGENT_REGISTRY))
def test_sample_input_is_valid_json(key):
    json.loads((ANR / key / "sample_input.json").read_text())


def test_all_12_folders_present():
    keys = {p.name for p in ANR.iterdir() if p.is_dir() and p.name[:2].isdigit()}
    assert keys == set(handler.AGENT_REGISTRY), f"folder set != registry: {keys ^ set(handler.AGENT_REGISTRY)}"
