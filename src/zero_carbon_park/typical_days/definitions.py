"""多典型日定义模块。"""

from __future__ import annotations

from dataclasses import dataclass


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

