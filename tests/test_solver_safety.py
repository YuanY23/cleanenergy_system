from __future__ import annotations

from types import SimpleNamespace

from pyomo.opt import TerminationCondition

import zero_carbon_park.optimization.solver as solver_module


def test_time_limit_without_incumbent_is_explicit(monkeypatch) -> None:
    result = SimpleNamespace(
        solver=SimpleNamespace(
            termination_condition=TerminationCondition.maxTimeLimit,
            status="warning",
        ),
        problem=SimpleNamespace(lower_bound=0.0, upper_bound=None),
    )

    class FakeSolver:
        def __init__(self) -> None:
            self.options = {}

        def solve(self, *_args, **_kwargs):
            return result

    class MissingSolution:
        def load_from(self, _result) -> None:
            raise ValueError("no incumbent")

    model = SimpleNamespace(solutions=MissingSolution())
    monkeypatch.setattr(solver_module, "SolverFactory", lambda _name: FakeSolver())

    status = solver_module.solve_model(model, time_limit_seconds=1.0)

    assert status == "time_limit_no_solution"
    assert model.solve_metadata["has_incumbent"] is False
