"""Capacity and dispatch variables shared by planning, replay and reliability."""

from __future__ import annotations

from collections.abc import Mapping

from pyomo.environ import Binary, ConcreteModel, NonNegativeReals, Var


CAPACITY_BOUNDS = {
    # Backwards-compatible defaults for the legacy 24 h demonstration. The
    # formal park-scale study passes explicit, auditable upper bounds from config.
    "wind_capacity_kw": 30_000.0,
    "pv_capacity_kw": 30_000.0,
    "battery_power_capacity_kw": 15_000.0,
    "battery_energy_capacity_kwh": 60_000.0,
    "electrolyzer_power_capacity_kw": 10_000.0,
    "h2_storage_capacity_kg": 5_000.0,
    "fuel_cell_power_capacity_kw": 5_000.0,
    "heat_pump_power_capacity_kw": 10_000.0,
}


def add_capacity_variables(
    model: ConcreteModel,
    *,
    capacity_mode: str = "free",
    fixed_capacities: Mapping[str, float] | None = None,
    capacity_upper_bounds: Mapping[str, float] | None = None,
) -> None:
    """Add capacity decisions, optionally fixing them for replay/event studies."""

    if capacity_mode not in {"free", "fixed"}:
        raise ValueError("capacity_mode must be 'free' or 'fixed'")
    explicit_bounds = dict(capacity_upper_bounds or {})
    bounds = {**CAPACITY_BOUNDS, **explicit_bounds}
    unknown = set(bounds) - set(CAPACITY_BOUNDS)
    if unknown:
        raise ValueError(f"unknown capacity upper bounds: {sorted(unknown)}")
    fixed = dict(fixed_capacities or {})
    unknown_fixed = set(fixed) - set(CAPACITY_BOUNDS)
    if unknown_fixed:
        raise ValueError(f"unknown fixed capacities: {sorted(unknown_fixed)}")
    if capacity_mode == "fixed" and set(fixed) != set(CAPACITY_BOUNDS):
        missing = sorted(set(CAPACITY_BOUNDS) - set(fixed))
        raise ValueError(f"fixed capacity mode requires every capacity: {missing}")
    if capacity_mode == "fixed":
        for name, selected in fixed.items():
            if name not in explicit_bounds:
                bounds[name] = max(bounds[name], float(selected))

    for name in CAPACITY_BOUNDS:
        upper = float(bounds[name])
        if upper <= 0.0:
            raise ValueError(f"capacity upper bound must be positive: {name}")
        variable = Var(domain=NonNegativeReals, bounds=(0.0, upper))
        setattr(model, name, variable)
        if capacity_mode == "fixed":
            selected = float(fixed[name])
            if not 0.0 <= selected <= upper:
                raise ValueError(f"fixed capacity outside bounds: {name}={selected}")
            variable.fix(selected)

    model.capacity_mode = capacity_mode
    model.capacity_upper_bounds = bounds


def add_operation_variables(model: ConcreteModel) -> None:
    """添加多典型日逐小时运行变量。"""

    model.grid_buy = Var(model.D, model.T, domain=NonNegativeReals)
    model.grid_sell = Var(model.D, model.T, domain=NonNegativeReals)
    model.grid_import_peak_kw = Var(domain=NonNegativeReals)
    model.pv_used = Var(model.D, model.T, domain=NonNegativeReals)
    model.pv_sold = Var(model.D, model.T, domain=NonNegativeReals)
    model.pv_curtail = Var(model.D, model.T, domain=NonNegativeReals)
    model.wind_used = Var(model.D, model.T, domain=NonNegativeReals)
    model.wind_sold = Var(model.D, model.T, domain=NonNegativeReals)
    model.wind_curtail = Var(model.D, model.T, domain=NonNegativeReals)

    model.heat_pump_power = Var(model.D, model.T, domain=NonNegativeReals)
    model.heat_pump_heat = Var(model.D, model.T, domain=NonNegativeReals)
    model.gas_boiler_heat = Var(model.D, model.T, domain=NonNegativeReals)
    model.gas_consumption = Var(model.D, model.T, domain=NonNegativeReals)

    model.battery_charge = Var(model.D, model.T, domain=NonNegativeReals)
    model.battery_discharge = Var(model.D, model.T, domain=NonNegativeReals)
    model.battery_soc = Var(model.D, model.T, domain=NonNegativeReals)
    model.is_battery_charging = Var(model.D, model.T, domain=Binary)

    model.electrolyzer_power = Var(model.D, model.T, domain=NonNegativeReals)
    model.electrolyzer_power_segment = Var(
        model.D, model.T, model.ELECTROLYZER_SEGMENTS, domain=NonNegativeReals
    )
    model.h2_production_segment = Var(
        model.D, model.T, model.ELECTROLYZER_SEGMENTS, domain=NonNegativeReals
    )
    model.h2_production = Var(model.D, model.T, domain=NonNegativeReals)
    model.is_electrolyzer_on = Var(model.D, model.T, domain=Binary)
    model.electrolyzer_segment_active = Var(
        model.D, model.T, model.ELECTROLYZER_ORDERED_SEGMENTS, domain=Binary
    )
    model.h2_charge = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_discharge = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_storage = Var(model.D, model.T, domain=NonNegativeReals)
    model.is_h2_charging = Var(model.D, model.T, domain=Binary)
    model.h2_external_supply = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_fuel_cell = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_fuel_cell_segment = Var(
        model.D, model.T, model.FUEL_CELL_SEGMENTS, domain=NonNegativeReals
    )
    model.fuel_cell_power_segment = Var(
        model.D, model.T, model.FUEL_CELL_SEGMENTS, domain=NonNegativeReals
    )
    model.fuel_cell_power = Var(model.D, model.T, domain=NonNegativeReals)
    model.is_fuel_cell_on = Var(model.D, model.T, domain=Binary)
    model.fuel_cell_segment_active = Var(
        model.D, model.T, model.FUEL_CELL_ORDERED_SEGMENTS, domain=Binary
    )
    model.fuel_cell_backup_capacity_kw = Var(domain=NonNegativeReals)

    model.battery_degradation_throughput_segment = Var(
        model.D, model.T, model.BATTERY_DEGRADATION_SEGMENTS, domain=NonNegativeReals
    )

    model.carbon_emission = Var(model.D, model.T, domain=NonNegativeReals)

    model.load_shed_critical = Var(model.D, model.T, domain=NonNegativeReals)
    model.load_shed_important = Var(model.D, model.T, domain=NonNegativeReals)
    model.load_shed_interruptible = Var(model.D, model.T, domain=NonNegativeReals)
