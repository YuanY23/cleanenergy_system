"""HiGHS 求解器调用模块。"""

from pyomo.environ import SolverFactory
from pyomo.opt import TerminationCondition


def solve_model(model) -> str:
    """调用 HiGHS 求解 Pyomo 模型，并返回简化后的状态字符串。"""

    # appsi_highs 使用 Python highspy 包，不依赖外部 highs.exe。
    solver = SolverFactory("appsi_highs")
    result = solver.solve(model)
    termination = result.solver.termination_condition

    if termination == TerminationCondition.optimal:
        return "optimal"

    return str(termination)
