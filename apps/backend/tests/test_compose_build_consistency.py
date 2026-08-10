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
    compose_env = repository_root / ".env"
    created_compose_env = False
    try:
        with compose_env.open("x", encoding="utf-8") as target:
            target.write((repository_root / ".env.example").read_text(encoding="utf-8"))
    except FileExistsError:
        pass
    else:
        created_compose_env = True
    try:
        rendered = subprocess.run(
            ["docker", "compose", "--profile", "integrations", "config", "--format", "json"],
            cwd=repository_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        if created_compose_env:
            compose_env.unlink()
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
