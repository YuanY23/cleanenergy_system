---
title: 零碳园区8784小时规划、全年回放与孤网保供升级 - Plan
type: feat
date: 2026-08-09
deepened: 2026-08-09
---

# 零碳园区8784小时规划、全年回放与孤网保供升级 - Plan

## Goal Capsule

- **目标**：把现有项目升级为“面向零碳工业园区的电—热—氢—储综合能源系统规划与韧性评估”。项目以2024年8784小时数据为基础，完成容量规划、固定容量全年回放、孤网保供评估和经济—碳—可靠性对比。
- **权威顺序**：本计划中的数据与口径要求 > 官方政策和数据源 > 项目配置快照 > 模型默认值 > 历史文档和旧结果。
- **执行边界**：不开发网页、驾驶舱或交互式系统。不把S0—S5等版本式场景作为项目主线。不把历史运行结果用于新基准。
- **停止条件**：数据质量门、物理约束门、全年回放门、可靠性口径门或结果复现门任一失败时，不发布最终结论和简历数字。
- **执行配置**：代码改造采用增量测试。完整8784小时求解标记为慢流程。正式发布只允许使用唯一的最新基准运行目录。
- **尾项责任**：最后一个实施单元负责旧产物隔离、静态报告、简历描述、面试问答和结果可复现性审计。

## Product Contract

### Summary

本升级不增加展示系统。它把项目的专业价值集中在四件事上：可追溯的8784小时数据、可信的多能耦合规划、连续状态的全年运行验证、面向重要负荷的孤网保供评估。最终成果是一份工程分析报告、一组静态专业图表、一套可复现结果和可量化的简历表述。

### Problem Frame

现有项目已具备电—热—氢—储优化、典型日、容量规划、敏感性和不确定性分析，但数据和模型仍有四个断点。

1. 正式工作簿仍是24小时重构样例；已有8784小时生成脚本与模型读取器不兼容。
2. 全年负荷为150 MW级，而规划模型多项容量上限仍是5—30 MW级。
3. 规划模型缺少储能互斥、储氢速率、跨期状态连续和正确的分段曲线约束。
4. 历史结果、图表和手写统计存在口径漂移，不能支撑新的简历结论。

### Requirements

#### 数据真实性、隔离与溯源

- R1. 正式基准必须重新下载2024年原始数据，并生成恰好8784个连续的本地标准时时间点。
- R2. 历史运行数据、旧图表、旧汇总结果和旧手写结论不得作为正式基准的输入。
- R3. 每个输入字段必须标注来源类别、原始单位、目标单位、时区、获取日期、来源URL、处理方法和文件哈希。
- R4. 气象、政策价格、碳因子、设备参数和工程假设必须分层标注，不能把再分析数据或合成负荷表述为园区实测数据。
- R5. 电、热、氢负荷必须由可解释的合成方法生成，并记录峰值、年总量、季节性、工作日效应和关键负荷比例等校准假设。
- R6. 数据管道必须拒绝缺失小时、重复时间戳、闰日错误、单位错误、容量因子越界和未经登记的输入文件。

#### 规划模型与物理约束

- R7. 容量规划和运行回放必须复用同一套电—热—氢—储约束，容量变量自由或固定由配置决定。
- R8. 模型必须约束电网接入容量、电池和储氢充放互斥、设备出力上下限、储能状态连续、设备可用率和分级失负荷。
- R9. 设备效率曲线必须使用有序增量段、SOS2或经验证的恒定效率，不能允许优化器任意选择最有利区段。
- R10. 规划输出必须形成经济型、低碳型和韧性型三个可比较方案，三者使用同一数据、成本年化和碳核算边界。
- R11. 代表时段必须从8784小时真实日期中选取，保留季节权重和跨代表时段储能状态连接，并强制包含低风低光、极寒高热负荷和高综合负荷等极端日。

#### 全年回放与可靠性

- R12. 固定规划容量后，系统必须以滚动窗口完成全部8784小时回放，并在窗口之间传递电池SOC和储氢库存。
- R13. 全年回放必须输出每小时能量平衡、设备出力、购售电、弃风弃光、外购氢、负荷损失和储能状态。
- R14. 孤网事件必须从正常全年回放对应时刻的实际事前状态启动，不能统一假设满电或满氢。
- R15. 可靠性评估必须覆盖2、4、8、24小时停电、连续低风低光叠加停电、极寒高热负荷和关键设备故障。
- R16. 确定性场景只报告ENS、失供小时、关键负荷供能率、最大连续失供时长、SOC最低值和孤网生存时长；没有概率数据时不得称为EENS、LOLP、SAIDI或SAIFI。

#### 能碳核算与最终成果

- R17. 园区运行碳排放必须同时输出企业范围二位置法和国家级零碳园区验收口径；两套口径分别列示天然气直接排放、净购电、绿电和抵消量，禁止混用排放因子。
- R18. 碳价只作为影子价格或敏感性参数，不把全国碳市场价格直接表述为本园区实际履约成本。
- R19. 正式成果必须包含输入数据审计、规划容量、全年运行、经济性、碳排放、可靠性和敏感性结果。
- R20. 最终只交付静态工程图表、技术报告、README、简历项目描述和面试问答，不交付交互式驾驶舱。
- R21. 所有简历数字必须能回溯到最新基准的结果表、配置快照、源文件哈希和求解日志。
- R22. 最终材料必须分别映射综合能源规划、新能源系统分析、能源管理/双碳和电力保供类岗位的能力关键词，并明确个人完成的建模、数据和分析工作。

### Acceptance Examples

- AE1. 当正式命令发现 `outputs/` 中的历史CSV时，程序仍只读取本次运行清单中列出的 `data/raw/` 和 `data/processed/` 文件，并在日志中列出被排除的旧路径。覆盖 R2、R3。
- AE2. 当2024年UTC气象转为北京时间时，管道会额外获取年界所需小时，最终本地时间从 `2024-01-01 00:00` 连续到 `2024-12-31 23:00`，且共有8784条。覆盖 R1、R6。
- AE3. 当24小时孤网事件发生在冬季晚高峰时，事件从该时刻全年回放的SOC和储氢库存启动，电网购售电归零，模型优先保关键负荷并显式记录ENS。覆盖 R14—R16。
- AE4. 当设备参数没有权威国内造价来源时，报告把它标为“国际数据库参考区间+本地化工程假设”，并对上下界做敏感性分析。覆盖 R3、R4、R19。

### Success Criteria

- 8784小时主表有8784个唯一、连续、本地时区明确的时间戳；所有强制字段无缺失。
- 电、热、氢逐时平衡最大绝对残差不高于 `1e-6` 的模型基准单位。
- 电池和储氢不存在超过数值容差的同时充放；任何设备不超过固定容量和可用率上限。
- 代表时段权重合计366天；年总量重构误差不高于2%；P5、P50、P95误差不高于5%；原始极值被强制保留。
- 全年回放恰好输出8784个唯一小时；滚动窗口无重复提交，无窗口边界能量重置。
- 三个规划方案在同一指标字典下完成成本、碳和可靠性对比。
- 低碳型和韧性型必须分别报告相对经济型的增量成本、减排收益和可靠性收益；若差异小于数值或工程显著性阈值，报告必须明确“未形成独立工程方案”，不能只更换标签。
- 低碳型必须量化相对国家级零碳园区适用指标的差距，并说明在经济型成本上限110%下是否可达；不可达时报告最小差距和主导约束。
- 代表时段方案的全年回放总成本与8784小时连续松弛下界差距不高于10%；超出时扩大代表时段集合并重新规划。
- 每个确定性停电场景都有ENS、关键负荷供能率和生存时长；指标名称不越过数据证据。
- 正式结果目录只包含本次基准的配置、数据清单、日志、表格、图和报告；历史产物不进入最终交付。

### Scope Boundaries

**本次范围内**

- 园区级电—热—氢—储容量规划和小时级能量平衡。
- 固定容量的8784小时运行回放。
- 面向重要负荷的孤网供能充裕度和设备故障压力测试。
- 运行阶段范围一、范围二位置法碳排放，以及零碳园区相关指标。
- 工程经济性、参数敏感性和静态成果整理。

**本次不做**

- 继电保护、短路电流、电能质量、潮流、频率稳定和电磁暂态。
- 全生命周期评价、完整范围三排放和产品碳足迹。
- 真实园区数字孪生、在线控制、负荷预测和交互式可视化。
- 在没有真实故障频率数据时宣称概率可靠性或标准合规认证。

## Planning Contract

### Key Technical Decisions

- KTD1. 采用“统一容量—运行模型”，通过配置切换容量自由或固定。旧 `models/`、`optimization/` 和 `scenarios/` 导入面只保留为调用统一核心的薄适配器，不再维护重复物理约束；当前消费者是既有回归测试和历史CLI，完成测试迁移后再评估退役。覆盖 R7—R10。
- KTD2. 2024年作为气象研究年，因为它是最近的完整闰年并天然形成8784小时。正式数据必须重新下载，现有 `outputs/nasa_power_ordos_2024.json` 只用于审计对照，不进入新基准。 (session-settled: user-directed — chosen over 复用历史缓存: 用户要求旧数据和旧结果不进入最新分析) 覆盖 R1—R4。
- KTD3. ERA5小时单层数据作为生产气象源，使用100 m风速、地表太阳辐射和2 m温度；NASA POWER用于月度交叉核验，Global Wind Atlas用于长期风资源偏差校准。ERA5提供直接的100 m风分量，可避免现有WS50M与轮毂高度不匹配。覆盖 R1、R3、R4。
- KTD4. 保留UTC和 `Asia/Shanghai` 两列时间。所有电价、负荷和结果按北京时间计算，原始气象时标不被覆盖。覆盖 R1、R3、R6。
- KTD5. 负荷采用“公开尺度校准的可审计合成负荷”，不伪装成真实园区SCADA。园区规模优先由最新公开的园区能耗、项目容量或产能资料校准；若没有直接适用数据，才使用150 MW峰值作为明确的工程情景假设，并同时运行50%、100%、150%三档规模敏感性。电负荷按工业基荷、工作日和温度修正构建；热负荷按采暖度时和工艺基荷构建；氢需求按连续工艺与可中断任务构建。覆盖 R4、R5。
- KTD6. 代表时段最终总数候选为8、12、16天，其中包含4个强制极端日，其余日期通过聚类选择。系统选择满足成功标准的最小集合，聚类中心映射到真实日期。短周期电池使用代表日内状态，储氢采用Kotzur式跨期库存变量和原始日序转移计数连接，禁止每个代表日独立循环归零。四类极端日为最大电负荷日、最大热负荷日、最低风光联合出力日和最大综合净负荷日。覆盖 R11。
- KTD7. 规划采用代表时段MILP作为主求解，并运行8784小时连续松弛基准提供目标下界。该基准只有一个决策用途：当固定容量全年回放总成本相对下界超过10%时，触发扩大代表时段集合并重新规划。最终容量必须通过8784小时固定容量回放，不以代表时段估算值直接发布。覆盖 R10—R13。
- KTD8. 全年回放采用168小时窗口、24小时提交步长。窗口传递SOC和储氢库存，只保存提交区结果。非末窗口使用滚动预测尾段的储能终值惩罚防止视野末端无价值放空；年末窗口由KTD9的年度循环条件约束。该设计控制MILP规模并保留连续状态。覆盖 R12、R13。
- KTD9. 年初储能状态通过年度循环预热迭代获得。若首尾状态在三次迭代后仍不能收敛到容量的1%，报告该偏差并禁止隐去初始库存影响。覆盖 R12、R13。
- KTD10. 可靠性先做确定性压力测试。事件从全年状态启动，并按关键、重要、可中断三类负荷设置不同失供惩罚。GB/T 29328-2018和自备应急电源容量达到保安负荷120%的管理要求作为工程对标，不作为项目认证结论。覆盖 R14—R16。
- KTD11. 碳核算输出两套不可混算的结果。企业范围二位置法采用最新省级电力CO2因子；国家级零碳园区口径采用该核算方法规定的化石能源电力因子和绿电零因子。外送电不直接抵扣企业范围二购电排放；碳价只做敏感性。覆盖 R17、R18。
- KTD12. 最终用经济型、低碳型、韧性型三方案讲述项目，不用S0—S5递进调度叙事。 (session-settled: user-directed — chosen over 版本式场景叙事: 简历需要呈现统一的零碳园区工程项目) 覆盖 R10、R19—R21。
- KTD13. 最终交付采用静态工程报告和图表。 (session-settled: user-directed — chosen over 交互式能碳驾驶舱: 面试官主要通过简历判断专业能力) 覆盖 R20。
- KTD14. 每次正式研究先写入 `artifacts/runs/<run_id>/` 不可变目录。只有全部发布门通过后，程序才以原子文件替换更新 `artifacts/latest.json` 指针。历史结果在实施时先列清单，再移出正式结果路径；任何删除动作单独记录。覆盖 R2、R21。

### High-Level Technical Design

```mermaid
flowchart LR
    A["官方原始数据与工程假设"] --> B["8784小时数据管道与质量门"]
    B --> C["真实日期代表时段与极端日"]
    C --> D["统一电-热-氢-储容量规划"]
    D --> E["固定容量8784小时滚动回放"]
    E --> F["孤网与设备故障事件"]
    D --> G["经济型/低碳型/韧性型方案"]
    E --> G
    F --> G
    G --> H["静态工程报告、图表与简历结论"]
```

### Data Source Plan

| 数据 | 正式用途 | 主来源 | 校核/说明 |
|---|---|---|---|
| 2024逐时太阳辐射、2 m温度、100 m风 | PV、风电和热负荷驱动 | Copernicus ERA5 Hourly Data on Single Levels | NASA POWER用于月度检查；Global Wind Atlas用于长期风资源校准，不拼接逐时时序 |
| 时区和历法 | 构造北京时间8784小时 | IANA `Asia/Shanghai` + Python时区库 | 原始UTC列永久保留 |
| 蒙西分时电价 | 逐时购电价格形状 | 内蒙古发改委分时电价通知 | 若实施日存在更新文件，以更新文件覆盖并记录版本 |
| 输配电价、需量电价、线损率 | 购电成本与接入成本 | 国家发改委第四监管周期省级电网输配电价 | 2026-08-01起执行，按假定电压等级配置 |
| 天然气价格 | 锅炉和燃气设备成本 | 鄂尔多斯市发改委最新非居民天然气价格 | 采用适用区域价格并做季节/区间敏感性 |
| 电力CO2因子 | 企业范围二位置法 | 生态环境部最新省级电力CO2因子 | 当前可核验内蒙古值为0.6479 kgCO2/kWh；实施时再次确认最新版本 |
| 天然气排放参数 | 范围一 | 生态环境部企业温室气体核算指南 | 由低位热值、单位热值含碳量和氧化率计算，不手填来历不明常数 |
| 零碳园区边界 | 验收口径碳核算与指标 | 国家发改委等部门零碳园区建设通知及核算方法 | 当前方法的化石能源电力因子为0.8325 kgCO2/kWh，直供非化石电力及合规绿电因子为0；与0.6479位置法结果分开报告 |
| 风光储造价 | CAPEX与敏感性 | IRENA Renewable Power Generation Costs in 2024 | 国际数据只作基准区间，报告本地化假设 |
| 电解槽效率与造价 | 制氢性能与成本 | IEA Global Hydrogen Review 2025、DOE技术目标 | 区分中国当前区间和远期目标，目标值不得当现状值 |
| 供电可靠性对标 | 事件与指标口径 | GB/T 29328-2018、国家能源局《电力可靠性管理办法》 | 只做工程对标，不声称认证 |
| 代表时段方法 | 时序聚类与季节储能处理 | Kotzur等，Applied Energy 2018 | 强制极端日并用全年回放消除代表日偏差 |

### System-Wide Impact

- 数据生命周期从“根目录Excel隐式发现”改为“原始层—处理层—运行清单—最新成功基准”。
- `planning/` 成为唯一正式模型核心；`replay/` 和 `reliability/` 固定容量复用该模型。
- 结果指标由 `reporting/metrics.py` 统一计算，图和报告不得自行重复计算指标。
- CLI只提供工程研究入口，不继续扩展版本号式命令。
- 所有测试改用显式fixture路径，禁止 `glob("*.xlsx")[0]` 选择不确定工作簿。

### Risks & Dependencies

- **气象再分析偏差**：ERA5不是场站实测。缓解方式是NASA月度交叉检查、容量因子合理性审计和结果敏感性。
- **合成负荷误解**：公开资料无法提供具体园区SCADA。缓解方式是字段级可信度标签、校准表和场景敏感性，最终材料明确“公开数据驱动的重构算例”。
- **MILP规模**：全年多能耦合模型可能产生数万二进制变量。缓解方式是代表时段规划、滚动回放、求解时限/MIP gap、慢流程标记和可验证降级路径。
- **国际造价本地化**：IRENA/IEA口径与国内项目边界不同。缓解方式是基准区间、人民币换算假设和±20%至±30%敏感性，不给出虚假精确值。
- **旧结果污染**：根目录、`outputs/`、`results_v1/` 和历史文档包含旧数据。缓解方式是运行白名单、哈希清单、只读隔离归档和发布门，不从这些路径读取正式输入。
- **用户现有改动**：`tests/test_excel_data_loader.py` 已有用户修改。实施时必须保留并在其基础上增量修改。

## Implementation Units

### Unit Index

| U-ID | 标题 | 主要文件 | 依赖 |
|---|---|---|---|
| U1 | 建立最新基准与污染隔离 | `src/zero_carbon_park/config.py`, `tests/conftest.py` | 无 |
| U2 | 建立来源注册表 | `src/zero_carbon_park/data/sources.py`, `data/metadata/` | U1 |
| U3 | 重建8784小时气象管道 | `src/zero_carbon_park/data/annual_pipeline.py`, `scripts/build_codex_data_workbook.py` | U1—U2 |
| U4 | 构建负荷和技术经济参数 | `src/zero_carbon_park/data/generator.py`, `src/zero_carbon_park/planning/cost_params.py` | U2—U3 |
| U5 | 统一并修正规划模型 | `src/zero_carbon_park/planning/` | U1、U4 |
| U6 | 生成并验证代表时段 | `src/zero_carbon_park/typical_days/` | U3—U5 |
| U7 | 求解三类容量方案 | `src/zero_carbon_park/planning/runner.py` | U5—U6 |
| U8 | 实现8784小时滚动回放 | `src/zero_carbon_park/replay/` | U5、U7 |
| U9 | 实现孤网保供评估 | `src/zero_carbon_park/reliability/` | U5、U8 |
| U10 | 统一经济、碳和可靠性指标 | `src/zero_carbon_park/reporting/metrics.py` | U7—U9 |
| U11 | 生成静态工程成果 | `src/zero_carbon_park/reporting/` | U10 |
| U12 | 发布最新基准与秋招材料 | `README.md`, `项目总结汇总/` | U1—U11 |

### U1. 建立最新基准与污染隔离

**Goal**：让任何正式运行只能读取显式登记的最新数据，先消除根目录Excel和历史结果的隐式污染。

**Requirements**：R2、R3、R21。

**Files**：修改 `src/zero_carbon_park/config.py`、`src/zero_carbon_park/cli.py`；新增 `tests/conftest.py`、`tests/test_run_manifest.py`。

**Approach**：定义研究年度、路径、规模、容量边界、求解器参数和运行ID。测试fixture使用明确文件名。正式运行生成 `manifest.json`，列出唯一输入、哈希、代码版本和被排除历史路径。实施前先列出旧产物；不在本单元自动递归删除。

**Test Scenarios**：根目录出现多个Excel；`outputs/`存在同名CSV；清单引用文件哈希变化；清单缺少来源ID。

**Verification**：`python -m pytest -q tests/test_run_manifest.py tests/test_excel_data_loader.py`。

### U2. 建立来源注册表

**Goal**：建立字段级数据来源和可信度体系。

**Requirements**：R3—R5、R17、R18。

**Files**：新增 `src/zero_carbon_park/data/sources.py`、`data/metadata/source_registry.csv`、`data/metadata/assumptions.yaml`、`docs/data_methodology.md`。

**Approach**：为每个字段记录 `source_id`、来源类别、URL、发布日期、获取时间、原单位、目标单位、时区、处理方法、转换公式、文件哈希、适用年度、可信度和备注。政策参数带生效日期；工程假设带上下界。

**Test Scenarios**：来源URL为空；目标单位、时区、处理方法或文件哈希为空；政策参数超出适用期；工程假设被误标为实测；同一字段存在两个有效主来源。

**Verification**：新增注册表schema测试并人工抽查气象、电价、碳因子、天然气和电解槽五类条目。

### U3. 重建8784小时气象管道

**Goal**：从官方源重新获得2024年逐时数据，生成可直接被模型读取的规范主表。

**Requirements**：R1、R3、R4、R6。

**Files**：新增 `src/zero_carbon_park/data/annual_pipeline.py`；修改 `src/zero_carbon_park/data/loader.py`、`src/zero_carbon_park/data/validation.py`、`scripts/build_codex_data_workbook.py`、`pyproject.toml`；新增 `tests/test_annual_data_pipeline.py`。

**Approach**：在 `pyproject.toml` 声明 `cdsapi` 和 `pvlib`。正式下载前预检CDS凭据和数据条款授权；预检失败时不写入任何原始或处理文件。下载覆盖北京时间年界的ERA5数据，保留UTC并转换为北京时间。由100 m U/V分量计算风速。Global Wind Atlas长期均值只用于可追溯偏差校准，并同时保留未校准风速结果做敏感性，避免把单一比例校正当作场站实测。使用 `pvlib` 根据太阳辐射、温度、倾角、方位角、DC/AC比和系统损失计算PV容量因子。输出 `data/raw/weather/` 原始响应、`data/processed/annual_timeseries_2024.csv`、质量报告和人读Excel。NASA POWER重新下载后仅做月度校核。自动化测试只使用固定下载fixture，不依赖实时网络。

**Test Scenarios**：CDS凭据或条款授权缺失；闰日缺失；UTC转本地年界少8小时；辐射单位误用；`-999`或NaN；风光容量因子越界；重复下载结果不一致；测试环境断网。

**Verification**：`python -m pytest -q tests/test_annual_data_pipeline.py`；质量报告通过8784小时、时间连续、单位、范围和哈希检查。

### U4. 构建负荷和技术经济参数

**Goal**：用透明方法生成与公开证据或声明情景相匹配的园区算例，并使容量边界和成本参数与负荷尺度一致。

**Requirements**：R3—R6、R17、R18。

**Files**：修改 `src/zero_carbon_park/data/generator.py`、`src/zero_carbon_park/planning/cost_params.py`、`src/zero_carbon_park/config.py`；新增 `tests/test_load_reconstruction.py`、`tests/test_cost_parameter_sources.py`。

**Approach**：先检索最新公开的园区能耗、项目容量或产能资料并形成尺度证据卡，再按KTD5确定基准规模。把电、热、氢负荷拆成可解释分量。所有峰值和年总量作为配置校准目标，不写死在代码。更新蒙西电价、输配电价、需量电价、天然气、碳因子、CAPEX、寿命、效率和固定运维。给出基准、低、高三档。

**Test Scenarios**：年度电量不等于逐时积分；热负荷对低温不敏感；节假日产生负值；容量上限低于强制负荷所需；成本参数缺来源。

**Verification**：负荷年总量与配置目标偏差不高于1%；输出月度统计、持续曲线和参数来源表。

### U5. 统一并修正规划模型

**Goal**：形成规划、回放和可靠性共用的物理约束核心。

**Requirements**：R7—R10、R12—R16。

**Files**：修改 `src/zero_carbon_park/planning/builder.py`、`variables.py`、`constraints.py`、`objective.py`、`cost_params.py`、`src/zero_carbon_park/models/performance_curves.py`、`src/zero_carbon_park/optimization/solver.py`；新增 `tests/test_planning_physics.py`。

**Approach**：容量变量由配置控制自由或固定。增加并网限额、储能互斥、储氢速率和互斥、可用率、分级失负荷、状态入口/出口接口、设备爬坡和最小负荷。修正分段效率。求解器记录时限、MIP gap、终止状态和日志。

**Test Scenarios**：电池和储氢同时充放；外购氢掩盖孤网缺口；电网无限购电；分段曲线跳到最优段；故障设备仍有出力；窗口状态未传入。

**Verification**：`python -m pytest -q tests/test_planning_physics.py tests/test_v0_4_planning_model_upgrades.py`。

### U6. 生成并验证代表时段

**Goal**：用真实全年日期替换人工缩放的三个典型日。

**Requirements**：R11。

**Files**：修改 `src/zero_carbon_park/typical_days/definitions.py`、`generator.py`、`runner.py`、`pyproject.toml`；新增 `clustering.py`、`diagnostics.py`、`tests/test_representative_periods.py`。

**Approach**：在 `pyproject.toml` 声明 `scikit-learn`。对PV、风电、电负荷、热负荷、氢负荷和电价进行按特征组标准化。按KTD6构造8、12、16天最终集合；每个集合先纳入4个强制极端日，再从其余日期聚类补足。中心映射到真实日期。重新分配权重，生成原始366日到代表日的顺序映射和相邻代表日转移计数。模型计算每个代表日的状态增量，并约束按原始日序累计后的SOC和储氢库存始终在上下界内，年末与年初循环。输出持续曲线、分位数、年总量和跨期库存误差。

**Test Scenarios**：权重不等于366；代表日不是原始日期；极端日被聚类覆盖掉；随机种子改变结果；某类量纲主导聚类；储氢在每个代表日边界被无成本重置；转移计数不能重构366日序列。

**Verification**：`python -m pytest -q tests/test_representative_periods.py`；满足Success Criteria中的聚类误差门。

### U7. 求解三类容量方案

**Goal**：得到经济型、低碳型和韧性型三个容量组合。

**Requirements**：R7—R11、R17—R19。

**Files**：修改 `src/zero_carbon_park/planning/runner.py`、`pareto.py`、`sensitivity.py`、`results.py`；新增 `tests/test_engineering_portfolios.py`。

**Approach**：先求经济型的最小等年值总成本。低碳型在等年值总成本不超过经济型110%的约束下最小化运行碳排放。韧性型最小化等年值总成本，同时要求24小时设计孤网事件的关键负荷供能率不低于99%，且自备可用电源容量不低于保安电负荷的120%。正式报告另将三方案与国家级零碳园区指标对标，但不把模型方案命名为政策认证结果。方案比较必须输出相对经济型的增量成本、减排量、ENS变化和适用条件；差异不显著时合并结论而不强行包装三个标签。所有方案保存容量、目标分解、约束松弛、求解状态和输入清单。

**Test Scenarios**：三个方案使用不同价格口径；低碳型成本超过经济型110%；碳目标只靠外送电抵扣；韧性型未满足99%关键负荷供能率或120%应急容量；韧性方案依赖无限外购氢；三个方案结果相同却被包装为独立方案；求解超时却被标为最优。

**Verification**：小型基准测试通过；正式求解的MIP gap和终止条件进入结果表。

### U8. 实现8784小时滚动回放

**Goal**：验证规划容量在连续全年时序中的可运行性。

**Requirements**：R12、R13、R21。

**Files**：新增 `src/zero_carbon_park/replay/__init__.py`、`runner.py`、`results.py`、`tests/test_full_year_replay.py`。

**Approach**：固定每个方案容量，按168小时窗口求解并提交前24小时。状态数据结构保存在 `runner.py`，结果契约保存在 `results.py`。传递SOC、储氢库存和必要的设备状态，并按KTD8设置尾段储能价值。进行年度循环预热。可行性问题通过高惩罚失负荷变量显式暴露，不以程序崩溃或静默截断处理。正常年回放要求ENS等于0；若ENS大于数值容差，或回放总成本相对KTD7下界超过10%，将最大缺口或最大成本偏差日期加入强制代表日集合并返回U6—U7重新规划。最多执行三次“规划—回放—补充极端日”闭环，仍不通过则停止发布并报告阻塞原因。

**Test Scenarios**：48/72小时微型数据跨窗口；窗口重叠重复；最后不足168小时；非末窗口在视野末端系统性放空；年末状态漂移；某小时容量越限；正常年ENS触发极端日回填和重新规划；三次闭环后仍失败；求解失败后结果仍被发布。

**Verification**：`python -m pytest -q tests/test_full_year_replay.py`；正式回放输出8784个唯一时间戳并通过平衡与连续性门。

### U9. 实现孤网保供评估

**Goal**：量化关键负荷在电网停电和设备故障下的保供能力。

**Requirements**：R14—R16。

**Files**：新增 `src/zero_carbon_park/reliability/definitions.py`、`runner.py`、`metrics.py`、`tests/test_reliability_events.py`、`tests/test_reliability_metrics.py`。

**Approach**：建立关键、重要、可中断负荷。事件定义集中在 `definitions.py`，结果结构和指标集中在 `metrics.py`。筛选月度高净负荷、最低SOC、最低储氢、极寒和低风低光起点，再对2、4、8、24小时孤网事件求解。增加电池、燃料电池、热泵、电解槽故障和外购氢受限复合事件。

**Test Scenarios**：停电时仍购售电；失负荷顺序错误；事件未继承事前状态；设备故障未降额；24小时事件比8小时事件的ENS更小且无物理原因；确定性指标被命名为EENS。

**Verification**：`python -m pytest -q tests/test_reliability_events.py tests/test_reliability_metrics.py`；人工核对一个可手算微型孤网算例。

### U10. 统一经济、碳和可靠性指标

**Goal**：保证表格、图和报告使用同一计算口径。

**Requirements**：R16—R19、R21。

**Files**：实现 `src/zero_carbon_park/reporting/metrics.py`；修改 `export.py`；新增 `tests/test_engineering_comparison.py`。

**Approach**：统一计算等年值CAPEX、固定/可变OPEX、购售能、需量费、弃电、可再生能源占比、绿电自给率、企业范围一和范围二位置法、国家级零碳园区验收口径、ENS、失供小时、关键负荷供能率、最大连续失供时长、SOC最低值和孤网生存时长。两套碳口径分别输出天然气直接排放、净购电、绿电和抵消量。每项指标保存公式版本和输入列。

**Test Scenarios**：成本分项不等于总成本；天然气排放重复计入；外送电错误抵扣范围二；0.6479与0.8325因子混入同一碳结果；国家级口径缺少绿电或抵消量分项；失供小时、最大连续失供时长或SOC最低值漏算；不同方案分母不同；碳价被计为真实收益。

**Verification**：`python -m pytest -q tests/test_engineering_comparison.py`；手工复算一个24小时微型结果。

### U11. 生成静态工程成果

**Goal**：用专业静态图表和技术报告呈现模型深度。

**Requirements**：R19—R21。

**Files**：修改 `src/zero_carbon_park/reporting/plots.py`；新增 `engineering_report.py`、`tests/test_engineering_pipeline.py`。

**Approach**：固定生成以下成果：

1. 8784小时风光与三类负荷持续曲线。
2. 代表时段覆盖、极端日和重构误差图。
3. 三方案容量配置与等年值成本堆叠图。
4. 月度购电、弃电、可再生能源占比和碳排放图。
5. 电池SOC与储氢库存年度热图或持续曲线。
6. 极端周电—热—氢调度堆叠图。
7. 停电时长—关键负荷供能率和ENS曲线。
8. 成本—碳—可靠性Pareto或气泡图。
9. 关键参数敏感性龙卷风图。

图表统一中文字体、单位、颜色和来源脚注。报告正文区分事实、模型结果和工程假设。

**Test Scenarios**：空序列；8784点图过密；单位混用；图表自行重算指标；旧 `scenario_id` 出现在主报告；图表引用非最新运行目录。

**Verification**：`python -m pytest -q tests/test_engineering_pipeline.py tests/test_plot_empty_series.py`；人工查看全部PNG/PDF，无截字、错轴、乱码和旧版本标签。

### U12. 发布最新基准与秋招材料

**Goal**：只发布一次通过全部门槛的最新结果，并形成面向能源央国企的项目表述。

**Requirements**：R2、R19—R21。

**Files**：修改 `README.md`、`项目总结汇总/` 下的项目总结；将U1清单明确列出的 `outputs/`、`results_v1/` 及其他历史生成产物移入只读隔离归档；新增 `artifacts/latest.json`、正式技术报告、结果摘要、简历表述和面试问答。源码、兼容API、测试和原始用户文档不属于历史产物处理范围。

**Approach**：运行全量慢流程到独立运行目录，全部发布门通过后才原子更新 `artifacts/latest.json`。消费U1生成的历史产物清单，逐项记录归档目标及处理结果；执行前验证目标绝对路径位于仓库和清单允许范围内。默认只把历史结果移入只读隔离归档并确认正式链路不引用；任何实际删除必须列出精确路径并再次取得用户批准。保留现有测试覆盖的 `models.*`、`optimization.*`、`scenarios.*` 和旧runner导入面作为调用统一核心的兼容API，但从默认CLI、主报告和正式发布路径移除S0—S5。实施时从目标央国企官方招聘页抽取至少6个综合能源规划、新能源系统分析、能源管理/双碳或电力保供岗位，形成岗位—能力证据卡。简历描述采用“构建模型—数据基础—优化方法—验证方法—量化结果”的结构；实际数字仅从冻结结果自动填充，并标明个人完成部分。

**Test Scenarios**：README数字与结果表不一致；简历引用旧图；报告说“真实园区数据”；S0—S5成为主叙事；失败运行覆盖最新成功基准；简历要点无法映射到岗位要求；三方案只有标签不同而无工程差异。

**Verification**：运行所有非慢测试、全量工程研究和结果一致性检查；人工从每条简历数字反查到结果CSV；用岗位—能力证据卡审查一页式项目叙事，确认每条核心能力至少由一个模型结果或代码模块支撑。

## Verification Contract

### Incremental Tests

```powershell
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_run_manifest.py tests/test_excel_data_loader.py tests/test_annual_data_pipeline.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_load_reconstruction.py tests/test_cost_parameter_sources.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_representative_periods.py tests/test_planning_physics.py tests/test_v0_4_planning_model_upgrades.py tests/test_engineering_portfolios.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_full_year_replay.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_reliability_events.py tests/test_reliability_metrics.py
.\engrysystem-env\Scripts\python.exe -m pytest -q tests/test_engineering_comparison.py tests/test_engineering_pipeline.py tests/test_plot_empty_series.py
```

### Regression Gate

在 `pyproject.toml` 注册 `slow` 标记。日常回归运行：

```powershell
.\engrysystem-env\Scripts\python.exe -m pytest -q -m "not slow"
```

正式发布再单独运行数据下载、代表时段规划、三方案8784小时回放和可靠性事件集。正式命令必须输出：运行ID、输入哈希、Git提交、求解器版本、MIP gap、开始/结束时间和成功状态。

### Release Gates

1. **数据门**：R1—R6和8784小时质量检查全部通过。
2. **物理门**：能量平衡、容量边界、互斥和状态连续测试全部通过。
3. **规划门**：三个方案均有可解释的求解状态和容量结果。
4. **回放门**：三个方案均完成8784小时回放，正常年ENS等于0；可靠性事件中的失负荷被显式报告。
5. **可靠性门**：事件口径、初始状态和指标命名通过审计。
6. **结果门**：图、表、报告、README和简历数字来自同一运行ID。
7. **清理门**：旧结果不在最新发布路径；废弃实验代码和重复图已移除；用户已有代码改动未被覆盖。

## Definition of Done

- U1—U12的测试场景和验证命令全部完成。
- 只有一套最新基准被主报告和README引用。
- 数据来源注册表覆盖正式输入的全部字段。
- 三个容量方案均通过固定容量8784小时回放。
- 孤网保供结论使用ENS和关键负荷供能率等证据匹配指标。
- 静态报告和图表可独立说明数据、模型、结果和局限。
- 简历项目描述包含真实运行得到的量化结果，不含占位符和旧结果。
- 所有死路实验代码、临时monkeypatch和重复产物从正式链路中隔离；测试覆盖的旧导入面作为调用统一核心的兼容API保留。

## Sources

- [Copernicus ERA5 hourly data on single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview)
- [NASA POWER Hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/)
- [Global Wind Atlas](https://globalwindatlas.info/en/about/introduction)
- [pvlib ModelChain](https://pvlib-python.readthedocs.io/en/stable/reference/modelchain.html)
- [内蒙古发改委：蒙西电网分时电价政策](https://fgw.nmg.gov.cn/zfxxgk/fdzdgknr/bmwj/202111/t20211124_1960686.html)
- [国家发改委：第四监管周期省级电网输配电价](https://www.ndrc.gov.cn/xxgk/zcfb/tz/202607/t20260710_1406431.html)
- [国家发改委等：零碳园区建设通知](https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20523)
- [零碳园区碳排放核算方法](https://www.ndrc.gov.cn/xxgk/zcfb/tz/202507/P020250708509043380772.pdf)
- [生态环境部：2023年电力二氧化碳排放因子](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf)
- [鄂尔多斯市：2026年非居民用天然气销售价格](https://www.ordos.gov.cn/ordosml/szbm/sfzhggwyh_n/202605/t20260528_3900116.html)
- [GB/T 29328-2018 重要电力用户供电电源及自备应急电源配置技术规范](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=19D335A4694C9A856AB1FFAEA7F7A45F)
- [国家能源局：电力可靠性管理办法（暂行）](https://hbj.nea.gov.cn/xxgk/zcfg/202402/t20240208_240006.html)
- [GB/T 43794-2024 用户供电可靠性评价指标导则](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=CD0D3C646D6B4CCDF7F411AA30DF4DCE)
- [IRENA Renewable Power Generation Costs in 2024](https://www.irena.org/Publications/2025/Jun/Renewable-Power-Generation-Costs-in-2024)
- [IEA Global Hydrogen Review 2025](https://www.iea.org/reports/global-hydrogen-review-2025/executive-summary)
- [DOE PEM Electrolysis Technical Targets](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis)
- [Kotzur et al., Time series aggregation for energy system design: Modeling seasonal storage](https://doi.org/10.1016/j.apenergy.2018.01.023)
