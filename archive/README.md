# 历史成果隔离归档

本目录只保存旧版本生成的数据、图表、结果和项目文档，用于追溯历史，不属于当前零碳园区研究的正式输入或正式结论。

- `legacy_generated/2026-08-09/outputs/`：原 `outputs/`。
- `legacy_generated/2026-08-09/results_v1/`：原 `results_v1/`。
- `legacy_generated/2026-08-09/data_processed/`：原 `data/processed/` 历史处理数据。
- `legacy_docs/2026-08-09/`：依赖旧结果、旧场景叙事的历史总结文档。

正式运行只允许读取运行清单显式列出的 `data/raw/` 和重新构建的 `data/processed/` 文件，并校验 SHA256。正式成果只写入 `artifacts/runs/<run_id>/`；质量门通过前不得创建或更新 `artifacts/latest.json`。

归档日期：2026-08-09。迁移为可恢复操作，未删除历史文件。
