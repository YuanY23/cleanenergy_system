"""S0-S5 场景定义模块。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioConfig:
    """单个场景的开关配置。"""

    scenario_id: str
    use_renewables: bool
    use_heat_pump: bool
    use_battery: bool
    use_hydrogen: bool
    use_fuel_cell: bool
    use_carbon_price: bool


def get_minimal_scenario_config(scenario_id: str) -> ScenarioConfig:
    """返回当前阶段支持的场景配置。"""

    normalized_id = scenario_id.upper()

    if normalized_id == "S0":
        # S0 是传统供能基准场景，只允许电网购电和燃气锅炉。
        return ScenarioConfig(
            scenario_id="S0",
            use_renewables=False,
            use_heat_pump=False,
            use_battery=False,
            use_hydrogen=False,
            use_fuel_cell=False,
            use_carbon_price=False,
        )

    if normalized_id == "S1":
        # S1 启用风电和光伏，但仍不启用热泵、储能和氢能。
        return ScenarioConfig(
            scenario_id="S1",
            use_renewables=True,
            use_heat_pump=False,
            use_battery=False,
            use_hydrogen=False,
            use_fuel_cell=False,
            use_carbon_price=False,
        )

    if normalized_id == "S2":
        # S2 在 S1 基础上加入电池储能。
        return ScenarioConfig(
            scenario_id="S2",
            use_renewables=True,
            use_heat_pump=False,
            use_battery=True,
            use_hydrogen=False,
            use_fuel_cell=False,
            use_carbon_price=False,
        )

    if normalized_id == "S3":
        # S3 在 S2 基础上加入电解槽、储氢罐和氢负荷。
        return ScenarioConfig(
            scenario_id="S3",
            use_renewables=True,
            use_heat_pump=False,
            use_battery=True,
            use_hydrogen=True,
            use_fuel_cell=False,
            use_carbon_price=False,
        )

    if normalized_id == "S4":
        # S4 加入燃料电池和热泵，形成电-热-氢-储完整耦合。
        return ScenarioConfig(
            scenario_id="S4",
            use_renewables=True,
            use_heat_pump=True,
            use_battery=True,
            use_hydrogen=True,
            use_fuel_cell=True,
            use_carbon_price=False,
        )

    if normalized_id == "S5":
        # S5 在 S4 基础上启用碳价成本，用于低碳调度对比。
        return ScenarioConfig(
            scenario_id="S5",
            use_renewables=True,
            use_heat_pump=True,
            use_battery=True,
            use_hydrogen=True,
            use_fuel_cell=True,
            use_carbon_price=True,
        )

    raise ValueError(f"当前阶段暂时只支持 S0-S5，收到: {scenario_id}")
