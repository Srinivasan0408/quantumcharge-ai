import time
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from scipy.optimize import minimize
from ortools.sat.python import cp_model

from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp

try:
    from qiskit_aer.primitives import Sampler as AerSampler
    AER_AVAILABLE = True
except ImportError:
    AerSampler = None
    AER_AVAILABLE = False

from qiskit.primitives import StatevectorSampler

from .models import (
    QuantumOptRequest,
    ComparisonBenchmarkResponse,
    QubitVariableMapping,
    QuantumStateDistribution,
    DecodedQuantumSchedule
)

logger = logging.getLogger("qibits.comparison")
logging.basicConfig(level=logging.INFO)

def validate_candidate_feasibility(
    bits_input: Any,
    qubit_map_meta: List[Tuple[int, str, int, str, float, float]],
    ev_records: List[Dict[str, Any]],
    ev_k_slots: Dict[int, int],
    candidate_slots: Optional[List[int]] = None,
    station_capacity: int = 1
) -> Tuple[bool, List[str]]:
    """
    Independently validates a candidate bitstring against physical charging constraints:
    1. Energy demand fulfillment per EV
    2. Charger exclusivity (no two EVs simultaneously on the same charger)
    3. Station grid capacity limit (maximum concurrent charging vehicles per slot)
    4. Arrival/departure time windows
    """
    if isinstance(bits_input, str):
        bits_array = [int(b) for b in bits_input]
    else:
        bits_array = list(bits_input)

    violations: List[str] = []

    # Map qubits to EV indices
    ev_qubits: Dict[int, List[int]] = {i: [] for i in range(len(ev_records))}
    for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map_meta):
        ev_qubits[i].append(q)

    # Check EV energy demands & arrival/departure windows
    for i, ev in enumerate(ev_records):
        ev_id = str(ev.get("ev_id"))
        arr = int(ev.get("arrival_slot", 0))
        dep = int(ev.get("departure_slot", 24))
        assigned_slots = sum(bits_array[q] for q in ev_qubits[i])
        expected_slots = ev_k_slots.get(i, 1)

        if assigned_slots != expected_slots:
            violations.append(
                f"Demand unfulfilled: EV {ev_id} required {expected_slots} slots but received {assigned_slots} slots"
            )

        # Check window
        for q in ev_qubits[i]:
            if bits_array[q]:
                slot = qubit_map_meta[q][2]
                if slot < arr or slot >= dep:
                    violations.append(
                        f"Time window violation: EV {ev_id} scheduled in slot {slot} outside window [{arr}, {dep})"
                    )

    # Check charger exclusivity
    charger_slots: Dict[Tuple[str, int], List[str]] = {}
    for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map_meta):
        if bits_array[q]:
            charger_slots.setdefault((ch, s), []).append(ev_id)

    for (ch, s), ev_list in charger_slots.items():
        if len(ev_list) > 1:
            violations.append(
                f"Charger conflict: Charger {ch} at slot {s} simultaneous charging by {', '.join(ev_list)}"
            )

    # Check station capacity
    slot_concurrency: Dict[int, List[str]] = {}
    for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map_meta):
        if bits_array[q]:
            slot_concurrency.setdefault(s, []).append(ev_id)

    for s, ev_list in slot_concurrency.items():
        if len(ev_list) > station_capacity:
            violations.append(
                f"Station capacity exceeded at slot {s}: {len(ev_list)} EVs charging simultaneously ({', '.join(ev_list)}) > limit {station_capacity}"
            )

    return (len(violations) == 0, violations)

def run_rigorous_comparison_benchmark(
    tariffs_df: pd.DataFrame,
    evs_df: pd.DataFrame,
    request: QuantumOptRequest,
    override_prices: Optional[Dict[int, float]] = None,
    override_evs: Optional[List[Dict[str, Any]]] = None
) -> ComparisonBenchmarkResponse:
    """
    Executes a mathematically consistent side-by-side benchmark between
    Google OR-Tools CP-SAT and genuine Qiskit QAOA on the EXACT SAME immutable input.
    """
    start_benchmark = time.time()

    # 1. Prepare Immutable Inputs (TASK 1)
    if override_evs is not None:
        ev_records = override_evs
    else:
        if request.ev_ids and len(request.ev_ids) > 0:
            selected_df = evs_df[evs_df["ev_id"].isin(request.ev_ids)].copy()
        else:
            selected_df = evs_df.head(2).copy()
        ev_records = selected_df.to_dict("records")

    if not ev_records:
        raise ValueError("Benchmark requires at least 2 EV records.")

    # Candidate slots
    if request.candidate_slots and len(request.candidate_slots) > 0:
        candidate_slots = sorted(request.candidate_slots)
    else:
        candidate_slots = [0, 1, 2]

    # Prices dictionary
    if override_prices is not None:
        prices_dict = {s: float(override_prices.get(s, 8.0)) for s in candidate_slots}
    else:
        profile_df = tariffs_df[tariffs_df["price_profile"].str.lower() == request.price_profile.lower()]
        if profile_df.empty:
            profile_df = tariffs_df
        t_dict = dict(zip(profile_df["slot"].astype(int), profile_df["price_inr_per_kwh"].astype(float)))
        prices_dict = {s: float(t_dict.get(s, 8.0)) for s in candidate_slots}

    station_capacity = int(request.station_capacity_units)
    unit_energy_mode = bool(request.unit_energy_mode)

    # Log exact immutable benchmark inputs (TASK 1)
    logger.info("=== TASK 1: BENCHMARK INPUT SPECIFICATION ===")
    logger.info(f"Candidate Slots: {candidate_slots}")
    logger.info(f"Tariff Prices (INR/kWh): {prices_dict}")
    logger.info(f"Station Capacity (simultaneous units): {station_capacity}")
    logger.info(f"Unit Energy Mode: {unit_energy_mode}")
    for ev in ev_records:
        logger.info(
            f"EV [{ev.get('ev_id')}]: Arrival={ev.get('arrival_slot')}, "
            f"Departure={ev.get('departure_slot')}, Charger={ev.get('charger_id')}, "
            f"ReqEnergy={ev.get('required_energy_kwh')} kWh, PMax={ev.get('maximum_charging_power_kw')} kW, "
            f"Eff={ev.get('charging_efficiency')}"
        )

    # 2. Build Explicit Qubit Variable Mapping (TASK 3)
    qubit_mappings: List[QubitVariableMapping] = []
    qubit_map_meta: List[Tuple[int, str, int, str, float, float]] = []
    # (ev_idx, ev_id, slot, charger_id, grid_energy_kwh, price)

    ev_qubits: Dict[int, List[int]] = {i: [] for i in range(len(ev_records))}
    ev_k_slots: Dict[int, int] = {}

    for i, ev in enumerate(ev_records):
        ev_id = str(ev.get("ev_id", f"EV{i+1}"))
        ch = str(ev.get("charger_id", f"CH{i+1}"))
        arr = int(ev.get("arrival_slot", 0))
        dep = int(ev.get("departure_slot", 3))
        p_max = float(ev.get("maximum_charging_power_kw", 7.2))
        eff = float(ev.get("charging_efficiency", 0.92))
        req_e = float(ev.get("required_energy_kwh", 1.0))

        if unit_energy_mode:
            # 1 kWh per slot
            slot_grid_kwh = 1.0
            k_slots = max(1, int(round(req_e / 1.0)))
        else:
            slot_grid_kwh = p_max * 1.0 # 1 hour at p_max
            hourly_batt = slot_grid_kwh * eff
            k_slots = max(1, int(round(req_e / hourly_batt))) if hourly_batt > 0 else 1

        ev_k_slots[i] = k_slots

        # Valid candidate slots within stay window
        valid_slots = [s for s in candidate_slots if arr <= s < dep]
        if not valid_slots:
            valid_slots = [s for s in candidate_slots]

        for s in valid_slots:
            q_idx = len(qubit_map_meta)
            p_price = prices_dict.get(s, 8.0)
            c_term = slot_grid_kwh * p_price

            qubit_map_meta.append((i, ev_id, s, ch, slot_grid_kwh, p_price))
            ev_qubits[i].append(q_idx)

            qubit_mappings.append(QubitVariableMapping(
                qubit_index=q_idx,
                ev_id=ev_id,
                slot=s,
                charger_id=ch,
                grid_energy_kwh=round(slot_grid_kwh, 3),
                tariff_inr_per_kwh=round(p_price, 2),
                cost_coefficient_inr=round(c_term, 3)
            ))

    num_qubits = len(qubit_map_meta)
    if num_qubits < 1 or num_qubits > 16:
        raise ValueError(f"Qubit count {num_qubits} is out of allowable benchmark range [1, 16].")

    # 3. Independent Feasibility Validator (TASK 4)
    def validate_solution_feasibility(bits_array: List[int]) -> Tuple[bool, List[str]]:
        return validate_candidate_feasibility(
            bits_array,
            qubit_map_meta,
            ev_records,
            ev_k_slots,
            candidate_slots,
            station_capacity
        )

    # 4. Consistent Economic Cost Calculation (TASK 2)
    def calculate_economic_cost(bits_array: List[int]) -> float:
        """
        Calculates the genuine electricity procurement cost in INR:
        Cost = sum_q (grid_energy_kwh_q * tariff_q) * x_q
        """
        tot = 0.0
        for q, (i, ev_id, s, ch, grid_kwh, price) in enumerate(qubit_map_meta):
            if bits_array[q]:
                tot += grid_kwh * price
        return round(tot, 2)

    # 5. Decode Bits to Detailed EV Schedules (TASK 3)
    def decode_schedules(bits_array: List[int]) -> List[DecodedQuantumSchedule]:
        schedules: List[DecodedQuantumSchedule] = []
        for i, ev in enumerate(ev_records):
            ev_id = str(ev.get("ev_id"))
            ch = str(ev.get("charger_id"))
            k_req = ev_k_slots[i]
            eff = float(ev.get("charging_efficiency", 0.92))

            ev_active_slots = [qubit_map_meta[q][2] for q in ev_qubits[i] if bits_array[q]]
            ev_grid_kwh = sum(qubit_map_meta[q][4] for q in ev_qubits[i] if bits_array[q])
            ev_cost = sum(qubit_map_meta[q][4] * qubit_map_meta[q][5] for q in ev_qubits[i] if bits_array[q])

            schedules.append(DecodedQuantumSchedule(
                ev_id=ev_id,
                charger_id=ch,
                required_slots=k_req,
                scheduled_slots=sorted(ev_active_slots),
                is_demand_satisfied=(len(ev_active_slots) == k_req),
                energy_delivered_kwh=round(ev_grid_kwh * eff, 3),
                cost_inr=round(ev_cost, 2)
            ))
        return schedules

    # =========================================================================
    # CLASSICAL SOLVER (Google OR-Tools CP-SAT)
    # =========================================================================
    start_c = time.time()
    cp_model_inst = cp_model.CpModel()
    x_cp = [cp_model_inst.NewBoolVar(f"x_{q}") for q in range(num_qubits)]

    # Constraints: EV Energy Demand
    for i in range(len(ev_records)):
        cp_model_inst.Add(sum(x_cp[q] for q in ev_qubits[i]) == ev_k_slots[i])

    # Constraints: Charger Exclusivity
    charger_slot_groups: Dict[Tuple[str, int], List[int]] = {}
    for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map_meta):
        charger_slot_groups.setdefault((ch, s), []).append(q)
    for (ch, s), q_group in charger_slot_groups.items():
        if len(q_group) > 1:
            cp_model_inst.Add(sum(x_cp[q] for q in q_group) <= 1)

    # Constraints: Station Capacity Limit
    slot_groups: Dict[int, List[int]] = {}
    for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map_meta):
        slot_groups.setdefault(s, []).append(q)
    for s, q_group in slot_groups.items():
        cp_model_inst.Add(sum(x_cp[q] for q in q_group) <= station_capacity)

    # Objective: Minimize true economic electricity cost
    # Scale to integer paise: int(round(c_q * 100))
    cp_obj = sum(
        int(round(qubit_map_meta[q][4] * qubit_map_meta[q][5] * 100)) * x_cp[q]
        for q in range(num_qubits)
    )
    cp_model_inst.Minimize(cp_obj)

    cp_solver = cp_model.CpSolver()
    cp_status_code = cp_solver.Solve(cp_model_inst)
    cp_time = time.time() - start_c

    classical_bits = [int(cp_solver.Value(x_cp[q])) for q in range(num_qubits)]
    c_var_bitstring = "".join(str(b) for b in classical_bits)
    # Qiskit little-endian string: q_{n-1} ... q_0
    c_qiskit_bitstring = "".join(str(classical_bits[num_qubits - 1 - q]) for q in range(num_qubits))
    c_economic_cost = calculate_economic_cost(classical_bits)
    c_feasible, c_violations = validate_solution_feasibility(classical_bits)
    c_schedules = decode_schedules(classical_bits)

    classical_data = {
        "status": cp_solver.StatusName(cp_status_code),
        "economic_cost_inr": c_economic_cost,
        "variable_bitstring": c_var_bitstring,
        "qiskit_bitstring": c_qiskit_bitstring,
        "solve_time_seconds": round(cp_time, 4),
        "is_feasible": c_feasible,
        "constraint_violations": c_violations,
        "schedules": [s.model_dump() for s in c_schedules]
    }

    # =========================================================================
    # QUANTUM SOLVER (Qiskit QAOA)
    # =========================================================================
    start_q = time.time()

    # QUBO Construction (TASK 2)
    # Objective: Min Cost_economic(x) + A * Demands^2 + B_ch * ChargerConflicts + B_cap * StationCapacity
    A = float(request.penalty_demand)
    B_ch = float(request.penalty_conflict)
    B_cap = float(request.penalty_conflict)

    linear = {q: 0.0 for q in range(num_qubits)}
    quad: Dict[Tuple[int, int], float] = {}
    qubo_constant = 0.0

    # 1. Economic Cost linear terms
    for q, (i, ev_id, s, ch, grid_kwh, price) in enumerate(qubit_map_meta):
        linear[q] += grid_kwh * price

    # 2. EV Demand Penalties: A * (sum_{q in ev_i} x_q - k_i)^2
    # = A * [ sum x_q + 2 sum_{q1<q2} x_q1 x_q2 - 2k sum x_q + k^2 ]
    for i, q_list in ev_qubits.items():
        k = ev_k_slots[i]
        qubo_constant += A * (k ** 2)
        for q in q_list:
            linear[q] += A * (1.0 - 2.0 * k)
        for idx1 in range(len(q_list)):
            for idx2 in range(idx1 + 1, len(q_list)):
                pair = tuple(sorted((q_list[idx1], q_list[idx2])))
                quad[pair] = quad.get(pair, 0.0) + 2.0 * A

    # 3. Charger Exclusivity Penalties: B_ch * x_q1 * x_q2 for same charger in same slot
    for (ch, s), q_group in charger_slot_groups.items():
        if len(q_group) > 1:
            for idx1 in range(len(q_group)):
                for idx2 in range(idx1 + 1, len(q_group)):
                    pair = tuple(sorted((q_group[idx1], q_group[idx2])))
                    quad[pair] = quad.get(pair, 0.0) + B_ch

    # 4. Station Capacity Penalties:
    # If station_capacity == 1: B_cap * x_q1 * x_q2 for any two EVs in same slot
    if station_capacity == 1:
        for s, q_group in slot_groups.items():
            if len(q_group) > 1:
                for idx1 in range(len(q_group)):
                    for idx2 in range(idx1 + 1, len(q_group)):
                        pair = tuple(sorted((q_group[idx1], q_group[idx2])))
                        # Don't double count if already penalized under charger conflict
                        if quad.get(pair, 0.0) < B_cap:
                            quad[pair] = quad.get(pair, 0.0) + B_cap

    # Helper function to compute true QUBO energy
    def compute_qubo_energy(bits_arr: List[int]) -> float:
        val = qubo_constant
        for q in range(num_qubits):
            if bits_arr[q]:
                val += linear[q]
        for (q1, q2), coeff in quad.items():
            if bits_arr[q1] and bits_arr[q2]:
                val += coeff
        return val

    # Convert QUBO to Ising Pauli-Z: x_q = (I - Z_q)/2
    h_ising = np.zeros(num_qubits)
    J_ising = np.zeros((num_qubits, num_qubits))

    for q, c in linear.items():
        h_ising[q] -= c / 2.0
    for (q1, q2), val in quad.items():
        h_ising[q1] -= val / 4.0
        h_ising[q2] -= val / 4.0
        J_ising[q1, q2] += val / 4.0

    pauli_list = []
    for q in range(num_qubits):
        if abs(h_ising[q]) > 1e-7:
            label = ['I'] * num_qubits
            label[num_qubits - 1 - q] = 'Z'
            pauli_list.append((''.join(label), float(h_ising[q])))

    for (q1, q2), val in quad.items():
        if abs(J_ising[q1, q2]) > 1e-7:
            label = ['I'] * num_qubits
            label[num_qubits - 1 - q1] = 'Z'
            label[num_qubits - 1 - q2] = 'Z'
            pauli_list.append((''.join(label), float(val)))

    if not pauli_list:
        label = ['I'] * num_qubits
        pauli_list.append((''.join(label), 0.0))

    cost_hamiltonian = SparsePauliOp.from_list(pauli_list)

    # QAOA Circuit & Sampler
    reps = int(request.qaoa_reps)
    ansatz = QAOAAnsatz(cost_operator=cost_hamiltonian, reps=reps)
    ansatz.measure_all()
    circuit_depth = ansatz.depth()
    gate_counts = {str(k): int(v) for k, v in ansatz.count_ops().items()}

    if AER_AVAILABLE:
        sampler = AerSampler()
        is_aer = True
    else:
        sampler = StatevectorSampler()
        is_aer = False

    def qaoa_loss(params):
        if is_aer:
            job = sampler.run([ansatz], parameter_values=[params], shots=int(request.shots))
            quasi = job.result().quasi_dists[0]
        else:
            job = sampler.run([(ansatz, params)], shots=int(request.shots))
            meas_counts = job.result()[0].data.meas.get_counts()
            tot = sum(meas_counts.values())
            quasi = {int(k, 2): v / tot for k, v in meas_counts.items()}

        avg_e = 0.0
        for state_int, prob in quasi.items():
            bits_arr = [(state_int >> q) & 1 for q in range(num_qubits)]
            avg_e += prob * compute_qubo_energy(bits_arr)
        return avg_e

    # Classical parameter optimization
    init_params = np.random.uniform(0.1, 0.8, 2 * reps).tolist()
    opt_res = minimize(
        qaoa_loss,
        init_params,
        method="COBYLA",
        options={"maxiter": int(request.max_iter)}
    )
    opt_params = opt_res.x

    # Sample final state distribution
    final_shots = max(1024, int(request.shots))
    if is_aer:
        final_job = sampler.run([ansatz], parameter_values=[opt_params], shots=final_shots)
        final_quasi = final_job.result().quasi_dists[0]
    else:
        final_job = sampler.run([(ansatz, opt_params)], shots=final_shots)
        raw_counts = final_job.result()[0].data.meas.get_counts()
        tot = sum(raw_counts.values())
        final_quasi = {int(k, 2): v / tot for k, v in raw_counts.items()}

    q_time = time.time() - start_q

    # Decode states and rank (TASK 3 & TASK 4)
    top_states: List[QuantumStateDistribution] = []
    best_candidate_bits: Optional[List[int]] = None
    best_candidate_qubo = float("inf")

    # Sort states by measurement probability
    sorted_states = sorted(final_quasi.items(), key=lambda x: -x[1])[:10]

    for state_int, prob in sorted_states:
        # Extract bits in explicit variable order: bits_arr[q] corresponds to qubit_map_meta[q]
        bits_arr = [(state_int >> q) & 1 for q in range(num_qubits)]
        var_str = "".join(str(b) for b in bits_arr)
        # Qiskit standard little-endian bitstring: q_{n-1} ... q_0
        qiskit_str = f"{state_int:0{num_qubits}b}"

        econ_c = calculate_economic_cost(bits_arr)
        qubo_e = compute_qubo_energy(bits_arr)
        is_feas, viols = validate_solution_feasibility(bits_arr)

        top_states.append(QuantumStateDistribution(
            variable_bitstring=var_str,
            qiskit_bitstring=qiskit_str,
            bitstring=var_str,
            probability=round(float(prob), 4),
            shots_count=int(round(prob * final_shots)),
            economic_cost_inr=econ_c,
            qubo_energy=round(qubo_e, 2),
            is_feasible=is_feas,
            constraint_violations=viols
        ))

        # Select candidate: prioritize lowest QUBO energy
        if qubo_e < best_candidate_qubo:
            best_candidate_qubo = qubo_e
            best_candidate_bits = bits_arr

    if best_candidate_bits is None:
        best_candidate_bits = [0] * num_qubits

    # Final decode for the chosen QAOA candidate
    q_var_bitstring = "".join(str(b) for b in best_candidate_bits)
    q_qiskit_bitstring = "".join(str(best_candidate_bits[num_qubits - 1 - q]) for q in range(num_qubits))
    q_economic_cost = calculate_economic_cost(best_candidate_bits)
    q_qubo_energy = round(compute_qubo_energy(best_candidate_bits), 2)
    q_feasible, q_violations = validate_solution_feasibility(best_candidate_bits)
    q_schedules = decode_schedules(best_candidate_bits)

    quantum_data = {
        "status": "FEASIBLE" if q_feasible else "INFEASIBLE",
        "economic_cost_inr": q_economic_cost,
        "qubo_objective_value": q_qubo_energy,
        "variable_bitstring": q_var_bitstring,
        "qiskit_bitstring": q_qiskit_bitstring,
        "execution_time_seconds": round(q_time, 4),
        "qubit_count": num_qubits,
        "circuit_depth": circuit_depth,
        "gate_counts": gate_counts,
        "is_feasible": q_feasible,
        "constraint_violations": q_violations,
        "schedules": [s.model_dump() for s in q_schedules],
        "top_states": [st.model_dump() for st in top_states]
    }

    # =========================================================================
    # FAIR COMPARISON & GAP ANALYSIS (TASK 5)
    # =========================================================================
    cost_diff = round(q_economic_cost - c_economic_cost, 2)
    exact_match = (q_var_bitstring == c_var_bitstring)
    runtime_ratio = round(q_time / max(0.0001, cp_time), 2)

    # Gaps
    classical_gap = 0.0 # CP-SAT is exact global minimum
    qaoa_gap = max(0.0, cost_diff) if q_feasible else 0.0

    summary_msg = (
        f"Classical OR-Tools CP-SAT: {classical_data['status']} at ₹{c_economic_cost:.2f} ({cp_time:.4f}s). "
        f"QAOA: {quantum_data['status']} at ₹{q_economic_cost:.2f} (QUBO energy: {q_qubo_energy:.2f}, {q_time:.4f}s). "
        f"Economic cost difference: ₹{cost_diff:.2f}. "
        f"Exact variable match: {'YES (Global optimum matched)' if exact_match else 'NO (Stochastic sample)'}."
    )

    elapsed_total = time.time() - start_benchmark
    logger.info(f"=== BENCHMARK COMPLETED in {elapsed_total:.3f}s: {summary_msg} ===")

    # Input specs dict for telemetry
    benchmark_inputs_summary = {
        "ev_ids": [str(e.get("ev_id")) for e in ev_records],
        "candidate_slots": candidate_slots,
        "tariff_prices_inr": prices_dict,
        "station_capacity_units": station_capacity,
        "unit_energy_mode": unit_energy_mode,
        "ev_specifications": [
            {
                "ev_id": str(e.get("ev_id")),
                "arrival_slot": int(e.get("arrival_slot", 0)),
                "departure_slot": int(e.get("departure_slot", 3)),
                "required_energy_kwh": float(e.get("required_energy_kwh", 1.0)),
                "charger_id": str(e.get("charger_id")),
                "maximum_power_kw": float(e.get("maximum_charging_power_kw", 7.2)),
                "charging_efficiency": float(e.get("charging_efficiency", 0.92))
            }
            for e in ev_records
        ]
    }

    return ComparisonBenchmarkResponse(
        instance_description=f"Immutable benchmark: {len(ev_records)} EVs, slots {candidate_slots}, station capacity {station_capacity}",
        ev_ids=[str(e.get("ev_id")) for e in ev_records],
        candidate_slots=candidate_slots,
        station_capacity_units=station_capacity,
        benchmark_inputs=benchmark_inputs_summary,
        qubit_mappings=qubit_mappings,
        classical_cpsat=classical_data,
        quantum_qaoa=quantum_data,
        cost_difference_inr=cost_diff,
        exact_match=exact_match,
        runtime_speedup_ratio=runtime_ratio,
        classical_optimality_gap_inr=classical_gap,
        qaoa_objective_gap_inr=qaoa_gap,
        summary=summary_msg
    )
