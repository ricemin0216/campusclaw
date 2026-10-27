"""Run the MCP API regression suite and write a local HTML report.

The generated report.html is intentionally ignored by Git.
"""

from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(__file__).with_name("report.html")


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_mcp.py",
            "-q",
            "--basetemp",
            str(ROOT / "tmp" / "apitest-pytest"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout + completed.stderr
    REPORT.write_text(
        "<!doctype html><meta charset=utf-8><title>MCP API 测试报告</title>"
        f"<h1>MCP API 测试报告</h1><p>退出码：{completed.returncode}</p><pre>{html.escape(output)}</pre>",
        encoding="utf-8",
    )
    print(output, end="")
    print(f"HTML report: {REPORT}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
