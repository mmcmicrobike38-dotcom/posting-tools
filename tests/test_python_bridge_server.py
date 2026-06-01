from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_python_bridge_server_handles_multiple_requests():
    script = Path("scripts/python_bridge.py")
    process = subprocess.Popen(
        [sys.executable, str(script), "--server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        for _ in range(2):
            process.stdin.write(json.dumps({"command": "ping"}) + "\n")
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            assert response == {"ok": True, "result": {"ok": True}}

        process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response == {"ok": True, "result": {"shutdown": True}}
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
