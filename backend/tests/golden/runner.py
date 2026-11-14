"""Prototip düzeneğini (Node) çalıştırır. Node yoksa golden testler atlanır."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.station.prototype import PROTOTYPE_HTML

HARNESS = Path(__file__).with_name("prototype_harness.mjs")
NODE = shutil.which("node")
requires_node = pytest.mark.skipif(NODE is None, reason="golden testler için Node.js gerekli")


def run_prototype(spec: dict) -> dict:
    proc = subprocess.run(
        [NODE, str(HARNESS), str(PROTOTYPE_HTML)],
        input=json.dumps(spec).encode("utf-8"),
        capture_output=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
    return json.loads(proc.stdout.decode("utf-8"))
