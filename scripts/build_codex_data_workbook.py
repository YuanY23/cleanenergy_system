"""Build the human-readable annual-data workbook from one verified CSV.

This compatibility wrapper intentionally has no download or cache logic.  It
only invokes the artifact-tool workbook builder against an explicit processed
file from ``data/processed`` and writes beneath ``artifacts/runs``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUILDER = Path(__file__).with_name("build_annual_data_workbook.mjs")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def build_workbook(
    *,
    annual_csv: str | Path,
    source_registry_csv: str | Path,
    output_xlsx: str | Path,
    node_executable: str | Path,
    node_modules: str | Path,
) -> Path:
    annual = Path(annual_csv).resolve()
    sources = Path(source_registry_csv).resolve()
    output = Path(output_xlsx).resolve()
    processed_root = (ROOT / "data" / "processed").resolve()
    metadata_root = (ROOT / "data" / "metadata").resolve()
    artifacts_root = (ROOT / "artifacts" / "runs").resolve()
    if not annual.is_file() or not _inside(annual, processed_root):
        raise ValueError("annual CSV must be an existing file under data/processed")
    if not sources.is_file() or not _inside(sources, metadata_root):
        raise ValueError("source registry must be under data/metadata")
    if not _inside(output, artifacts_root):
        raise ValueError("workbook output must be under artifacts/runs")

    runtime_modules = Path(node_modules).resolve()
    if not runtime_modules.is_dir():
        raise RuntimeError("the provided artifact-tool node_modules directory is missing")
    node = Path(node_executable).resolve()
    if not node.is_file():
        raise RuntimeError("the provided Node.js executable is missing")

    with tempfile.TemporaryDirectory(prefix="zero-carbon-workbook-") as temp_name:
        temp_dir = Path(temp_name)
        shutil.copy2(BUILDER, temp_dir / BUILDER.name)
        os.symlink(runtime_modules, temp_dir / "node_modules", target_is_directory=True)
        subprocess.run(
            [
                str(node),
                str(temp_dir / BUILDER.name),
                "--annual",
                str(annual),
                "--sources",
                str(sources),
                "--output",
                str(output),
            ],
            cwd=temp_dir,
            check=True,
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从本次8784小时处理数据生成审计工作簿；不下载、不读取历史缓存。"
    )
    parser.add_argument("--annual", required=True)
    parser.add_argument(
        "--sources", default=str(ROOT / "data" / "metadata" / "source_registry.csv")
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--node", default=os.environ.get("CODEX_NODE"))
    parser.add_argument(
        "--node-modules", default=os.environ.get("CODEX_NODE_MODULES")
    )
    args = parser.parse_args()
    if not args.node or not args.node_modules:
        parser.error("provide --node and --node-modules (or CODEX_NODE/CODEX_NODE_MODULES)")
    result = build_workbook(
        annual_csv=args.annual,
        source_registry_csv=args.sources,
        output_xlsx=args.output,
        node_executable=args.node,
        node_modules=args.node_modules,
    )
    print(result)


if __name__ == "__main__":
    main()
