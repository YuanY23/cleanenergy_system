from __future__ import annotations

import pandas as pd

from zero_carbon_park.formal_study import (
    _canonical_reliability_starts,
    fixed_solution_sensitivity,
    formal_planning_cost_params,
)


def test_canonical_reliability_starts_keep_three_state_stresses_and_global_peak() -> None:
    timestamps = pd.date_range("2024-01-01", periods=5, freq="h", tz="Asia/Shanghai")
    annual = pd.DataFrame(
        {"timestamp_local": timestamps, "electric_load_kw": [1, 8, 3, 10, 2]}
    )
    starts = pd.DataFrame(
        {
            "reason": [
                "monthly_high_electric_load",
                "monthly_high_electric_load",
                "minimum_battery_soc",
                "minimum_h2_inventory",
                "lowest_renewable",
            ],
            "month": [1, 2, 1, 1, 1],
            "start_timestamp": timestamps,
        }
    )

    selected = _canonical_reliability_starts(annual, starts)

    assert set(selected["reason"]) == {
        "monthly_high_electric_load",
        "minimum_battery_soc",
        "minimum_h2_inventory",
        "lowest_renewable",
    }
    assert selected.loc[
        selected["reason"].eq("monthly_high_electric_load"), "start_timestamp"
    ].iloc[0] == timestamps[1]


def test_fixed_solution_sensitivity_is_symmetric_and_nonnegative() -> None:
    summary = pd.DataFrame(
        {
            "portfolio_id": ["economic"],
            "annual_grid_cost_cny": [100.0],
            "annual_gas_cost_cny": [50.0],
        }
    )
    capacity = pd.DataFrame(
        [
            {
                "portfolio_id": "economic",
                "capacity_variable": name,
                "capacity_value": value,
            }
            for name, value in {
                "wind_capacity_kw": 10.0,
                "pv_capacity_kw": 20.0,
                "battery_power_capacity_kw": 5.0,
                "battery_energy_capacity_kwh": 30.0,
            }.items()
        ]
    )

    result = fixed_solution_sensitivity(
        summary, capacity, formal_planning_cost_params()
    )

    assert len(result) == 5
    assert (result["high_impact_cny"] >= 0).all()
    assert (result["low_impact_cny"] == -result["high_impact_cny"]).all()
    assert result["method"].str.contains("不重新优化").all()
