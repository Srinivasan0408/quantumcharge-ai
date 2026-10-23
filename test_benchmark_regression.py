import pytest
import pandas as pd
from backend.models import QuantumOptRequest
from backend.comparison import run_rigorous_comparison_benchmark

def test_identical_benchmark_inputs():
    """Verify both solvers receive identical immutable benchmark inputs."""
    tariffs_df = pd.read_csv("data/tariffs.csv")
    evs_df = pd.read_csv("data/ev_sessions.csv")

    req = QuantumOptRequest(
        ev_ids=["EV001", "EV003"],
        candidate_slots=[0, 1, 2],
        price_profile="TimeOfUse",
        qaoa_reps=1,
        shots=512,
        max_iter=10
    )

    res = run_rigorous_comparison_benchmark(tariffs_df, evs_df, req)

    # Check that EV inputs and slots are identical
    assert res.benchmark_inputs["ev_ids"] == ["EV001", "EV003"]
    assert res.benchmark_inputs["candidate_slots"] == [0, 1, 2]
    assert len(res.qubit_mappings) == 6 # 3 slots * 2 EVs
    assert res.station_capacity_units == 1

def test_reproducible_task6_reference_test():
    """
    TASK 6 Reference Test:
    EV001 & EV003 across slots [0, 1, 2] with prices [8, 3, 6] INR/kWh and station capacity = 1.
    Expected classical minimum cost: INR 9.00 (slot 1 at INR 3 + slot 2 at INR 6).
    """
    tariffs_df = pd.DataFrame()
    evs_df = pd.DataFrame()

    override_evs = [
        {
            "ev_id": "EV001",
            "arrival_slot": 0,
            "departure_slot": 3,
            "required_energy_kwh": 1.0,
            "charger_id": "CH01",
            "battery_capacity_kwh": 6.0,
            "initial_soc_percent": 40.0,
            "target_soc_percent": 60.0,
            "maximum_charging_power_kw": 7.2,
            "charging_efficiency": 1.0
        },
        {
            "ev_id": "EV003",
            "arrival_slot": 0,
            "departure_slot": 3,
            "required_energy_kwh": 1.0,
            "charger_id": "CH03",
            "battery_capacity_kwh": 4.0,
            "initial_soc_percent": 50.0,
            "target_soc_percent": 75.0,
            "maximum_charging_power_kw": 7.4,
            "charging_efficiency": 1.0
        }
    ]
    override_prices = {0: 8.0, 1: 3.0, 2: 6.0}

    req = QuantumOptRequest(
        ev_ids=["EV001", "EV003"],
        candidate_slots=[0, 1, 2],
        price_profile="Custom",
        qaoa_reps=1,
        shots=1024,
        max_iter=25,
        penalty_demand=25.0,
        penalty_conflict=30.0,
        unit_energy_mode=True,
        station_capacity_units=1
    )

    res = run_rigorous_comparison_benchmark(
        tariffs_df,
        evs_df,
        req,
        override_prices=override_prices,
        override_evs=override_evs
    )

    # 1. Classical CP-SAT MUST find exactly INR 9.00
    assert res.classical_cpsat["status"] in ("OPTIMAL", "FEASIBLE")
    assert res.classical_cpsat["economic_cost_inr"] == 9.00
    assert res.classical_cpsat["is_feasible"] is True

    # Check classical optimal slots: must be slot 1 (price 3) and slot 2 (price 6)
    c_schedules = res.classical_cpsat["schedules"]
    all_c_slots = sorted([s["scheduled_slots"][0] for s in c_schedules])
    assert all_c_slots == [1, 2]

    # 2. QAOA evaluates the exact same economic formulation
    q = res.quantum_qaoa
    assert "economic_cost_inr" in q
    assert "qubo_objective_value" in q
    assert q["economic_cost_inr"] > 0

    # If QAOA finds a feasible state, economic cost is at least 9.00 (the global optimum)
    if q["is_feasible"]:
        assert q["economic_cost_inr"] >= 9.00
        assert res.qaoa_objective_gap_inr >= 0.0

def test_economic_cost_versus_qubo_penalty_separation():
    """Verify economic electricity cost is separated from QUBO penalty energy."""
    override_evs = [
        {"ev_id": "EV1", "arrival_slot": 0, "departure_slot": 2, "required_energy_kwh": 1.0, "charger_id": "CH1", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0},
        {"ev_id": "EV2", "arrival_slot": 0, "departure_slot": 2, "required_energy_kwh": 1.0, "charger_id": "CH2", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0}
    ]
    override_prices = {0: 10.0, 1: 5.0}

    req = QuantumOptRequest(
        ev_ids=["EV1", "EV2"],
        candidate_slots=[0, 1],
        qaoa_reps=1,
        shots=512,
        max_iter=10,
        penalty_demand=50.0,
        penalty_conflict=50.0,
        unit_energy_mode=True,
        station_capacity_units=1
    )

    res = run_rigorous_comparison_benchmark(
        pd.DataFrame(), pd.DataFrame(), req,
        override_prices=override_prices, override_evs=override_evs
    )

    # Check top states
    for state in res.quantum_qaoa["top_states"]:
        econ_cost = state["economic_cost_inr"]
        qubo_e = state["qubo_energy"]
        # If state is feasible, economic cost matches the expected slot tariff
        if state["is_feasible"]:
            assert econ_cost in (15.0,) # one at 10, one at 5 (total 15)
        else:
            # Infeasible states have constraint violations and penalized QUBO energy
            assert len(state["constraint_violations"]) > 0
            assert qubo_e != econ_cost

def test_bitstring_endianness_and_mapping():
    """Verify explicit variable mapping and Qiskit endianness encoding."""
    override_evs = [
        {"ev_id": "EV1", "arrival_slot": 0, "departure_slot": 2, "required_energy_kwh": 1.0, "charger_id": "CH1", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0},
        {"ev_id": "EV2", "arrival_slot": 0, "departure_slot": 2, "required_energy_kwh": 1.0, "charger_id": "CH2", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0}
    ]
    override_prices = {0: 10.0, 1: 5.0}

    req = QuantumOptRequest(
        ev_ids=["EV1", "EV2"],
        candidate_slots=[0, 1],
        qaoa_reps=1,
        shots=256,
        max_iter=5,
        unit_energy_mode=True,
        station_capacity_units=1
    )

    res = run_rigorous_comparison_benchmark(
        pd.DataFrame(), pd.DataFrame(), req,
        override_prices=override_prices, override_evs=override_evs
    )

    # Check variable bitstring vs qiskit bitstring for all states
    for st in res.quantum_qaoa["top_states"]:
        var_bits = st["variable_bitstring"]
        qis_bits = st["qiskit_bitstring"]
        # Qiskit bitstring must be exact reverse of variable order
        assert qis_bits == var_bits[::-1]

def test_fastapi_reference_test_route_registered():
    """Verify that /api/benchmark/reference-test and aliases exist and support GET and POST."""
    from backend.main import app, run_reproducible_reference_test

    routes = {r.path: r.methods for r in app.routes if hasattr(r, "methods")}
    
    assert "/api/benchmark/reference-test" in routes, "Reference test route missing from app"
    assert "GET" in routes["/api/benchmark/reference-test"]
    assert "POST" in routes["/api/benchmark/reference-test"]

    assert "/api/benchmark/reference" in routes
    assert "/api/reference-test" in routes

    # Direct function execution test
    resp = run_reproducible_reference_test(reps=1, shots=256, max_iter=5)
    assert resp.classical_cpsat["economic_cost_inr"] == 9.00
    assert resp.station_capacity_units == 1
    assert "tariff_prices_inr" in resp.benchmark_inputs
    assert resp.benchmark_inputs["tariff_prices_inr"] == {"0": 8.0, "1": 3.0, "2": 6.0} or resp.benchmark_inputs["tariff_prices_inr"] == {0: 8.0, 1: 3.0, 2: 6.0}
    assert len(resp.qubit_mappings) == 6

def test_independent_feasibility_validation_rejects_conflicts():
    """Verify that station capacity violations and unfulfilled demands are marked infeasible."""
    from backend.comparison import validate_candidate_feasibility

    candidate_slots = [0, 1, 2]
    ev_records = [
        {"ev_id": "EV001", "arrival_slot": 0, "departure_slot": 3, "required_energy_kwh": 1.0, "charger_id": "CH01", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0},
        {"ev_id": "EV003", "arrival_slot": 0, "departure_slot": 3, "required_energy_kwh": 1.0, "charger_id": "CH03", "charging_efficiency": 1.0, "maximum_charging_power_kw": 1.0}
    ]
    qubit_map_meta = [
        (0, "EV001", 0, "CH01", 1.0, 8.0),
        (0, "EV001", 1, "CH01", 1.0, 3.0),
        (0, "EV001", 2, "CH01", 1.0, 6.0),
        (1, "EV003", 0, "CH03", 1.0, 8.0),
        (1, "EV003", 1, "CH03", 1.0, 3.0),
        (1, "EV003", 2, "CH03", 1.0, 6.0)
    ]
    ev_k_slots = {0: 1, 1: 1} # Each EV needs 1 slot

    # Case 1: Both EVs assigned to Slot 1 -> Violates station capacity (1 simultaneous unit)
    # EV001 on slot 1 (bit 1 = 1), EV003 on slot 1 (bit 4 = 1) -> "010010"
    is_feas, viols = validate_candidate_feasibility(
        "010010", qubit_map_meta, ev_records, ev_k_slots, candidate_slots, station_capacity=1
    )
    assert is_feas is False
    assert any("Station capacity exceeded" in v for v in viols)

    # Case 2: EV001 assigned to 0 slots -> Violates demand fulfillment
    is_feas2, viols2 = validate_candidate_feasibility(
        "000010", qubit_map_meta, ev_records, ev_k_slots, candidate_slots, station_capacity=1
    )
    assert is_feas2 is False
    assert any("Demand unfulfilled" in v for v in viols2)

    # Case 3: EV001 on slot 1, EV003 on slot 2 -> FEASIBLE!
    # EV001 on slot 1 (bit 1 = 1), EV003 on slot 2 (bit 5 = 1) -> "010001"
    is_feas3, viols3 = validate_candidate_feasibility(
        "010001", qubit_map_meta, ev_records, ev_k_slots, candidate_slots, station_capacity=1
    )
    assert is_feas3 is True
    assert len(viols3) == 0
