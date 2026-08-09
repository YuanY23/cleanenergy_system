"""Run the manifest-pinned formal 2024 study."""

from __future__ import annotations

import argparse
from pathlib import Path

from zero_carbon_park.formal_study import run_formal_study


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    outputs = run_formal_study(args.manifest, repo_root=args.repo_root)
    print(outputs["completion"])


if __name__ == "__main__":
    main()
