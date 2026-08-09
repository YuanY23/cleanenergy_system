import pandas as pd
import pytest

import zero_carbon_park.planning.runner as portfolio_runner
from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.planning.runner import (
    classify_independent_engineering_solution,
    solve_engineering_portfolios,
)
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


CAPACITY_BOUNDS = {
    "wind_capacity_kw": 20.0,
    "pv_capacity_kw": 20.0,
    "battery_power_capacity_kw": 20.0,
    "battery_energy_capacity_kwh": 40.0,
    "electrolyzer_power_capacity_kw": 20.0,
    "h2_storage_capacity_kg": 20.0,
    "fuel_cell_power_capacity_kw": 20.0,
    "heat_pump_power_capacity_kw": 20.0,
}


def _parameters(values):
    return pd.DataFrame(
        [{"parameter": name, "value": selected} for name, selected in values.items()]
    )


def _representative_day(*, grid_sell_price=0.0):
    frame = pd.DataFrame(
        {
            "pv_cf": [1.0] * 4,
            "wind_cf": [0.0] * 4,
            "electric_load_kw": [10.0] * 4,
            "critical_load_kw": [5.0] * 4,
            "important_load_kw": [5.0] * 4,
            "interruptible_load_kw": [0.0] * 4,
            "heat_load_kw": [0.0] * 4,
            "hydrogen_load_kg": [0.0] * 4,
            "electricity_price_cny_per_kwh": [1.0] * 4,
            "grid_sell_price_cny_per_kwh": [grid_sell_price] * 4,
            "gas_price_cny_per_m3": [3.0] * 4,
            "grid_emission_kgco2_per_kwh": [1.0] * 4,
            "carbon_price_cny_per_tco2": [0.0] * 4,
        }
    )
    workbook = InputWorkbook(
        timeseries=frame,
        device_params=_parameters(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 100.0,
                "gas_boiler_eff": 0.9,
                "gas_lhv_kwh_per_m3": 9.8,
                "battery_eta_ch": 1.0,
                "battery_eta_dis": 1.0,
                "electrolyzer_kWh_per_kgH2": 50.0,
                "fuel_cell_kWh_per_kgH2": 20.0,
            }
        ),
        economic_params=_parameters(
            {
                "gas_emission_factor": 2.0,
                "curtail_penalty": 0.0,
                "battery_om": 0.0,
                "electrolyzer_om": 0.0,
                "fuel_cell_om": 0.0,
                "h2_external_supply_cost": 1000.0,
                "critical_load_shed_penalty_cny_per_kwh": 10000.0,
                "important_load_shed_penalty_cny_per_kwh": 1000.0,
                "interruptible_load_shed_penalty_cny_per_kwh": 100.0,
            }
        ),
        scenarios=pd.DataFrame(),
    )
    config = TypicalDayConfig(
        day_id="TD", name="benchmark", weight_days=1,
        pv_scale=1.0, wind_scale=1.0, electric_load_scale=1.0,
        heat_load_scale=1.0, hydrogen_load_scale=1.0,
        electricity_price_scale=1.0, gas_price_scale=1.0,
        grid_emission_scale=1.0, carbon_price_scale=1.0,
    )
    return [(config, workbook)]


def _costs():
    return PlanningCostParams(
        discount_rate=0.0,
        wind_capex_cny_per_kw=10000.0,
        pv_capex_cny_per_kw=200.0,
        battery_power_capex_cny_per_kw=100.0,
        battery_energy_capex_cny_per_kwh=100.0,
        electrolyzer_capex_cny_per_kw=10000.0,
        h2_storage_capex_cny_per_kg=10000.0,
        fuel_cell_capex_cny_per_kw=10000.0,
        heat_pump_capex_cny_per_kw=10000.0,
        grid_import_limit_kw=20.0,
    )


def test_three_portfolios_obey_cost_carbon_and_islanded_design_contracts():
    result = solve_engineering_portfolios(
        _representative_day(),
        _costs(),
        capacity_upper_bounds=CAPACITY_BOUNDS,
        low_carbon_cost_ratio=1.10,
        secure_capacity_multiplier=1.20,
        critical_supply_min_ratio=0.99,
        time_limit_seconds=10.0,
        mip_gap=0.001,
    )

    summary = result["summary"].set_index("portfolio_id")
    assert set(summary.index) == {"economic", "low_carbon", "resilience"}
    assert set(summary["status"]) == {"optimal"}
    assert summary.loc["low_carbon", "annual_total_cost_cny"] <= (
        1.10 * summary.loc["economic", "annual_total_cost_cny"] + 1e-5
    )
    assert summary.loc["low_carbon", "annual_carbon_emission_kg"] < summary.loc[
        "economic", "annual_carbon_emission_kg"
    ]
    assert summary.loc["low_carbon", "annual_ens_critical_kwh"] == pytest.approx(0.0)
    assert summary.loc["low_carbon", "annual_ens_important_kwh"] == pytest.approx(0.0)
    assert summary.loc["resilience", "annual_h2_external_supply_kg"] == pytest.approx(0.0)
    assert summary.loc["resilience", "critical_load_supply_rate"] >= 0.99
    assert summary.loc["resilience", "secure_capacity_margin_kw"] >= -1e-6
    assert summary.loc["resilience", "islanded_design_basis"]
    assert not summary.loc["resilience", "certification_claimed"]
    assert "外送电不抵扣" in summary.loc["low_carbon", "carbon_accounting_boundary"]
    assert summary.loc["low_carbon", "incremental_cost_vs_economic_cny"] >= -1e-5
    assert summary.loc["low_carbon", "carbon_reduction_vs_economic_kg"] > 0.0
    assert summary.loc["resilience", "reliability_benefit_vs_economic"] >= 0.0
    assert summary.loc["low_carbon", "is_independent_engineering_solution"]
    assert summary.loc["resilience", "is_independent_engineering_solution"]
    assert summary.loc["economic", "solver_requested_mip_gap"] == pytest.approx(0.001)
    assert '"pv_capex_cny_per_kw": 200.0' in summary.loc[
        "economic", "cost_params_json"
    ]
    assert summary.loc["economic", "representative_period_weights_json"] == '{"TD": 1.0}'

    capacities = result["capacity"]
    assert set(capacities["portfolio_id"]) == set(summary.index)
    assert len(capacities) == 3 * len(CAPACITY_BOUNDS)


def test_export_revenue_never_credits_operating_carbon():
    result = solve_engineering_portfolios(
        _representative_day(grid_sell_price=5.0),
        _costs(),
        capacity_upper_bounds=CAPACITY_BOUNDS,
        time_limit_seconds=10.0,
    )
    low_carbon = result["summary"].set_index("portfolio_id").loc["low_carbon"]
    assert low_carbon["annual_carbon_emission_kg"] >= 0.0
    assert low_carbon["carbon_accounting_boundary"] == "购电与燃气运行排放；外送电不抵扣"


def test_numerically_identical_solution_is_not_relabelled_as_independent():
    independent, reason = classify_independent_engineering_solution(
        candidate_capacities={name: 1.0 for name in CAPACITY_BOUNDS},
        baseline_capacities={name: 1.0 + 1e-9 for name in CAPACITY_BOUNDS},
        candidate_metrics={"cost": 100.0, "carbon": 50.0, "reliability": 1.0},
        baseline_metrics={"cost": 100.0 + 1e-8, "carbon": 50.0, "reliability": 1.0},
        relative_threshold=1e-5,
        absolute_threshold=1e-6,
    )
    assert not independent
    assert reason == "未形成独立工程方案"


def test_capacity_bounds_must_be_complete_and_finite():
    with pytest.raises(ValueError, match="all capacity variables"):
        solve_engineering_portfolios(
            _representative_day(), _costs(), capacity_upper_bounds={"pv_capacity_kw": 1.0}
        )


def test_timeout_without_incumbent_is_reported_not_relabelled(monkeypatch):
    monkeypatch.setattr(portfolio_runner, "solve_model", lambda *args, **kwargs: "time_limit")
    with pytest.raises(RuntimeError, match="time_limit.*no extractable incumbent"):
        solve_engineering_portfolios(
            _representative_day(), _costs(), capacity_upper_bounds=CAPACITY_BOUNDS
        )
