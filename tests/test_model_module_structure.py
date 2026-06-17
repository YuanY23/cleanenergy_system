from zero_carbon_park.models.constraints_carbon import add_carbon_constraints
from zero_carbon_park.models.constraints_heat import add_heat_constraints
from zero_carbon_park.models.constraints_hydrogen import add_hydrogen_constraints
from zero_carbon_park.models.constraints_power import (
    add_power_balance_constraints,
    add_renewable_constraints,
)
from zero_carbon_park.models.constraints_storage import add_battery_constraints
from zero_carbon_park.models.objective import add_total_cost_objective
from zero_carbon_park.models.sets import add_time_set
from zero_carbon_park.models.variables import add_decision_variables


def test_model_building_modules_expose_named_functions():
    """模型模块不能只是占位文件，必须暴露 builder 可复用的组装函数。"""

    assert callable(add_time_set)
    assert callable(add_decision_variables)
    assert callable(add_renewable_constraints)
    assert callable(add_power_balance_constraints)
    assert callable(add_heat_constraints)
    assert callable(add_battery_constraints)
    assert callable(add_hydrogen_constraints)
    assert callable(add_carbon_constraints)
    assert callable(add_total_cost_objective)
