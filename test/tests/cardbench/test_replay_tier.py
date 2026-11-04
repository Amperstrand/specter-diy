"""Hardware-free tier: deterministic vector replay of the full 6-story session.

Runs the bench suite as a subprocess against the committed vector capture
(USCARD_DETERMINISTIC session) - exit 0 + 6/6 proves the whole client stack
byte-for-byte against recorded card answers, with the drift detector armed.
"""
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
VECTOR = os.path.join(os.path.dirname(__file__), "vectors", "cardman-full-session.jsonl")


def test_replay_full_session():
    if not os.path.exists(VECTOR):
        import pytest
        pytest.skip("vector session not committed")
    env = dict(os.environ)
    env.update({
        "USCARD_BACKEND": "replay",
        "USCARD_TRANSCRIPT": VECTOR,
    })
    proc = subprocess.run(
        ["python3", "suite.py"], cwd=REPO, env=env,
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "6/6 stories green" in proc.stdout, proc.stdout
