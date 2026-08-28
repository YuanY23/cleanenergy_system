from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import export_processed_inputs, load_input_workbook
from zero_carbon_park.data.validation import validate_parameter_table, validate_timeseries
from zero_carbon_park.reporting.plots import plot_input_curves


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_load_input_workbook_reads_core_sheets():
    workbook = load_input_workbook(_workbook_path())

    assert len(workbook.timeseries) == 24
    assert len(workbook.device_params) > 0
    assert len(workbook.economic_params) > 0
    assert len(workbook.scenarios) >= 6
    required_columns = {
        "hour",
        "pv_cf",
        "wind_cf",
        "pv_available_kw",
        "wind_available_kw",
        "electric_load_kw",
        "heat_load_kw",
        "hydrogen_load_kg",
        "tou_period",
        "electricity_price_cny_per_kwh",
        "gas_price_cny_per_m3",
        "grid_emission_kgco2_per_kwh",
        "carbon_price_cny_per_tco2",
    }
    assert required_columns.issubset(set(workbook.timeseries.columns))


def test_loaded_workbook_data_passes_validation():
    workbook = load_input_workbook(_workbook_path())

    validate_timeseries(workbook.timeseries, expected_hours=24)
    validate_parameter_table(workbook.device_params)
    validate_parameter_table(workbook.economic_params)

    assert "battery_energy_kWh" in set(workbook.device_params["parameter"])
    assert "carbon_price" in set(workbook.economic_params["parameter"])


def test_export_processed_inputs_writes_model_ready_files(tmp_path: Path):
    output_paths = export_processed_inputs(_workbook_path(), tmp_path)
    figure_path = tmp_path / "input_curves.png"

    plot_input_curves(pd.read_csv(output_paths["timeseries_csv"]), figure_path)

    expected_keys = {
        "timeseries_csv",
        "timeseries_excel",
        "device_params_csv",
        "device_params_excel",
        "economic_params_csv",
        "economic_params_excel",
        "scenarios_csv",
        "scenarios_excel",
    }
    assert expected_keys == set(output_paths)
    for path in output_paths.values():
        assert path.exists()
        assert path.stat().st_size > 0
    assert figure_path.exists()
    assert figure_path.stat().st_size > 0
