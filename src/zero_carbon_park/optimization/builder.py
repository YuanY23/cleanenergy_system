"""MILP 模型组装模块。"""

from __future__ import annotations

import pandas as pd
from pyomo.environ import ConcreteModel, Param, Set

from zero_carbon_park.models.constraints_carbon import add_carbon_constraints
from zero_carbon_park.models.constraints_heat import add_heat_constraints
from zero_carbon_park.models.constraints_hydrogen import add_hydrogen_constraints
from zero_carbon_park.models.constraints_power import (
    add_power_balance_constraints,
    add_renewable_constraints,
)
from zero_carbon_park.models.constraints_storage import add_battery_constraints
from zero_carbon_park.models.objective import add_total_cost_objective
from zero_carbon_park.models.parameters import parameter_frame_to_dict
from zero_carbon_park.models.performance_curves import (
    battery_degradation_segments,
    conversion_segments,
)
from zero_carbon_park.models.sets import add_time_set
from zero_carbon_park.models.variables import add_decision_variables
from zero_carbon_park.scenarios.definitions import ScenarioConfig


def build_minimal_milp_model(
    timeseries: pd.DataFrame,
    device_params: pd.DataFrame,
    economic_params: pd.DataFrame,
    scenario: ScenarioConfig,
) -> ConcreteModel:
    """构建当前阶段的 MILP 模型。

    当前支持 S0-S3：
    - S0：电网 + 燃气锅炉
    - S1：S0 + 风电光伏
    - S2：S1 + 电池储能
    - S3：S2 + 电解槽 + 储氢罐 + 氢负荷
    - S4：S3 + 燃料电池 + 热泵
    - S5：S4 + 碳价成本
    """

    device = parameter_frame_to_dict(device_params)
    economic = parameter_frame_to_dict(economic_params)
    data = timeseries.reset_index(drop=True)
    last_hour = len(data) - 1

    model = ConcreteModel(name=f"milp_{scenario.scenario_id}")

    add_time_set(model, last_hour)

    # 场景开关转为 0/1 参数，方便统一写约束。
    renewable_enabled = 1.0 if scenario.use_renewables else 0.0
    heat_pump_enabled = 1.0 if scenario.use_heat_pump else 0.0
    battery_enabled = 1.0 if scenario.use_battery else 0.0
    hydrogen_enabled = 1.0 if scenario.use_hydrogen else 0.0
    fuel_cell_enabled = 1.0 if scenario.use_fuel_cell else 0.0
    carbon_price_enabled = 1.0 if scenario.use_carbon_price else 0.0

    _add_timeseries_params(
        model,
        data,
        renewable_enabled,
        hydrogen_enabled,
        carbon_price_enabled,
        heat_pump_cop_default=float(device["heat_pump_COP"]),
    )
    _add_device_and_economic_params(
        model,
        device,
        economic,
        heat_pump_enabled,
        battery_enabled,
        hydrogen_enabled,
        fuel_cell_enabled,
    )
    _add_performance_curve_params(model, device, economic)
    add_decision_variables(model)
    add_renewable_constraints(model)
    add_heat_constraints(model)
    add_battery_constraints(model)
    add_hydrogen_constraints(model)
    add_power_balance_constraints(model)
    add_carbon_constraints(model)
    add_total_cost_objective(model)

    return model


def _add_timeseries_params(
    model: ConcreteModel,
    data: pd.DataFrame,
    renewable_enabled: float,
    hydrogen_enabled: float,
    carbon_price_enabled: float,
    heat_pump_cop_default: float,
) -> None:
    """把逐小时输入数据写入模型参数。"""

    model.electric_load = Param(
        model.T, initialize={t: float(data.loc[t, "electric_load_kw"]) for t in model.T}
    )
    model.heat_load = Param(
        model.T, initialize={t: float(data.loc[t, "heat_load_kw"]) for t in model.T}
    )
    model.heat_pump_cop = Param(
        model.T,
        initialize={
            t: _timeseries_value(data, t, "heat_pump_cop", heat_pump_cop_default)
            for t in model.T
        },
    )
    model.heat_pump_available_ratio = Param(
        model.T,
        initialize={
            t: _timeseries_value(data, t, "heat_pump_available_ratio", 1.0)
            for t in model.T
        },
    )
    model.hydrogen_load = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "hydrogen_load_kg"]) * hydrogen_enabled
            for t in model.T
        },
    )
    model.pv_available = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "pv_available_kw"]) * renewable_enabled for t in model.T
        },
    )
    model.wind_available = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "wind_available_kw"]) * renewable_enabled
            for t in model.T
        },
    )
    model.grid_price = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "electricity_price_cny_per_kwh"]) for t in model.T
        },
    )
    model.gas_price = Param(
        model.T,
        initialize={t: float(data.loc[t, "gas_price_cny_per_m3"]) for t in model.T},
    )
    model.grid_emission_factor = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "grid_emission_kgco2_per_kwh"]) for t in model.T
        },
    )
    model.carbon_price = Param(
        model.T,
        initialize={
            t: float(data.loc[t, "carbon_price_cny_per_tco2"])
            / 1000.0
            * carbon_price_enabled
            for t in model.T
        },
    )


def _add_device_and_economic_params(
    model: ConcreteModel,
    device: dict[str, float],
    economic: dict[str, float],
    heat_pump_enabled: float,
    battery_enabled: float,
    hydrogen_enabled: float,
    fuel_cell_enabled: float,
) -> None:
    """把设备参数和经济参数写入模型。"""

    model.heat_pump_power_max = Param(
        initialize=float(device["heat_pump_power_kW"]) * heat_pump_enabled
    )
    model.gas_boiler_heat_max = Param(initialize=float(device["gas_boiler_heat_kW"]))
    model.gas_boiler_eff = Param(initialize=float(device["gas_boiler_eff"]))
    model.gas_lhv = Param(initialize=float(device["gas_lhv_kwh_per_m3"]))

    model.battery_power_max = Param(
        initialize=float(device["battery_power_kW"]) * battery_enabled
    )
    model.battery_energy_max = Param(
        initialize=float(device["battery_energy_kWh"]) * battery_enabled
    )
    model.battery_eta_ch = Param(initialize=float(device["battery_eta_ch"]))
    model.battery_eta_dis = Param(initialize=float(device["battery_eta_dis"]))
    model.battery_initial_soc = Param(
        initialize=float(device["battery_initial_soc"]) * battery_enabled
    )

    model.electrolyzer_power_max = Param(
        initialize=float(device["electrolyzer_power_kW"]) * hydrogen_enabled
    )
    model.electrolyzer_kwh_per_kg = Param(
        initialize=float(device["electrolyzer_kWh_per_kgH2"])
    )
    model.electrolyzer_min_load_rate = Param(
        initialize=float(device.get("electrolyzer_min_load_rate", 0.0))
    )
    model.h2_storage_capacity = Param(
        initialize=float(device["h2_storage_capacity_kg"]) * hydrogen_enabled
    )
    model.h2_storage_initial = Param(
        initialize=float(device["h2_storage_initial_kg"]) * hydrogen_enabled
    )
    model.h2_storage_loss_rate_per_hour = Param(
        initialize=float(device.get("h2_storage_loss_rate_per_hour", 0.0))
    )
    model.fuel_cell_power_max = Param(
        initialize=float(device["fuel_cell_power_kW"]) * fuel_cell_enabled
    )
    model.fuel_cell_kwh_per_kg = Param(
        initialize=float(device["fuel_cell_kWh_per_kgH2"])
    )
    model.fuel_cell_min_load_rate = Param(
        initialize=float(device.get("fuel_cell_min_load_rate", 0.0))
    )

    model.gas_emission_factor = Param(initialize=float(economic["gas_emission_factor"]))
    model.curtail_penalty = Param(initialize=float(economic["curtail_penalty"]))
    model.battery_om = Param(initialize=float(economic["battery_om"]))
    model.electrolyzer_om = Param(initialize=float(economic["electrolyzer_om"]))
    model.fuel_cell_om = Param(initialize=float(economic["fuel_cell_om"]))
    model.h2_external_supply_cost = Param(
        # 外部补氢成本故意设置较高，只在本地制氢和储氢无法满足需求时启用。
        initialize=float(economic.get("h2_external_supply_cost", 1000.0))
    )
    model.h2_sale_price = Param(
        # 默认不启用售氢；v1.4 售氢场景通过 h2_sale_enabled 打开收益。
        initialize=float(economic.get("h2_sale_price", 0.0))
        * float(economic.get("h2_sale_enabled", 0.0))
    )
    model.carbon_emission_cap = Param(
        # 默认给一个很大的上限，相当于不启用碳排放总量约束。
        initialize=float(economic.get("carbon_emission_cap_kg", 1.0e12))
    )
    model.carbon_cap_excess_penalty = Param(
        # 碳约束超额惩罚设高，用于优先满足约束；若物理不可行则暴露超额量。
        initialize=float(economic.get("carbon_cap_excess_penalty", 10000.0))
    )
    model.renewable_min_consumption_rate = Param(
        # 默认最低消纳率为 0，不影响既有场景。
        initialize=float(economic.get("renewable_min_consumption_rate", 0.0))
    )


def _add_performance_curve_params(
    model: ConcreteModel,
    device: dict[str, float],
    economic: dict[str, float],
) -> None:
    electrolyzer_segments = conversion_segments(
        device,
        prefix="electrolyzer",
        fallback_kwh_per_kg=float(device["electrolyzer_kWh_per_kgH2"]),
    )
    model.ELECTROLYZER_SEGMENTS = Set(
        initialize=[segment.index for segment in electrolyzer_segments],
        ordered=True,
    )
    model.electrolyzer_segment_power_fraction = Param(
        model.ELECTROLYZER_SEGMENTS,
        initialize={
            segment.index: segment.width_rate for segment in electrolyzer_segments
        },
    )
    model.electrolyzer_segment_kwh_per_kg = Param(
        model.ELECTROLYZER_SEGMENTS,
        initialize={
            segment.index: segment.kwh_per_kg for segment in electrolyzer_segments
        },
    )

    fuel_cell_segments = conversion_segments(
        device,
        prefix="fuel_cell",
        fallback_kwh_per_kg=float(device["fuel_cell_kWh_per_kgH2"]),
    )
    model.FUEL_CELL_SEGMENTS = Set(
        initialize=[segment.index for segment in fuel_cell_segments],
        ordered=True,
    )
    model.fuel_cell_segment_power_fraction = Param(
        model.FUEL_CELL_SEGMENTS,
        initialize={segment.index: segment.width_rate for segment in fuel_cell_segments},
    )
    model.fuel_cell_segment_kwh_per_kg = Param(
        model.FUEL_CELL_SEGMENTS,
        initialize={segment.index: segment.kwh_per_kg for segment in fuel_cell_segments},
    )

    degradation_segments = battery_degradation_segments(
        economic,
        fallback_cost_cny_per_kwh=float(
            economic.get("battery_degradation_cost_cny_per_kwh", 0.0)
        ),
    )
    model.BATTERY_DEGRADATION_SEGMENTS = Set(
        initialize=[segment.index for segment in degradation_segments],
        ordered=True,
    )
    model.battery_degradation_segment_width_rate = Param(
        model.BATTERY_DEGRADATION_SEGMENTS,
        initialize={segment.index: segment.width_rate for segment in degradation_segments},
    )
    model.battery_degradation_segment_cost = Param(
        model.BATTERY_DEGRADATION_SEGMENTS,
        initialize={
            segment.index: segment.cost_cny_per_kwh for segment in degradation_segments
        },
    )


def _timeseries_value(
    frame: pd.DataFrame, row_index: int, column: str, default: float
) -> float:
    if column in frame.columns:
        return float(frame.loc[row_index, column])
    return float(default)
