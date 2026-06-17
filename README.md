# 零碳园区电-热-氢-储综合能源系统优化调度

本项目基于鄂尔多斯零碳园区数据包，构建 24 小时日前 MILP 优化调度仿真模型，覆盖风电、光伏、电网、电池储能、电解槽、储氢罐、燃料电池、热泵、燃气锅炉和碳排放成本。

## 运行方式

在项目根目录执行：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs
```

运行后会生成：

1. 标准化输入数据：`outputs/processed_inputs/`
2. 场景结果表：`outputs/runs/first_version/`
3. 结果图表：`outputs/figures/`
4. 项目结论初稿：`outputs/docs/project_conclusions.md`

## 模型结构

当前模型支持 S0-S5：

| 场景 | 含义 |
|---|---|
| S0 | 传统供能：电网购电 + 燃气锅炉 |
| S1 | 新能源接入：风电 + 光伏 |
| S2 | 新能源 + 电池储能 |
| S3 | 新能源 + 电池储能 + 制氢储氢 |
| S4 | 完整系统：加入热泵和燃料电池 |
| S5 | 低碳调度：S4 基础上加入碳价成本 |

## 技术栈

1. Python
2. pandas / numpy
3. Pyomo
4. HiGHS
5. matplotlib
6. openpyxl
7. pytest

## 验证

运行测试：

```powershell
.\engrysystem-env\Scripts\python.exe -m pytest -q
```

## v2 多典型日与年化分析

运行夏季、冬季、过渡季三个典型日 S5 调度：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-typical-days
```

运行多典型日加权年化分析：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-annualization
```

输出目录：

1. 多典型日调度结果：`outputs/results/v2_typical_days/`
2. 加权年化结果：`outputs/results/v2_annualized/`
3. 容量规划优化结果：`outputs/results/v2_capacity_planning/`

运行多典型日容量规划优化：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-capacity-planning
```

容量规划会在多典型日联合约束下，同时优化风电、光伏、电池、电解槽、储氢、燃料电池和热泵容量，并输出年化投资成本、年运行成本、年总成本、年碳排放和新能源消纳率。

## v3 投资敏感性与 Pareto 分析

运行设备投资参数敏感性分析：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-investment-sensitivity
```

该分析在容量规划模型基础上，分别调整风电、光伏、电池、电解槽、储氢、燃料电池和热泵投资成本，输出不同投资成本假设下的最优容量、年度成本、年度碳排放和新能源消纳率。

运行成本-碳排放 Pareto 分析：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-pareto-analysis
```

该分析采用年度碳排放上限约束，生成不同减排目标下的年度总成本、设备容量配置和新能源消纳结果，用于研究低碳目标与系统成本之间的权衡关系。

新增输出目录：

1. 投资敏感性结果：`outputs/results/v3_investment_sensitivity/`
2. 成本-碳排放 Pareto 结果：`outputs/results/v3_pareto_cost_carbon/`

## v4 不确定性压力测试

运行固定容量不确定性压力测试：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-uncertainty-stress-test
```

该分析先使用容量规划模型求得基准最优容量，然后固定该容量，在正常预测、光伏偏低、风电偏低、负荷偏高、氢负荷偏高和极端组合场景下重新运行调度，用于检查当前容量方案面对预测误差时的成本、碳排放、外部补氢和新能源消纳表现。

输出目录：

1. 不确定性压力测试结果：`outputs/results/v4_uncertainty_stress_test/`

## v4.2 场景概率加权随机容量规划

运行随机容量规划：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-stochastic-planning
```

该分析把夏季、冬季、过渡季三个典型日与正常预测、光伏偏低、风电偏低、负荷偏高、氢负荷偏高和极端组合六类不确定性场景组合为 18 个概率加权运行场景，在同一组容量决策下最小化期望年总成本。相比固定容量压力测试，随机容量规划会重新选择风电、光伏、电池、电解槽、储氢和热泵容量，使容量配置同时考虑正常工况与不利工况的概率影响。

输出目录：

1. 随机容量规划结果：`outputs/results/v4_stochastic_planning/`

## v4.3 最坏情形鲁棒容量规划

运行鲁棒容量规划：

```powershell
.\engrysystem-env\Scripts\python.exe -m zero_carbon_park.cli --workbook ".\鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx" --output outputs --run-robust-planning
```

该分析同样使用三类典型日与六类不确定性场景，但不再按概率求期望成本，而是把每个不确定性场景都按 365 天年化，要求同一组容量配置在所有场景下可运行，并最小化六类场景中的最大年度总成本。该方法用于评估更保守的工程配置，重点控制风光偏低、负荷偏高或极端组合场景下的成本上界。

输出目录：

1. 鲁棒容量规划结果：`outputs/results/v4_robust_planning/`
