from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_all_python_services_share_one_backend_image() -> None:
    """A backend rebuild must not leave Worker or Scheduler on stale code."""

    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    repository_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment.setdefault("CODEX_CLI_VERSION", "0.146.0")
    rendered = subprocess.run(
        ["docker", "compose", "--profile", "integrations", "config", "--format", "json"],
        cwd=repository_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(rendered.stdout)["services"]
    backend_services = (
        "api",
        "worker",
        "scheduler",
        "feishu-connector",
        "file-indexer",
    )
    images = {name: services[name].get("image") for name in backend_services}

    assert all(images.values()), images
    assert len(set(images.values())) == 1, images
