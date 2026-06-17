"""不确定性压力测试场景定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UncertaintyCase:
    """单个不确定性压力测试场景。"""

    case_id: str
    name: str
    probability: float
    pv_scale: float = 1.0
    wind_scale: float = 1.0
    electric_load_scale: float = 1.0
    heat_load_scale: float = 1.0
    hydrogen_load_scale: float = 1.0


def get_default_uncertainty_cases() -> list[UncertaintyCase]:
    """返回默认不确定性压力测试场景。

    概率用于后续随机优化扩展；当前压力测试主要逐场景比较结果。
    """

    return [
        UncertaintyCase(
            case_id="NORMAL",
            name="正常预测",
            probability=0.50,
        ),
        UncertaintyCase(
            case_id="PV_LOW",
            name="光伏偏低",
            probability=0.12,
            pv_scale=0.70,
        ),
        UncertaintyCase(
            case_id="WIND_LOW",
            name="风电偏低",
            probability=0.12,
            wind_scale=0.75,
        ),
        UncertaintyCase(
            case_id="LOAD_HIGH",
            name="电热负荷偏高",
            probability=0.10,
            electric_load_scale=1.10,
            heat_load_scale=1.10,
        ),
        UncertaintyCase(
            case_id="H2_HIGH",
            name="氢负荷偏高",
            probability=0.08,
            hydrogen_load_scale=1.30,
        ),
        UncertaintyCase(
            case_id="EXTREME",
            name="风光偏低且负荷偏高",
            probability=0.08,
            pv_scale=0.70,
            wind_scale=0.75,
            electric_load_scale=1.10,
            heat_load_scale=1.15,
            hydrogen_load_scale=1.30,
        ),
    ]

