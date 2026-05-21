#!/usr/bin/env python
"""Run all visualization and report generation."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], description: str) -> bool:
    """Run command and report result."""
    print(f"\n{'='*60}")
    print(f"📊 {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, cwd=str(Path(__file__).parent), check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        return False
    except FileNotFoundError as e:
        print(f"⚠️  {description} skipped: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("🎨 AcneLLM Dataset Visualization Pipeline")
    print("="*60)

    root = Path(__file__).parent

    # Step 1: Generate PNG charts
    success = run_cmd(
        [sys.executable, "plot_datasets.py"],
        "Generating PNG charts",
    )

    if not success:
        print("\n⚠️  Failed to generate PNG charts (might be missing seaborn/matplotlib)")
        print("   Install: pip install matplotlib seaborn")
        return

    # Step 2: Generate HTML report
    success = run_cmd(
        [sys.executable, "generate_report.py"],
        "Generating HTML report",
    )

    if not success:
        print("\n⚠️  Failed to generate HTML report")
        return

    # Summary
    print("\n" + "="*60)
    print("✅ Visualization Complete!")
    print("="*60)
    print("\n📁 Generated files:")
    for file in sorted(root.glob("*.png")):
        print(f"   - {file.name}")
    for file in ["report.html", "README.md"]:
        fpath = root / file
        if fpath.exists():
            print(f"   - {file.name}")

    html_path = root / "report.html"
    if html_path.exists():
        print(f"\n🌐 Open report in browser:")
        print(f"   file://{html_path.absolute()}")


if __name__ == "__main__":
    main()
