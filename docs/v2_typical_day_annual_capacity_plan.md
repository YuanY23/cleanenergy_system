# 多典型日、年化分析与容量规划优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 v1.4 电-热-氢-储 24 小时 MILP 调度模型基础上，扩展多典型日仿真、多典型日加权年化统计，并进一步建立容量规划优化模型。

**Architecture:** 先保持现有单日调度模型稳定不变，新增多典型日数据层和批量运行层；再新增年化汇总层，把不同典型日按代表天数加权为年度成本、年度排放和年度消纳结果；最后新增容量规划模型，在多典型日联合约束下优化风电、光伏、电池、电解槽、储氢、燃料电池和热泵容量。容量规划模型与现有运行调度模型分开，避免破坏 v1.4 已验证功能。

**Tech Stack:** Python 3.12, pandas, numpy, Pyomo, HiGHS, matplotlib, openpyxl, pytest.

---

## 1. 当前基础

当前项目已经完成：

1. 单典型日 24 小时 MILP 优化调度。
2. 基础场景 S0-S5。
3. v1.1 参数敏感性。
4. v1.2 能源价格与电网排放因子敏感性。
5. v1.3 设备容量方案对比。
6. v1.4 售氢、碳排放上限、新能源消纳率约束。
7. CSV、Excel、PNG、Markdown、Word 结果输出。

当前模型的核心边界是“给定设备容量，优化 24 小时运行调度”。下一阶段要升级为：

```text
多个典型日输入
    ↓
每个典型日独立运行调度
    ↓
按代表天数加权成年化结果
    ↓
在多典型日联合约束下优化设备容量
```

## 2. 总体研究路线

本轮建议命名为 v2，分为三个可单独验收的大阶段：

| 阶段 | 名称 | 目标 | 是否改变数学模型 |
|---|---|---|---|
| v2.1 | 多典型日扩展 | 建立夏季、冬季、过渡季典型日，并分别运行 S5 | 不改变核心模型 |
| v2.2 | 多典型日加权年化 | 按代表天数汇总年度成本、年度排放、年度能源量 | 不改变核心模型 |
| v2.3 | 容量规划优化 | 把部分设备容量变成优化变量，加入投资年化成本 | 新增规划模型 |

执行顺序必须按 v2.1 -> v2.2 -> v2.3。原因是容量规划依赖多典型日数据和年化成本口径，如果先做容量规划，结果缺少年度解释基础。

## 3. 文件结构设计

### 3.1 新增文件

```text
src/zero_carbon_park/typical_days/
├── __init__.py
├── definitions.py        多典型日定义、代表天数、季节参数
├── generator.py          基于当前典型日生成夏季/冬季/过渡季数据
├── runner.py             多典型日批量运行
└── annualization.py      多典型日加权年化统计

src/zero_carbon_park/planning/
├── __init__.py
├── cost_params.py        容量投资、寿命、年化系数参数
├── variables.py          容量规划变量
├── builder.py            容量规划 Pyomo 模型组装
├── constraints.py        规划容量与逐时运行约束
├── objective.py          年化总成本目标函数
├── results.py            规划结果提取
└── runner.py             容量规划运行入口

tests/
├── test_typical_day_generation.py
├── test_typical_day_annualization.py
└── test_capacity_planning.py
```

### 3.2 修改文件

```text
src/zero_carbon_park/cli.py
```

新增命令行能力：

1. `--run-typical-days`：运行多典型日调度。
2. `--run-annualization`：运行多典型日加权年化。
3. `--run-capacity-planning`：运行容量规划优化。

```text
README.md
项目研究报告.md
```

后续执行完成后更新使用方式和研究结论。

## 4. v2.1 多典型日扩展研究方案

### 4.1 研究目的

当前 24 小时典型日只能代表一种运行状态，无法反映季节差异。多典型日扩展的目的，是用少量代表日近似全年运行差异，使模型从“单日调度分析”升级为“多季节运行分析”。

### 4.2 典型日设置

第一版建议使用三个典型日：

| 典型日编号 | 名称 | 代表天数 | 主要特征 |
|---|---|---:|---|
| TD_SUMMER | 夏季典型日 | 120 | 光伏高、电负荷高、热负荷低 |
| TD_WINTER | 冬季典型日 | 120 | 热负荷高、风电较高、光伏较低 |
| TD_TRANSITION | 过渡季典型日 | 125 | 电负荷、热负荷、风光均接近基准 |

代表天数合计为 365 天。

### 4.3 数据生成方法

由于当前还没有真实多季节数据，第一版先基于现有 24 小时数据做比例扰动，保证模型能跑通。

建议扰动系数：

| 字段 | 夏季 | 冬季 | 过渡季 |
|---|---:|---:|---:|
| `pv_available_kw` | 1.15 | 0.70 | 1.00 |
| `wind_available_kw` | 0.90 | 1.15 | 1.00 |
| `electric_load_kw` | 1.15 | 1.05 | 1.00 |
| `heat_load_kw` | 0.60 | 1.35 | 0.90 |
| `hydrogen_load_kg` | 1.00 | 1.00 | 1.00 |
| `electricity_price_cny_per_kwh` | 1.05 | 1.05 | 1.00 |
| `gas_price_cny_per_m3` | 1.00 | 1.00 | 1.00 |
| `grid_emission_kgco2_per_kwh` | 1.00 | 1.00 | 1.00 |
| `carbon_price_cny_per_tco2` | 1.00 | 1.00 | 1.00 |

说明：

1. 夏季光伏较高，电负荷略高，热负荷降低。
2. 冬季风电较高，热负荷显著增加，光伏降低。
3. 过渡季接近当前基准日。
4. 氢负荷第一版保持不变，避免过早引入过多变量。
5. 后续如果用户提供真实多季节数据，再替换生成器。

### 4.4 v2.1 输出

输出目录建议：

```text
outputs/results/v2_typical_days/
├── TD_SUMMER/
│   ├── scenario_summary.csv
│   ├── scenario_hourly_results.csv
│   ├── input_timeseries.csv
│   ├── device_outputs.png
│   ├── battery_soc.png
│   └── h2_storage.png
├── TD_WINTER/
├── TD_TRANSITION/
└── typical_day_summary.csv
```

第一版只运行 S5，即当前完整低碳调度场景。原因是 S5 包含完整电-热-氢-储和碳价，最适合作为多典型日基准。

### 4.5 验收标准

1. 三个典型日均生成 24 行时间序列。
2. 三个典型日均能运行 S5 并得到 `optimal`。
3. 每个典型日输出逐时结果和汇总结果。
4. 夏季、冬季、过渡季结果在购电量、热泵供热、碳排放上有明显差异。
5. 原有 S0-S5、v1.1-v1.4 测试仍全部通过。

## 5. v2.2 多典型日加权年化研究方案

### 5.1 研究目的

多典型日加权年化的目的是把不同典型日结果按代表天数汇总，得到近似年度指标。这样可以回答：

1. 全年运行成本大约是多少？
2. 全年碳排放大约是多少？
3. 全年新能源消纳率大约是多少？
4. 哪个季节对成本和排放贡献最大？
5. 哪类设备全年利用率较高，哪类设备利用率偏低？

### 5.2 年化计算方法

对每个典型日 `d`，设代表天数为 `weight_days[d]`。

年度总成本：

```text
annual_total_cost = Σ daily_total_cost[d] × weight_days[d]
```

年度购电量：

```text
annual_grid_purchase = Σ daily_grid_purchase[d] × weight_days[d]
```

年度碳排放：

```text
annual_carbon_emission = Σ daily_carbon_emission[d] × weight_days[d]
```

年度新能源可发量：

```text
annual_renewable_available = Σ daily_renewable_available[d] × weight_days[d]
```

年度新能源利用量：

```text
annual_renewable_used = Σ daily_renewable_used[d] × weight_days[d]
```

年度新能源消纳率：

```text
annual_renewable_consumption_rate
= annual_renewable_used / annual_renewable_available
```

设备年度利用量也按相同方式计算，例如热泵年度供热、电池年度充放电、电解槽年度制氢、燃料电池年度发电等。

### 5.3 v2.2 输出

输出目录建议：

```text
outputs/results/v2_annualized/
├── annual_summary.csv
├── annual_summary.xlsx
├── typical_day_contribution.csv
├── typical_day_contribution.xlsx
├── annual_cost_breakdown.png
├── annual_carbon_by_typical_day.png
├── annual_energy_by_typical_day.png
└── annual_conclusion.md
```

核心表字段：

| 字段 | 含义 |
|---|---|
| `annual_total_cost_cny` | 年度总运行成本 |
| `annual_grid_cost_cny` | 年度购电成本 |
| `annual_gas_cost_cny` | 年度天然气成本 |
| `annual_carbon_cost_cny` | 年度碳成本 |
| `annual_grid_purchase_kwh` | 年度购电量 |
| `annual_renewable_available_kwh` | 年度新能源可发量 |
| `annual_renewable_used_kwh` | 年度新能源利用量 |
| `annual_renewable_consumption_rate` | 年度新能源消纳率 |
| `annual_carbon_emission_kg` | 年度碳排放 |
| `annual_h2_production_kg` | 年度制氢量 |
| `annual_h2_external_supply_kg` | 年度外部补氢量 |
| `annual_fuel_cell_generation_kwh` | 年度燃料电池发电量 |
| `annual_heat_pump_heat_kwh` | 年度热泵供热量 |
| `annual_gas_boiler_heat_kwh` | 年度燃气锅炉供热量 |

### 5.4 验收标准

1. `annual_summary.csv` 只有一行年度汇总结果。
2. `typical_day_contribution.csv` 有三行，分别对应夏季、冬季、过渡季。
3. 年度代表天数合计为 365。
4. 年度成本等于三个典型日成本按代表天数加权之和。
5. 年度新能源消纳率使用“年度利用量 / 年度可发量”计算，不直接平均三个日消纳率。
6. 输出至少三张图：成本构成、碳排放贡献、能源量贡献。

## 6. v2.3 容量规划优化研究方案

### 6.1 研究目的

当前 v1.3 只是“给定容量倍数后做方案对比”，并不是让模型自动决定最优容量。容量规划优化的目的是把部分设备容量作为决策变量，让模型同时决定：

1. 风电装机多大合适？
2. 光伏装机多大合适？
3. 电池功率和容量多大合适？
4. 电解槽功率多大合适？
5. 储氢罐容量多大合适？
6. 燃料电池容量是否值得配置？
7. 热泵容量是否需要扩展？

容量规划结果需要在“年度运行成本 + 年化投资成本”口径下评价，而不能只看某一天的运行成本。

### 6.2 规划变量

第一版建议优化以下容量变量：

| 变量 | 含义 | 单位 | 建议上下限 |
|---|---|---|---|
| `wind_capacity_kw` | 风电装机容量 | kW | 0-30000 |
| `pv_capacity_kw` | 光伏装机容量 | kW | 0-30000 |
| `battery_power_capacity_kw` | 电池功率容量 | kW | 0-15000 |
| `battery_energy_capacity_kwh` | 电池能量容量 | kWh | 0-60000 |
| `electrolyzer_power_capacity_kw` | 电解槽功率 | kW | 0-10000 |
| `h2_storage_capacity_kg` | 储氢罐容量 | kg | 0-5000 |
| `fuel_cell_power_capacity_kw` | 燃料电池功率 | kW | 0-5000 |
| `heat_pump_power_capacity_kw` | 热泵功率 | kW | 0-10000 |

燃气锅炉第一版建议保留固定容量，作为保供兜底设备。原因是如果一开始也优化锅炉容量，会引入更多可靠性和备用容量问题，影响第一版规划模型跑通。

### 6.3 容量与运行耦合

当前调度模型使用固定容量参数，例如：

```text
电池充电功率 <= 电池额定功率
电解槽耗电功率 <= 电解槽额定功率
热泵耗电功率 <= 热泵额定功率
```

容量规划模型中应改为：

```text
电池充电功率[d,t] <= 电池功率容量
电池放电功率[d,t] <= 电池功率容量
电池 SOC[d,t] <= 电池能量容量
电解槽耗电功率[d,t] <= 电解槽功率容量
储氢量[d,t] <= 储氢容量
燃料电池发电功率[d,t] <= 燃料电池功率容量
热泵耗电功率[d,t] <= 热泵功率容量
```

风光可发功率由固定时间序列改为：

```text
光伏可发功率[d,t] = 光伏装机容量 × 光伏容量因子[d,t]
风电可发功率[d,t] = 风电装机容量 × 风电容量因子[d,t]
```

### 6.4 年化投资成本

容量规划目标函数建议为：

```text
min annual_total_cost
  = annual_operation_cost
  + annualized_investment_cost
```

其中年度运行成本来自多典型日加权：

```text
annual_operation_cost
= Σ daily_operation_cost[d] × weight_days[d]
```

年化投资成本：

```text
annualized_investment_cost
= wind_capacity_kw × wind_capex_cny_per_kw × CRF_wind
+ pv_capacity_kw × pv_capex_cny_per_kw × CRF_pv
+ battery_power_capacity_kw × battery_power_capex_cny_per_kw × CRF_battery
+ battery_energy_capacity_kwh × battery_energy_capex_cny_per_kwh × CRF_battery
+ electrolyzer_power_capacity_kw × electrolyzer_capex_cny_per_kw × CRF_electrolyzer
+ h2_storage_capacity_kg × h2_storage_capex_cny_per_kg × CRF_h2_storage
+ fuel_cell_power_capacity_kw × fuel_cell_capex_cny_per_kw × CRF_fuel_cell
+ heat_pump_power_capacity_kw × heat_pump_capex_cny_per_kw × CRF_heat_pump
```

资本回收系数 CRF：

```text
CRF = r × (1 + r)^n / ((1 + r)^n - 1)
```

其中 `r` 为折现率，`n` 为设备寿命年限。

第一版建议折现率取 8%。投资成本先采用工程假设，后续可替换真实数据。

### 6.5 建议投资参数第一版

| 设备 | 投资参数 | 建议值 | 单位 | 寿命/年 |
|---|---|---:|---|---:|
| 风电 | `wind_capex_cny_per_kw` | 6000 | 元/kW | 20 |
| 光伏 | `pv_capex_cny_per_kw` | 3500 | 元/kW | 25 |
| 电池功率 | `battery_power_capex_cny_per_kw` | 800 | 元/kW | 12 |
| 电池容量 | `battery_energy_capex_cny_per_kwh` | 1200 | 元/kWh | 12 |
| 电解槽 | `electrolyzer_capex_cny_per_kw` | 3000 | 元/kW | 15 |
| 储氢罐 | `h2_storage_capex_cny_per_kg` | 2500 | 元/kg | 20 |
| 燃料电池 | `fuel_cell_capex_cny_per_kw` | 6000 | 元/kW | 10 |
| 热泵 | `heat_pump_capex_cny_per_kw` | 1000 | 元/kW | 15 |

这些参数第一版只用于跑通容量规划逻辑，不作为最终工程报价。后续如果用户提供真实设备价格，应替换。

### 6.6 规划约束建议

第一版容量规划至少加入以下约束：

1. 每个典型日、每个小时满足电力平衡。
2. 每个典型日、每个小时满足热力平衡。
3. 每个典型日、每个小时满足氢气平衡。
4. 每个典型日内部电池 SOC 动态成立。
5. 每个典型日内部储氢动态成立。
6. 每个典型日电池末端 SOC 等于初始 SOC。
7. 每个典型日储氢末端库存等于初始储氢量。
8. 所有设备出力不超过规划容量。
9. 风光利用与弃电之和等于规划容量乘容量因子。
10. 外部补氢允许存在但成本很高，用于识别规划不足。

暂不加入的复杂约束：

1. 设备最小启停时间。
2. 设备爬坡约束。
3. 整数台数约束。
4. 电池寿命衰减。
5. 风光建设土地约束。
6. 电网最大接入容量约束。

原因是第一版容量规划的目标是先建立“规划-运行一体化”闭环，避免一次性复杂化导致模型难以调试。

### 6.7 v2.3 输出

输出目录建议：

```text
outputs/results/v2_capacity_planning/
├── planning_summary.csv
├── planning_summary.xlsx
├── planning_capacity_result.csv
├── planning_capacity_result.xlsx
├── planning_typical_day_operation.csv
├── planning_typical_day_operation.xlsx
├── planning_hourly_results.csv
├── capacity_mix.png
├── annual_cost_breakdown.png
├── annual_carbon_by_typical_day.png
└── planning_conclusion.md
```

核心输出字段：

| 字段 | 含义 |
|---|---|
| `wind_capacity_kw` | 最优风电装机 |
| `pv_capacity_kw` | 最优光伏装机 |
| `battery_power_capacity_kw` | 最优电池功率 |
| `battery_energy_capacity_kwh` | 最优电池容量 |
| `electrolyzer_power_capacity_kw` | 最优电解槽功率 |
| `h2_storage_capacity_kg` | 最优储氢容量 |
| `fuel_cell_power_capacity_kw` | 最优燃料电池容量 |
| `heat_pump_power_capacity_kw` | 最优热泵功率 |
| `annual_operation_cost_cny` | 年度运行成本 |
| `annualized_investment_cost_cny` | 年化投资成本 |
| `annual_total_cost_cny` | 年度总成本 |
| `annual_carbon_emission_kg` | 年度碳排放 |
| `annual_renewable_consumption_rate` | 年度新能源消纳率 |
| `annual_h2_external_supply_kg` | 年度外部补氢量 |

### 6.8 容量规划验收标准

1. 容量规划模型可以用 HiGHS 求解到 `optimal`。
2. 所有容量变量在设定上下限内。
3. 所有典型日电、热、氢平衡残差接近 0。
4. 年度总成本等于年度运行成本加年化投资成本。
5. 输出最优容量配置表。
6. 输出每个典型日的运行结果。
7. 若燃料电池最优容量为 0，应在结论中解释其经济性不足。
8. 若外部补氢不为 0，应在结论中解释本地制氢或储氢能力不足。

## 7. 任务拆分

### Task 1: 多典型日定义与生成器

**Files:**
- Create: `src/zero_carbon_park/typical_days/__init__.py`
- Create: `src/zero_carbon_park/typical_days/definitions.py`
- Create: `src/zero_carbon_park/typical_days/generator.py`
- Create: `tests/test_typical_day_generation.py`

- [x] 定义 `TypicalDayConfig`，字段包含 `day_id`、`name`、`weight_days` 和各类缩放系数。
- [x] 定义 `get_default_typical_days()`，返回 TD_SUMMER、TD_WINTER、TD_TRANSITION。
- [x] 编写 `generate_typical_day_workbook(workbook, config)`，返回扰动后的 `InputWorkbook`。
- [x] 测试三个典型日均为 24 行。
- [x] 测试代表天数合计为 365。
- [x] 测试冬季热负荷总量大于过渡季，夏季热负荷总量小于过渡季。

### Task 2: 多典型日批量运行

**Files:**
- Create: `src/zero_carbon_park/typical_days/runner.py`
- Create: `tests/test_typical_day_runner.py`

- [x] 编写 `run_typical_day_scenarios(workbook_path, output_root, scenario_id="S5")`。
- [x] 每个典型日生成独立输出目录。
- [x] 每个典型日导出 `input_timeseries.csv`。
- [x] 每个典型日运行 S5 并导出 summary、hourly 和图表。
- [x] 汇总生成 `typical_day_summary.csv`。
- [x] 测试三个典型日求解状态均为 `optimal`。

### Task 3: 多典型日加权年化

**Files:**
- Create: `src/zero_carbon_park/typical_days/annualization.py`
- Create: `tests/test_typical_day_annualization.py`

- [x] 编写 `annualize_typical_day_results(summary, weights)`。
- [x] 按代表天数加权年度成本、购电量、排放、制氢量、热泵供热等。
- [x] 年度新能源消纳率使用年度新能源利用量除以年度新能源可发量。
- [x] 输出 `annual_summary.csv` 和 `typical_day_contribution.csv`。
- [x] 测试年度成本等于三个典型日成本加权和。
- [x] 测试年度消纳率不是简单平均，而是总量口径。

### Task 4: 年化图表与结论

**Files:**
- Modify: `src/zero_carbon_park/reporting/plots.py`
- Create or Modify: `src/zero_carbon_park/reporting/export.py`
- Create: `tests/test_annualized_reporting.py`

- [x] 新增年度成本构成图。
- [x] 新增典型日碳排放贡献图。
- [x] 新增典型日能源量贡献图。
- [x] 生成 `annual_conclusion.md`。
- [x] 测试空数据不会导致图表函数崩溃。

### Task 5: CLI 接入 v2.1 和 v2.2

**Files:**
- Modify: `src/zero_carbon_park/cli.py`
- Modify: `README.md`
- Test: `tests/test_full_pipeline.py`

- [x] 添加 `--run-typical-days` 参数。
- [x] 添加 `--run-annualization` 参数。
- [x] 保持原有不带新参数时仍运行 v1 基础流程。
- [x] 测试新 CLI 参数能生成 `outputs/results/v2_typical_days` 和 `outputs/results/v2_annualized`。

### Task 6: 容量规划参数

**Files:**
- Create: `src/zero_carbon_park/planning/__init__.py`
- Create: `src/zero_carbon_park/planning/cost_params.py`
- Create: `tests/test_capacity_planning.py`

- [x] 定义 `PlanningCostParams`。
- [x] 实现 `capital_recovery_factor(rate, years)`。
- [x] 实现默认投资成本参数。
- [x] 测试 CRF 计算结果为正数。
- [x] 测试所有默认投资成本参数均大于 0。

### Task 7: 容量规划模型变量与约束

**Files:**
- Create: `src/zero_carbon_park/planning/variables.py`
- Create: `src/zero_carbon_park/planning/constraints.py`
- Create: `src/zero_carbon_park/planning/builder.py`
- Test: `tests/test_capacity_planning.py`

- [x] 创建容量变量：风电、光伏、电池功率、电池容量、电解槽、储氢、燃料电池、热泵。
- [x] 创建多典型日逐时运行变量。
- [x] 复用 v1 的电、热、氢、储能、碳排放逻辑，但增加典型日维度 `D`。
- [x] 风光可发功率改为容量变量乘容量因子。
- [x] 设备出力上限改为规划容量。
- [x] 测试模型能创建并包含容量变量。

### Task 8: 容量规划目标函数

**Files:**
- Create: `src/zero_carbon_park/planning/objective.py`
- Modify: `src/zero_carbon_park/planning/builder.py`
- Test: `tests/test_capacity_planning.py`

- [x] 计算多典型日加权运行成本。
- [x] 计算年化投资成本。
- [x] 目标函数为年度运行成本加年化投资成本。
- [x] 测试目标函数表达式可以被 Pyomo 构造。

### Task 9: 容量规划求解与结果输出

**Files:**
- Create: `src/zero_carbon_park/planning/results.py`
- Create: `src/zero_carbon_park/planning/runner.py`
- Modify: `src/zero_carbon_park/cli.py`
- Test: `tests/test_capacity_planning.py`

- [x] 编写 `run_capacity_planning(workbook_path, output_root)`。
- [x] 调用 HiGHS 求解规划模型。
- [x] 输出容量结果表、年度成本表、典型日运行表和逐时结果表。
- [x] 输出容量组合图和年度成本构成图。
- [x] CLI 添加 `--run-capacity-planning`。
- [x] 测试规划输出文件存在。

### Task 10: 文档与研究结论更新

**Files:**
- Modify: `README.md`
- Modify: `项目研究报告.md`
- Create: `outputs/results/v2_capacity_planning/planning_conclusion.md`

- [x] README 增加 v2 运行方式。
- [x] 项目研究报告增加多典型日、年化分析和容量规划章节。
- [x] 规划结果输出结论说明最优容量、成本、排放、消纳率和设备经济性。
- [x] 全量运行 `pytest -q`。

## 8. 推荐执行顺序和汇报节点

### 第一大阶段：v2.1 多典型日扩展

完成 Task 1、Task 2 后汇报。

汇报内容：

1. 三个典型日数据是否生成。
2. 三个典型日 S5 是否求解成功。
3. 夏季、冬季、过渡季总成本、购电量、碳排放差异。
4. 输出目录和图表位置。

### 第二大阶段：v2.2 多典型日加权年化

完成 Task 3、Task 4、Task 5 后汇报。

汇报内容：

1. 年度总成本。
2. 年度碳排放。
3. 年度新能源消纳率。
4. 三个典型日对年度成本和排放的贡献。
5. CLI 新命令是否可用。

### 第三大阶段：v2.3 容量规划优化

完成 Task 6、Task 7、Task 8、Task 9、Task 10 后汇报。

汇报内容：

1. 最优容量配置。
2. 年化投资成本。
3. 年度运行成本。
4. 年度总成本。
5. 年度碳排放。
6. 是否存在外部补氢。
7. 燃料电池、储氢、热泵等设备是否被模型选择。

## 9. 风险与控制

### 9.1 数据风险

第一版多典型日由基准日缩放得到，不是真实全年数据。因此结论只能作为方法验证和趋势分析，不能作为最终工程结论。

控制方式：

1. 在报告中明确“典型日由基准数据缩放生成”。
2. 输出每个典型日的输入曲线，方便人工检查。
3. 后续获得真实数据后，只替换数据生成层，不重写模型。

### 9.2 规划模型规模风险

容量规划模型会把典型日维度、小时维度和容量变量放在一起，变量和约束数量明显增加。

控制方式：

1. 第一版只做 3 个典型日，每个典型日 24 小时。
2. 第一版不加爬坡、最小启停和整数台数。
3. 容量变量先用连续变量，避免整数规划过大。
4. 若 HiGHS 求解慢，先关闭部分二进制启停变量，验证 LP 版本，再恢复 MILP。

### 9.3 投资参数风险

容量规划结果对投资成本非常敏感。第一版投资参数是工程假设，不宜直接作为真实经济性结论。

控制方式：

1. 在 `planning/cost_params.py` 中集中管理投资参数。
2. 输出投资参数表，保证结果可追溯。
3. 后续增加投资成本敏感性分析。

## 10. 最终交付物

完成本计划后，项目应新增以下成果：

1. 多典型日输入数据。
2. 多典型日 S5 调度结果。
3. 多典型日加权年化结果。
4. 容量规划优化模型。
5. 最优容量配置结果。
6. 年化成本、排放、消纳率图表。
7. v2 阶段研究结论文档。
8. 更新后的 README 和项目研究报告。

## 11. 建议先执行的最小闭环

如果你同意本方案，建议先只执行第一大阶段：

```text
Task 1 -> Task 2
```

也就是先把三个典型日生成出来，并分别跑通 S5。这个阶段不动容量规划模型，风险最低，最适合先确认多典型日数据逻辑是否符合你的研究理解。

第一大阶段通过后，再执行：

```text
Task 3 -> Task 4 -> Task 5
```

最后再进入容量规划：

```text
Task 6 -> Task 7 -> Task 8 -> Task 9 -> Task 10
```
