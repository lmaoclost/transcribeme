"""Slim image contract: api/beat/download boot without torch/faster-whisper/transformers.

The transcription worker runs on the ML image; everything else must import cleanly
on the slim image where those packages are absent.
"""

from __future__ import annotations

import subprocess
import sys

BLOCKED = ["faster_whisper", "torch", "transformers", "sentencepiece", "accelerate", "sacremoses"]

PROBE = """
import sys

class _Blocker:
    def find_module(self, name, path=None):
        if name.split(".")[0] in %r:
            return self
    def load_module(self, name):
        raise ImportError(f"blocked on slim image: {name}")

sys.meta_path.insert(0, _Blocker())
for m in list(sys.modules):
    if m.split(".")[0] in %r:
        del sys.modules[m]

import app.api
import app.download_processor
import app.celery_app
print("slim-boot-ok")
""" % (BLOCKED, BLOCKED)


def test_slim_boot_without_ml_deps():
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "slim-boot-ok" in proc.stdout, proc.stderr[-2000:]
