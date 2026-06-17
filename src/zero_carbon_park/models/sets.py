"""模型集合定义模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, RangeSet


def add_time_set(model: ConcreteModel, last_hour: int) -> None:
    """加入时间集合。

    参数
    ----
    model:
        Pyomo 模型对象，所有变量和约束都会挂在这个对象上。
    last_hour:
        最后一个小时的编号。24 小时数据对应 0 到 23，所以 last_hour 为 23。
    """

    # T 是逐小时调度集合。当前项目使用 24 小时数据，但这里按输入行数自动确定。
    model.T = RangeSet(0, last_hour)
