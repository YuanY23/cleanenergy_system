"""容量规划模型组装。"""

from __future__ import annotations

from collections.abc import Mapping

from pyomo.environ import ConcreteModel, Param, RangeSet, Set, value

from zero_carbon_park.models.parameters import parameter_frame_to_dict
from zero_carbon_park.models.performance_curves import (
    battery_degradation_segments,
    conversion_segments,
)
from zero_carbon_park.planning.constraints import add_planning_constraints
from zero_carbon_park.planning.cost_params import (
    PlanningCostParams,
    capital_recovery_factor,
)
from zero_carbon_park.planning.objective import add_capacity_planning_objective
from zero_carbon_park.planning.variables import (
    add_capacity_variables,
    add_operation_variables,
)


def build_capacity_planning_model(
    typical_days,
    cost_params: PlanningCostParams,
    annual_carbon_emission_cap_kg: float | None = None,
    *,
    capacity_mode: str = "free",
    fixed_capacities: Mapping[str, float] | None = None,
    capacity_upper_bounds: Mapping[str, float] | None = None,
    islanded: bool = False,
    allow_external_h2: bool | None = None,
    allow_hydrogen_shedding: bool = False,
    initial_battery_soc_kwh: float | Mapping[str, float] | None = None,
    final_battery_soc_kwh: float | Mapping[str, float] | None = None,
    initial_h2_inventory_kg: float | Mapping[str, float] | None = None,
    final_h2_inventory_kg: float | Mapping[str, float] | None = None,
    performance_curve_mode: str = "constant_efficiency",
    objective_mode: str = "economic",
    annual_total_cost_cap_cny: float | None = None,
    critical_supply_min_ratio: float | None = None,
    secure_capacity_multiplier: float | None = None,
    secure_battery_duration_hours: float | None = None,
    enforce_terminal_states: bool = True,
) -> ConcreteModel:
    """Build the common capacity/dispatch model.

    ``capacity_mode='free'`` performs capacity planning. ``'fixed'`` fixes every
    capacity and is the contract used by chronological replay and outage events.
    State values may be scalars or day-id mappings; omitted states retain the
    historical representative-day fractions (50% battery, 30% hydrogen).
    """

    if not typical_days:
        raise ValueError("容量规划至少需要一个典型日")
    if performance_curve_mode not in {"constant_efficiency", "ordered_incremental"}:
        raise ValueError(
            "performance_curve_mode must be constant_efficiency or ordered_incremental"
        )
    if objective_mode not in {"economic", "carbon"}:
        raise ValueError("objective_mode must be economic or carbon")
    if annual_total_cost_cap_cny is not None and annual_total_cost_cap_cny < 0.0:
        raise ValueError("annual_total_cost_cap_cny cannot be negative")
    if critical_supply_min_ratio is not None and not 0.0 <= critical_supply_min_ratio <= 1.0:
        raise ValueError("critical_supply_min_ratio must be within [0, 1]")
    if secure_capacity_multiplier is not None and secure_capacity_multiplier < 0.0:
        raise ValueError("secure_capacity_multiplier cannot be negative")
    if secure_battery_duration_hours is not None and secure_battery_duration_hours < 0.0:
        raise ValueError("secure_battery_duration_hours cannot be negative")

    first_workbook = typical_days[0][1]
    device = parameter_frame_to_dict(first_workbook.device_params)
    economic = parameter_frame_to_dict(first_workbook.economic_params)
    day_ids = [config.day_id for config, _ in typical_days]
    last_hour = len(first_workbook.timeseries) - 1

    model = ConcreteModel(name="capacity_planning")
    model.D = Set(initialize=day_ids, ordered=True)
    model.T = RangeSet(0, last_hour)
    model.islanded = bool(islanded)
    model.allow_external_h2 = bool(not islanded if allow_external_h2 is None else allow_external_h2)
    model.allow_hydrogen_shedding = bool(allow_hydrogen_shedding)
    model.performance_curve_mode = performance_curve_mode
    model.objective_mode = objective_mode
    model.enforce_terminal_states = bool(enforce_terminal_states)
    if islanded and model.allow_external_h2:
        raise ValueError("islanded operation cannot enable external hydrogen supply")

    _add_timeseries_params(model, typical_days, device, economic)
    model.critical_supply_min_ratio = Param(
        initialize=(
            float(critical_supply_min_ratio)
            if critical_supply_min_ratio is not None
            else 0.0
        )
    )
    model.secure_capacity_multiplier = Param(
        initialize=(
            float(secure_capacity_multiplier)
            if secure_capacity_multiplier is not None
            else 0.0
        )
    )
    model.secure_battery_duration_hours = Param(
        initialize=(
            float(secure_battery_duration_hours)
            if secure_battery_duration_hours is not None
            else 0.0
        )
    )
    model.peak_critical_load_kw = Param(
        initialize=max(
            float(value(model.critical_load[d, t])) for d in model.D for t in model.T
        )
    )
    _add_device_params(model, device)
    _add_economic_params(model, economic)
    _add_investment_params(model, cost_params)
    _add_performance_curve_params(model, device, economic, cost_params)
    _add_boundary_state_params(
        model,
        day_ids,
        initial_battery_soc_kwh=initial_battery_soc_kwh,
        final_battery_soc_kwh=final_battery_soc_kwh,
        initial_h2_inventory_kg=initial_h2_inventory_kg,
        final_h2_inventory_kg=final_h2_inventory_kg,
    )
    model.annual_carbon_emission_cap_kg = Param(
        initialize=(
            float(annual_carbon_emission_cap_kg)
            if annual_carbon_emission_cap_kg is not None
            else 1.0e15
        )
    )

    add_capacity_variables(
        model,
        capacity_mode=capacity_mode,
        fixed_capacities=fixed_capacities,
        capacity_upper_bounds=capacity_upper_bounds,
    )
    add_operation_variables(model)
    add_planning_constraints(model)
    add_capacity_planning_objective(
        model,
        objective_mode=objective_mode,
        annual_total_cost_cap_cny=annual_total_cost_cap_cny,
    )

    return model


def _add_timeseries_params(
    model: ConcreteModel,
    typical_days,
    device: dict[str, float],
    economic: dict[str, float],
) -> None:
    """写入多典型日时间序列参数。"""

    by_day = {config.day_id: (config, workbook.timeseries.reset_index(drop=True)) for config, workbook in typical_days}

    model.weight_days = Param(model.D, initialize={d: by_day[d][0].weight_days for d in model.D})
    for column, param_name in [
        ("pv_cf", "pv_cf"),
        ("wind_cf", "wind_cf"),
        ("electric_load_kw", "electric_load"),
        ("heat_load_kw", "heat_load"),
        ("hydrogen_load_kg", "hydrogen_load"),
        ("electricity_price_cny_per_kwh", "grid_price"),
        ("gas_price_cny_per_m3", "gas_price"),
        ("grid_emission_kgco2_per_kwh", "grid_emission_factor"),
    ]:
        setattr(
            model,
            param_name,
            Param(
                model.D,
                model.T,
                initialize={(d, t): float(by_day[d][1].loc[t, column]) for d in model.D for t in model.T},
            ),
        )

    tier_columns = {
        "critical_load": "critical_load_kw",
        "important_load": "important_load_kw",
        "interruptible_load": "interruptible_load_kw",
    }
    for param_name, column in tier_columns.items():
        values = {}
        for d in model.D:
            frame = by_day[d][1]
            explicit_tiers = all(name in frame.columns for name in tier_columns.values())
            for t in model.T:
                if explicit_tiers:
                    selected = float(frame.loc[t, column])
                elif param_name == "important_load":
                    selected = float(frame.loc[t, "electric_load_kw"])
                else:
                    selected = 0.0
                if selected < 0.0:
                    raise ValueError(f"{column} cannot be negative")
                values[(d, t)] = selected
        setattr(model, param_name, Param(model.D, model.T, initialize=values))

    for d in model.D:
        frame = by_day[d][1]
        if all(name in frame.columns for name in tier_columns.values()):
            tier_sum = frame[list(tier_columns.values())].sum(axis=1)
            if not (tier_sum - frame["electric_load_kw"]).abs().le(1.0e-6).all():
                raise ValueError("tiered electric loads must sum to electric_load_kw")

    model.carbon_price = Param(
        model.D,
        model.T,
        initialize={
            (d, t): float(by_day[d][1].loc[t, "carbon_price_cny_per_tco2"]) / 1000.0
            for d in model.D
            for t in model.T
        },
    )

    for column, param_name, default in [
        ("heat_pump_cop", "heat_pump_cop", device["heat_pump_COP"]),
        ("heat_pump_available_ratio", "heat_pump_available_ratio", 1.0),
        (
            "electrolyzer_kwh_per_kg",
            "electrolyzer_kwh_per_kg",
            device["electrolyzer_kWh_per_kgH2"],
        ),
        (
            "fuel_cell_kwh_per_kg",
            "fuel_cell_kwh_per_kg",
            device["fuel_cell_KWh_per_kgH2"]
            if "fuel_cell_KWh_per_kgH2" in device
            else device["fuel_cell_kWh_per_kgH2"],
        ),
        (
            "grid_sell_price_cny_per_kwh",
            "grid_sell_price",
            economic.get("grid_sell_price_cny_per_kwh", 0.0),
        ),
        ("pv_available_ratio", "pv_available_ratio", 1.0),
        ("wind_available_ratio", "wind_available_ratio", 1.0),
        ("battery_available_ratio", "battery_available_ratio", 1.0),
        ("electrolyzer_available_ratio", "electrolyzer_available_ratio", 1.0),
        ("fuel_cell_available_ratio", "fuel_cell_available_ratio", 1.0),
        ("grid_available_ratio", "grid_available_ratio", 1.0),
        ("h2_external_available_ratio", "h2_external_available_ratio", 1.0),
        ("gas_boiler_available_ratio", "gas_boiler_available_ratio", 1.0),
    ]:
        values = {
            (d, t): _timeseries_value(by_day[d][1], t, column, default)
            for d in model.D
            for t in model.T
        }
        if param_name.endswith("available_ratio") and any(
            not 0.0 <= selected <= 1.0 for selected in values.values()
        ):
            raise ValueError(f"{column} must be within [0, 1]")
        setattr(
            model,
            param_name,
            Param(
                model.D,
                model.T,
                initialize=values,
            ),
        )


def _add_device_params(model: ConcreteModel, device: dict[str, float]) -> None:
    """写入设备效率和固定容量参数。"""

    model.gas_boiler_heat_max = Param(initialize=float(device["gas_boiler_heat_kW"]))
    model.gas_boiler_eff = Param(initialize=float(device["gas_boiler_eff"]))
    model.gas_lhv = Param(initialize=float(device["gas_lhv_kwh_per_m3"]))
    model.battery_eta_ch = Param(initialize=float(device["battery_eta_ch"]))
    model.battery_eta_dis = Param(initialize=float(device["battery_eta_dis"]))
    model.electrolyzer_min_load_rate = Param(
        initialize=float(device.get("electrolyzer_min_load_rate", 0.0))
    )
    model.fuel_cell_min_load_rate = Param(
        initialize=float(device.get("fuel_cell_min_load_rate", 0.0))
    )
    model.h2_storage_loss_rate_per_hour = Param(
        initialize=float(device.get("h2_storage_loss_rate_per_hour", 0.0))
    )
    model.h2_storage_charge_rate_per_hour = Param(
        initialize=float(device.get("h2_storage_charge_rate_per_hour", 1.0))
    )
    model.h2_storage_discharge_rate_per_hour = Param(
        initialize=float(device.get("h2_storage_discharge_rate_per_hour", 1.0))
    )
    model.electrolyzer_ramp_rate_per_hour = Param(
        initialize=float(device.get("electrolyzer_ramp_rate_per_hour", 1.0))
    )
    model.fuel_cell_ramp_rate_per_hour = Param(
        initialize=float(device.get("fuel_cell_ramp_rate_per_hour", 1.0))
    )


def _add_economic_params(model: ConcreteModel, economic: dict[str, float]) -> None:
    """写入运行经济参数。"""

    model.gas_emission_factor = Param(initialize=float(economic["gas_emission_factor"]))
    model.curtail_penalty = Param(initialize=float(economic["curtail_penalty"]))
    model.battery_om = Param(initialize=float(economic["battery_om"]))
    model.electrolyzer_om = Param(initialize=float(economic["electrolyzer_om"]))
    model.fuel_cell_om = Param(initialize=float(economic["fuel_cell_om"]))
    model.h2_external_supply_cost = Param(
        initialize=float(economic.get("h2_external_supply_cost", 1000.0))
    )
    model.hydrogen_unserved_penalty = Param(
        initialize=float(
            economic.get("hydrogen_unserved_penalty_cny_per_kg", 100_000.0)
        )
    )
    model.green_power_min_share = Param(
        initialize=float(economic.get("green_power_min_share", 0.0))
    )
    model.critical_load_shed_penalty = Param(
        initialize=float(economic.get("critical_load_shed_penalty_cny_per_kwh", 100_000.0))
    )
    model.important_load_shed_penalty = Param(
        initialize=float(economic.get("important_load_shed_penalty_cny_per_kwh", 10_000.0))
    )
    model.interruptible_load_shed_penalty = Param(
        initialize=float(economic.get("interruptible_load_shed_penalty_cny_per_kwh", 1_000.0))
    )


def _add_performance_curve_params(
    model: ConcreteModel,
    device: dict[str, float],
    economic: dict[str, float],
    cost_params: PlanningCostParams,
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
    model.ELECTROLYZER_ORDERED_SEGMENTS = Set(
        initialize=[segment.index for segment in electrolyzer_segments[1:]], ordered=True
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
    model.FUEL_CELL_ORDERED_SEGMENTS = Set(
        initialize=[segment.index for segment in fuel_cell_segments[1:]], ordered=True
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
        fallback_cost_cny_per_kwh=cost_params.battery_degradation_cost_cny_per_kwh,
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


def _add_investment_params(
    model: ConcreteModel,
    cost_params: PlanningCostParams,
) -> None:
    """写入年化投资成本参数。"""

    rate = cost_params.discount_rate
    model.wind_capex_annual_cny_per_kw = Param(
        initialize=cost_params.wind_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.wind_life_years)
    )
    model.pv_capex_annual_cny_per_kw = Param(
        initialize=cost_params.pv_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.pv_life_years)
    )
    battery_crf = capital_recovery_factor(rate, cost_params.battery_life_years)
    model.battery_power_capex_annual_cny_per_kw = Param(
        initialize=cost_params.battery_power_capex_cny_per_kw * battery_crf
    )
    model.battery_energy_capex_annual_cny_per_kwh = Param(
        initialize=cost_params.battery_energy_capex_cny_per_kwh * battery_crf
    )
    model.electrolyzer_capex_annual_cny_per_kw = Param(
        initialize=cost_params.electrolyzer_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.electrolyzer_life_years)
    )
    model.h2_storage_capex_annual_cny_per_kg = Param(
        initialize=cost_params.h2_storage_capex_cny_per_kg
        * capital_recovery_factor(rate, cost_params.h2_storage_life_years)
    )
    model.fuel_cell_capex_annual_cny_per_kw = Param(
        initialize=cost_params.fuel_cell_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.fuel_cell_life_years)
    )
    model.heat_pump_capex_annual_cny_per_kw = Param(
        initialize=cost_params.heat_pump_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.heat_pump_life_years)
    )
    model.battery_degradation_cost_cny_per_kwh = Param(
        initialize=cost_params.battery_degradation_cost_cny_per_kwh
    )
    model.fuel_cell_backup_value_cny_per_kw_year = Param(
        initialize=cost_params.fuel_cell_backup_value_cny_per_kw_year
    )
    model.fuel_cell_backup_reserve_kw = Param(
        initialize=cost_params.fuel_cell_backup_reserve_kw
    )
    model.fuel_cell_backup_required_kw = Param(
        initialize=cost_params.fuel_cell_backup_required_kw
    )
    model.grid_export_limit_kw = Param(initialize=cost_params.grid_export_limit_kw)
    model.grid_import_limit_kw = Param(
        initialize=0.0 if model.islanded else cost_params.grid_import_limit_kw
    )
    model.h2_external_supply_limit_kg_per_hour = Param(
        initialize=(
            cost_params.h2_external_supply_limit_kg_per_hour
            if model.allow_external_h2
            else 0.0
        )
    )
    model.demand_charge_cny_per_kw_year = Param(
        initialize=cost_params.demand_charge_cny_per_kw_year
    )


def _timeseries_value(frame, row_index: int, column: str, default: float) -> float:
    if column in frame.columns:
        return float(frame.loc[row_index, column])
    return float(default)


def _add_boundary_state_params(
    model: ConcreteModel,
    day_ids: list[str],
    *,
    initial_battery_soc_kwh,
    final_battery_soc_kwh,
    initial_h2_inventory_kg,
    final_h2_inventory_kg,
) -> None:
    boundaries = {
        "initial_battery_soc_kwh": (initial_battery_soc_kwh, 0.5),
        "final_battery_soc_kwh": (final_battery_soc_kwh, 0.5),
        "initial_h2_inventory_kg": (initial_h2_inventory_kg, 0.3),
        "final_h2_inventory_kg": (final_h2_inventory_kg, 0.3),
    }
    model._absolute_boundary_state = {}
    for name, (raw, fraction) in boundaries.items():
        absolute = raw is not None
        if raw is None:
            values = {day_id: float(fraction) for day_id in day_ids}
        elif isinstance(raw, Mapping):
            missing = set(day_ids) - set(raw)
            if missing:
                raise ValueError(f"{name} is missing day ids: {sorted(missing)}")
            values = {day_id: float(raw[day_id]) for day_id in day_ids}
        else:
            values = {day_id: float(raw) for day_id in day_ids}
        if any(selected < 0.0 for selected in values.values()):
            raise ValueError(f"{name} cannot be negative")
        setattr(model, name, Param(model.D, initialize=values))
        model._absolute_boundary_state[name] = absolute
