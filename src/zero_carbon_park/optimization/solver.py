"""HiGHS solver wrapper with reproducibility metadata."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from pyomo.environ import SolverFactory
from pyomo.opt import TerminationCondition


def solve_model(
    model,
    *,
    time_limit_seconds: float | None = None,
    mip_gap: float | None = None,
    log_path: str | Path | None = None,
    tee: bool = False,
) -> str:
    """Solve with HiGHS and attach the requested/observed solver metadata.

    The string return value is retained for existing callers. Detailed evidence
    is stored on ``model.solve_metadata`` for result manifests and reports.
    """

    if time_limit_seconds is not None and time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive")
    if mip_gap is not None and not 0 <= mip_gap < 1:
        raise ValueError("mip_gap must be within [0, 1)")

    solver = SolverFactory("appsi_highs")
    if time_limit_seconds is not None:
        solver.options["time_limit"] = float(time_limit_seconds)
    if mip_gap is not None:
        solver.options["mip_rel_gap"] = float(mip_gap)
    resolved_log = str(Path(log_path).resolve()) if log_path is not None else None
    if resolved_log is not None:
        solver.options["log_file"] = resolved_log

    started = perf_counter()
    result = solver.solve(model, tee=tee, load_solutions=False)
    elapsed = perf_counter() - started
    termination = result.solver.termination_condition
    has_incumbent = False
    if termination in {
        TerminationCondition.optimal,
        TerminationCondition.feasible,
        TerminationCondition.maxTimeLimit,
    }:
        try:
            model.solutions.load_from(result)
            has_incumbent = True
        except (RuntimeError, TypeError, ValueError):
            if termination != TerminationCondition.maxTimeLimit:
                raise

    solver_status = str(result.solver.status)
    lower_bound = getattr(result.problem, "lower_bound", None)
    upper_bound = getattr(result.problem, "upper_bound", None)
    actual_gap = None
    if lower_bound is not None and upper_bound is not None:
        try:
            lower, upper = float(lower_bound), float(upper_bound)
            denominator = max(abs(upper), 1.0e-12)
            actual_gap = abs(upper - lower) / denominator
        except (TypeError, ValueError):
            actual_gap = None
    model.solve_metadata = {
        "solver": "appsi_highs",
        "time_limit_seconds": (
            float(time_limit_seconds) if time_limit_seconds is not None else None
        ),
        "requested_mip_gap": float(mip_gap) if mip_gap is not None else None,
        "termination_condition": str(termination),
        "solver_status": solver_status,
        "elapsed_seconds": elapsed,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "actual_gap": actual_gap,
        "has_incumbent": has_incumbent,
        "log_path": resolved_log,
    }

    if termination == TerminationCondition.optimal:
        return "optimal"
    if termination == TerminationCondition.infeasible:
        return "infeasible"
    if termination == TerminationCondition.maxTimeLimit:
        return "time_limit" if has_incumbent else "time_limit_no_solution"

    return str(termination)
