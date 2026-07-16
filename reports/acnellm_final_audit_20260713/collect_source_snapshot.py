"""Collect read-only repository, service and installed-model audit metadata."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "source_snapshot.json"


def command(*args: str) -> str:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    modelfile = ROOT / "model" / "Modelfile"
    installed = command("ollama", "show", "--modelfile", "acnellm-v2-q4:latest")
    data = {
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "branch": command("git", "branch", "--show-current"),
        "head": command("git", "rev-parse", "HEAD"),
        "head_summary": command("git", "log", "-1", "--format=%h %s"),
        "status_short": command("git", "status", "--short"),
        "staged_source_stat": command(
            "git", "diff", "--cached", "--stat", "--", "src", "config", "model", "tests", "scripts", "docs"
        ),
        "backend_health": get_json("http://127.0.0.1:8000/api/v1/health"),
        "repo_modelfile_sha256": sha256(modelfile),
        "installed_model_modelfile": installed,
        "installed_has_new_system_contract": all(
            marker in installed
            for marker in (
                "Nguồn sự thật DUY NHẤT",
                "Không hướng dẫn tự nặn, tự chích",
                "CHỈ nêu tên guideline/nghiên cứu cụ thể",
            )
        ),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
