# 面向零碳工业园区的电—热—氢—储系统规划与韧性评估

本项目围绕能源央国企常见的“新能源规划—综合能源协同—全年运行校核—极端工况保供—能碳核算”工作链，构建园区级电、热、氢、储一体化规划模型。研究对象为公开园区尺度校准的合成算例，不是某个企业的 SCADA 实测项目，也不是交互式展示系统。

## 项目主线

1. 以 2024 年闰年 8784 小时为统一时间边界，使用 ERA5 气象、公开园区用能尺度和区域政策参数重构输入。
2. 对风光、电负荷、热负荷、氢负荷和电价进行标准化，选取 8/12/16 个真实代表日，强制保留峰荷、低风光等极端日期，并保存 366 天映射与跨期状态链接。
3. 用同一套 Pyomo 物理约束求解经济型、低碳型和韧性型容量方案，覆盖风光、电池、电解槽、储氢、燃料电池、热泵和燃气锅炉。
4. 固定规划容量，以 168 小时展望、24 小时提交的滚动窗口完成全年回放，传递电池 SOC 和储氢库存，检查逐时能量平衡、容量越限和正常年 ENS。
5. 从全年回放的实际事前状态启动 2/4/8/24 小时孤网及设备故障事件，按关键、重要、可中断负荷顺序量化 ENS、关键负荷供能率、连续失供时长和孤网生存时间。
6. 分开报告企业位置法碳排放与国家级零碳园区核算口径；图、表、报告和简历数字必须来自同一个冻结运行 ID。

## 工程边界

- 电、热、氢三条母线逐时守恒；规划与回放共用约束，不为不同结果维护两套模型。
- 电池与储氢禁止同一时段充放，设备考虑可用率、爬坡、最小负荷和分段性能。
- 低碳型在等年值成本不超过经济型 110% 的约束下最小化运行碳排放，外送电不抵扣购电或燃气排放，且不允许通过失负荷“减碳”。
- 韧性型按孤网、禁外购氢、关键负荷供能率和自备可用电源容量进行工程筛选；120% 保安负荷只作对标，不声称标准认证。
- 没有故障概率数据时只报告确定性 ENS，不使用 EENS、LOLP、SAIDI 或 SAIFI 等概率指标名称。

## 数据与复现

正式运行只读取 `data/raw/` 与 `data/processed/` 中由运行清单显式声明并固定 SHA256 的文件，输出只写入 `artifacts/runs/<run_id>/`。程序不会按文件名自动寻找历史结果，也不会将旧缓存拼入新数据。

正式清单校验还会同时检查字段级来源注册表、原文件哈希、当前 Git 版本以及 `src/`、`scripts/` 和 `data/metadata/` 的受控状态。`--manifest` 入口仅执行这套发布前校验，并明确禁止 `--output` 和所有 S0—S5/旧典型日动作；兼容期 `--workbook` 结果始终标记为非正式基准。

数据来源、单位转换、适用期和工程假设见：

- [数据方法说明](docs/data_methodology.md)
- [字段级来源注册表](data/metadata/source_registry.csv)
- [有界工程假设](data/metadata/assumptions.yaml)

当前正式发布门仍关闭：本机尚未配置 Copernicus CDS/ERA5 凭据，因此没有冻结任何新的 8784 小时量化结论、图表或简历数字。该状态是为了避免旧 NASA 缓存或不可追溯替代数据污染结果。

## 代码结构

```text
src/zero_carbon_park/
├── data/             # 来源注册、ERA5管道、负荷重构与质量门
├── typical_days/     # 真实代表日、366天映射、诊断与跨期链接
├── planning/         # 统一物理模型和三类容量方案
├── replay/           # 固定容量滚动全年回放
├── reliability/      # 孤网与设备故障确定性压力测试
├── reporting/        # 统一指标、静态图表和技术报告
└── optimization/     # HiGHS求解与复现元数据
```

## 验证

```powershell
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_representative_periods.py tests/test_planning_physics.py tests/test_engineering_portfolios.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_full_year_replay.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_reliability_events.py tests/test_reliability_metrics.py tests/test_engineering_comparison.py
.\engrysystem-env\Scripts\python.exe -m pytest -q -m "not slow"
```

秋招项目叙事、岗位能力映射和待正式跑数的简历模板位于 [项目总结汇总](项目总结汇总/)；其中所有方括号量化字段必须由冻结结果自动替换后才能投递。
