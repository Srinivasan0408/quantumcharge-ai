import pandas as pd
import pytest
from backend.models import QuantumOptRequest
from backend.quantum_optimizer import run_genuine_qaoa

def test_genuine_qaoa_execution():
    tariffs_df = pd.read_csv("data/tariffs.csv")
    evs_df = pd.read_csv("data/ev_sessions.csv")

    # Feasible small instance: EV001 and EV003
    req = QuantumOptRequest(
        ev_ids=["EV001", "EV003"],
        candidate_slots=[0, 1, 2],
        price_profile="TimeOfUse",
        qaoa_reps=1,
        shots=1024,
        max_iter=15,
        penalty_demand=20.0,
        penalty_conflict=25.0
    )

    res = run_genuine_qaoa(tariffs_df, evs_df, req)

    assert res.success is True
    assert res.error is None
    assert res.execution_time_seconds > 0.0
    assert res.qubit_count > 0
    assert res.circuit_depth > 0
    assert len(res.gate_counts) > 0
    assert len(res.optimal_bitstring) == res.qubit_count
    assert len(res.top_states) > 0
    assert len(res.schedules) == 2

    # Verify real classical comparison attached
    assert res.classical_comparison is not None
    assert "status" in res.classical_comparison
    assert res.classical_comparison["status"] in ("OPTIMAL", "FEASIBLE")

def test_qaoa_infeasible_or_exceeded_error_handling():
    tariffs_df = pd.read_csv("data/tariffs.csv")
    evs_df = pd.read_csv("data/ev_sessions.csv")

    # Request too many EVs to trigger real error
    req = QuantumOptRequest(
        ev_ids=["EV001", "EV002", "EV003", "EV004", "EV005", "EV006", "EV007", "EV008"],
        price_profile="TimeOfUse"
    )

    res = run_genuine_qaoa(tariffs_df, evs_df, req)
    assert res.success is False
    assert res.error is not None
    assert "Quantum simulation limit exceeded" in res.error
