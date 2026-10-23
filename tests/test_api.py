import pytest
from backend.main import (
    health_check,
    load_sample_data,
    validate_active_datasets,
    analyze_active_datasets,
    run_classical_optimizer,
    run_quantum_optimizer,
    run_comparison_benchmark,
    add_or_update_ev_session,
    delete_ev_session,
    get_tariffs,
    get_ev_sessions
)
from backend.models import (
    ClassicalOptRequest,
    QuantumOptRequest,
    EVSessionRecord
)

def test_api_health():
    res = health_check()
    assert res["status"] == "healthy"
    assert "aer_simulator_available" in res
    assert res["tariffs_records"] == 96
    assert res["ev_records"] == 25

def test_load_sample_preset():
    res = load_sample_data()
    assert res["tariffs_count"] == 96
    assert res["evs_count"] == 25
    assert len(res["profiles"]) == 4

def test_api_validate():
    res = validate_active_datasets()
    assert res.valid is True
    assert res.total_tariff_records == 96
    assert res.total_ev_records == 25
    assert len(res.errors) == 0

def test_api_analyze():
    res = analyze_active_datasets()
    assert len(res.tariffs) == 4
    assert res.fleet.total_evs == 25
    assert res.theoretical_peak_demand_kw > 100.0

def test_api_optimize_classical():
    req = ClassicalOptRequest(
        price_profile="TimeOfUse",
        grid_power_limit_kw=75.0,
        peak_penalty_weight=0.05,
        time_limit_seconds=5.0
    )
    res = run_classical_optimizer(req)
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert res.objective_cost_inr > 0.0
    assert len(res.ev_schedules) == 25
    assert len(res.hourly_metrics) == 24

def test_api_optimize_quantum():
    req = QuantumOptRequest(
        ev_ids=["EV001", "EV003"],
        candidate_slots=[0, 1, 2],
        price_profile="TimeOfUse",
        qaoa_reps=1,
        shots=512,
        max_iter=10
    )
    res = run_quantum_optimizer(req)
    assert res.success is True
    assert res.qubit_count > 0
    assert len(res.optimal_bitstring) == res.qubit_count
    assert len(res.schedules) == 2

def test_api_optimize_compare():
    req = QuantumOptRequest(
        ev_ids=["EV001", "EV003"],
        candidate_slots=[0, 1, 2],
        price_profile="TimeOfUse",
        qaoa_reps=1,
        shots=512,
        max_iter=10
    )
    res = run_comparison_benchmark(req)
    assert res.classical_cpsat is not None
    assert res.quantum_qaoa is not None
    assert "Classical OR-Tools CP-SAT" in res.summary

def test_api_reproducible_reference_test():
    from backend.main import run_reproducible_reference_test
    res = run_reproducible_reference_test(reps=1, shots=512, max_iter=10)
    assert res.classical_cpsat["economic_cost_inr"] == 9.00
    assert res.classical_cpsat["is_feasible"] is True

def test_api_manual_ev_crud():
    new_ev = EVSessionRecord(
        arrival_slot=2,
        battery_capacity_kwh=8.0,
        charger_id="CH09",
        charging_efficiency=0.92,
        departure_slot=8,
        ev_id="TEST_EV_99",
        initial_soc_percent=30.0,
        maximum_charging_power_kw=11.0,
        required_energy_kwh=5.0,
        target_soc_percent=90.0
    )
    # Add
    res_add = add_or_update_ev_session(new_ev)
    assert "TEST_EV_99" in res_add["message"]
    # Check
    sessions = get_ev_sessions()
    assert any(e["ev_id"] == "TEST_EV_99" for e in sessions)
    # Delete
    res_del = delete_ev_session("TEST_EV_99")
    assert "TEST_EV_99" in res_del["message"]
