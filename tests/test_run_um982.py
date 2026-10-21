"""The root launcher must work without PYTHONPATH or an installed package."""

import os
import subprocess
import sys

LAUNCHER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "run_um982.py",
)


def test_launcher_runs_outside_repo_without_pythonpath(tmp_path):
    # A child process is required: pytest's own pythonpath setting already
    # puts src/ on sys.path, which would hide a broken launcher.
    child_env = dict(os.environ)
    child_env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, LAUNCHER_PATH, "--help"],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--port" in completed.stdout
