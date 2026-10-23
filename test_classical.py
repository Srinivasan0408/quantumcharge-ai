import pandas as pd
import pytest
from backend.models import ClassicalOptRequest
from backend.classical_optimizer import solve_classical_cpsat

def test_classical_cpsat_solver():
    tariffs_df = pd.read_csv("data/tariffs.csv")
    evs_df = pd.read_csv("data/ev_sessions.csv")

    req = ClassicalOptRequest(
        price_profile="TimeOfUse",
        grid_power_limit_kw=70.0,
        peak_penalty_weight=0.05,
        time_limit_seconds=10.0
    )

    res = solve_classical_cpsat(tariffs_df, evs_df, req)

    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert res.is_optimal is True or res.status == "FEASIBLE"
    assert res.execution_time_seconds > 0.0
    assert res.objective_cost_inr > 0.0
    assert len(res.ev_schedules) == 25
    assert len(res.hourly_metrics) == 24
    assert res.grid_peak_power_kw <= req.grid_power_limit_kw + 0.001
    assert res.overall_fulfillment_percent > 90.0

    # Test EV schedule constraints
    for sched in res.ev_schedules:
        assert sched.final_soc_percent >= sched.initial_soc_percent
        for s in sched.charging_slots:
            assert sched.arrival_slot <= s < sched.departure_slot
