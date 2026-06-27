import subprocess
import sys
import os
from pathlib import Path


def test_module_help_works_without_playwright():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "gmsg", "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "Google Messages CLI" in result.stdout
    assert "gmsg send" in result.stdout
