import pandas as pd

from zero_carbon_park.reporting.plots import plot_battery_soc, plot_h2_storage


def test_soc_and_h2_plots_do_not_warn_when_no_series_are_drawn(tmp_path, recwarn):
    hourly = pd.DataFrame(
        {
            "scenario_id": ["EMPTY", "EMPTY"],
            "hour": [0, 1],
            "battery_soc_kwh": [0.0, 0.0],
            "h2_storage_kg": [0.0, 0.0],
        }
    )

    plot_battery_soc(hourly, tmp_path / "battery_soc.png")
    plot_h2_storage(hourly, tmp_path / "h2_storage.png")

    assert len(recwarn) == 0
