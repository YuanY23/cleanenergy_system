"""多典型日定义模块。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TypicalDayConfig:
    """单个典型日的缩放配置。

    day_id: 典型日编号，用于输出目录和结果表。
    name: 中文名称，便于报告展示。
    weight_days: 该典型日代表的全年天数。
    *_scale: 对基准 24 小时输入曲线的缩放倍数。
    """

    day_id: str
    name: str
    weight_days: int
    pv_scale: float
    wind_scale: float
    electric_load_scale: float
    heat_load_scale: float
    hydrogen_load_scale: float
    electricity_price_scale: float
    gas_price_scale: float
    grid_emission_scale: float
    carbon_price_scale: float


@dataclass(frozen=True)
class RepresentativePeriodConfig:
    """Configuration for deterministic, real-day representative periods."""

    k: int = 12
    seed: int = 20240809
    timestamp_column: str = "timestamp_local"
    feature_columns: tuple[str, ...] | None = None
    max_iterations: int = 50
    include_year_wrap: bool = True

    def __post_init__(self) -> None:
        if self.k not in {8, 12, 16}:
            raise ValueError("k must be 8, 12 or 16")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")


@dataclass(frozen=True)
class RepresentativePeriodResult:
    """Auditable compression output and occurrence-level chronology interface.

    ``chronology_links`` deliberately retains one row per calendar-day state
    transition.  A planning model can therefore link storage end/start states
    in the original 366-day order instead of imposing independent daily loops.
    ``transition_counts`` is the corresponding compact aggregate.
    """

    representative_days: pd.DataFrame
    representative_hourly: pd.DataFrame
    day_mapping: pd.DataFrame
    transition_counts: pd.DataFrame
    chronology_links: pd.DataFrame
    normalization: pd.DataFrame
    extreme_days: dict[str, object]
    feature_columns: tuple[str, ...]
    seed: int
    k: int


def get_default_typical_days() -> list[TypicalDayConfig]:
    """返回 v2.1 第一版使用的三个典型日配置。"""

    return [
        TypicalDayConfig(
            day_id="TD_SUMMER",
            name="夏季典型日",
            weight_days=120,
            pv_scale=1.15,
            wind_scale=0.90,
            electric_load_scale=1.15,
            heat_load_scale=0.60,
            hydrogen_load_scale=1.00,
            electricity_price_scale=1.05,
            gas_price_scale=1.00,
            grid_emission_scale=1.00,
            carbon_price_scale=1.00,
        ),
        TypicalDayConfig(
            day_id="TD_WINTER",
            name="冬季典型日",
            weight_days=120,
            pv_scale=0.70,
            wind_scale=1.15,
            electric_load_scale=1.05,
            heat_load_scale=1.35,
            hydrogen_load_scale=1.00,
            electricity_price_scale=1.05,
            gas_price_scale=1.00,
            grid_emission_scale=1.00,
            carbon_price_scale=1.00,
        ),
        TypicalDayConfig(
            day_id="TD_TRANSITION",
            name="过渡季典型日",
            weight_days=125,
            pv_scale=1.00,
            wind_scale=1.00,
            electric_load_scale=1.00,
            heat_load_scale=0.90,
            hydrogen_load_scale=1.00,
            electricity_price_scale=1.00,
            gas_price_scale=1.00,
            grid_emission_scale=1.00,
            carbon_price_scale=1.00,
        ),
    ]
