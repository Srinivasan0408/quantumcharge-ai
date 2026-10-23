import time
import traceback
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
    QuantumOptResponse,
    QuantumStateDistribution,
    DecodedQuantumSchedule,
    QubitVariableMapping
)

logger = logging.getLogger("qibits.quantum")

def run_genuine_qaoa(
    tariffs_df: pd.DataFrame,
    evs_df: pd.DataFrame,
    request: QuantumOptRequest
) -> QuantumOptResponse:
    """
    Executes genuine Qiskit QAOA with explicit variable-to-qubit mapping,
    endianness clarity, and independent constraint validation.
    """
    start_time = time.time()
    convergence_history: List[float] = []

    try:
        # 1. Filter Tariff profile
        profile_df = tariffs_df[tariffs_df["price_profile"].str.lower() == request.price_profile.lower()]
        if profile_df.empty:
            profile_df = tariffs_df

        prices_dict: Dict[int, float] = {}
        for _, r in profile_df.iterrows():
            prices_dict[int(r["slot"])] = float(r["price_inr_per_kwh"])
        for s in range(24):
            if s not in prices_dict:
                prices_dict[s] = 8.0

        # 2. Select EV subset
        if request.ev_ids and len(request.ev_ids) > 0:
            selected_evs = evs_df[evs_df["ev_id"].isin(request.ev_ids)].copy()
        else:
            selected_evs = evs_df.head(2).copy()

        if selected_evs.empty:
            raise ValueError("No valid EVs found for quantum optimization.")

        if len(selected_evs) > 6:
            raise ValueError(
                f"Quantum simulation limit exceeded: {len(selected_evs)} EVs requested. "
                "Please select between 2 and 4 EVs to maintain feasible circuit simulation."
            )

        # Determine candidate slots
        ev_records = selected_evs.to_dict("records")
        all_min_slot = min(int(e["arrival_slot"]) for e in ev_records)
        all_max_slot = max(int(e["departure_slot"]) for e in ev_records)

        if request.candidate_slots and len(request.candidate_slots) > 0:
            allowed_slots = sorted(request.candidate_slots)
        else:
            allowed_slots = list(range(all_min_slot, min(all_max_slot, all_min_slot + 3)))

        # 3. Create explicit qubit variable mapping (TASK 3)
        qubit_map: List[Tuple[int, str, int, str, float, float]] = []
        # (ev_idx, ev_id, slot, charger_id, grid_kwh, price)
        qubit_mappings: List[QubitVariableMapping] = []
        ev_slot_qubits: Dict[int, List[int]] = {i: [] for i in range(len(ev_records))}
        ev_k_slots: Dict[int, int] = {}

        unit_mode = bool(request.unit_energy_mode)

        for i, ev in enumerate(ev_records):
            ev_id = str(ev["ev_id"])
            ch = str(ev["charger_id"])
            arr = int(ev["arrival_slot"])
            dep = int(ev["departure_slot"])
            eff = float(ev.get("charging_efficiency", 0.92))
            p_max = float(ev["maximum_charging_power_kw"])
            req_e = float(ev["required_energy_kwh"])

            if unit_mode:
                grid_kwh_per_slot = 1.0
                k_needed = max(1, int(round(req_e / 1.0)))
            else:
                grid_kwh_per_slot = p_max * 1.0
                hourly_charge = grid_kwh_per_slot * eff
                k_needed = max(1, int(round(req_e / hourly_charge))) if hourly_charge > 0 else 1

            ev_k_slots[i] = k_needed

            valid_slots = [s for s in allowed_slots if arr <= s < dep]
            if not valid_slots:
                valid_slots = list(range(arr, min(dep, arr + 2)))

            for s in valid_slots:
                q_idx = len(qubit_map)
                price = prices_dict.get(s, 8.0)
                qubit_map.append((i, ev_id, s, ch, grid_kwh_per_slot, price))
                ev_slot_qubits[i].append(q_idx)

                qubit_mappings.append(QubitVariableMapping(
                    qubit_index=q_idx,
                    ev_id=ev_id,
                    slot=s,
                    charger_id=ch,
                    grid_energy_kwh=round(grid_kwh_per_slot, 3),
                    tariff_inr_per_kwh=round(price, 2),
                    cost_coefficient_inr=round(grid_kwh_per_slot * price, 3)
                ))

        num_qubits = len(qubit_map)
        if num_qubits < 1:
            raise ValueError("Zero qubits mapped. Ensure EV arrival/departure windows overlap with candidate slots.")
        if num_qubits > 16:
            raise ValueError(f"Problem requires {num_qubits} qubits, exceeding the simulator threshold (max 16 qubits).")

        # 4. Formulate QUBO (TASK 2)
        # Min C_econ(x) + A * DemandPenalties + B * ChargerConflicts + B_cap * StationCapacity
        A = float(request.penalty_demand)
        B_ch = float(request.penalty_conflict)
        B_cap = float(request.penalty_conflict)
        station_capacity = int(request.station_capacity_units)

        linear = {q: 0.0 for q in range(num_qubits)}
        quad: Dict[Tuple[int, int], float] = {}
        qubo_constant = 0.0

        # Linear term: grid_kwh * price (consistent economic basis)
        for q, (i, ev_id, s, ch, grid_kwh, price) in enumerate(qubit_map):
            linear[q] += grid_kwh * price

        # Demand penalty: A * (sum x_q - k)^2
        for i, q_list in ev_slot_qubits.items():
            k = ev_k_slots[i]
            qubo_constant += A * (k ** 2)
            for q in q_list:
                linear[q] += A * (1.0 - 2.0 * k)
            for idx1 in range(len(q_list)):
                for idx2 in range(idx1 + 1, len(q_list)):
                    pair = tuple(sorted((q_list[idx1], q_list[idx2])))
                    quad[pair] = quad.get(pair, 0.0) + 2.0 * A

        # Charger conflict penalty: same slot, same charger
        for q1 in range(num_qubits):
            i1, ev1_id, s1, ch1, _, _ = qubit_map[q1]
            for q2 in range(q1 + 1, num_qubits):
                i2, ev2_id, s2, ch2, _, _ = qubit_map[q2]
                if s1 == s2 and ch1 == ch2 and i1 != i2:
                    pair = (q1, q2)
                    quad[pair] = quad.get(pair, 0.0) + B_ch

        # Station capacity penalty (if capacity == 1)
        if station_capacity == 1:
            for q1 in range(num_qubits):
                i1, ev1_id, s1, ch1, _, _ = qubit_map[q1]
                for q2 in range(q1 + 1, num_qubits):
                    i2, ev2_id, s2, ch2, _, _ = qubit_map[q2]
                    if s1 == s2 and i1 != i2:
                        pair = (q1, q2)
                        if quad.get(pair, 0.0) < B_cap:
                            quad[pair] = quad.get(pair, 0.0) + B_cap

        # QUBO energy evaluation
        def compute_qubo_val(bits_arr: List[int]) -> float:
            cost = qubo_constant
            for q in range(num_qubits):
                if bits_arr[q]:
                    cost += linear[q]
            for (q1, q2), val in quad.items():
                if bits_arr[q1] and bits_arr[q2]:
                    cost += val
            return cost

        # Economic cost evaluation (genuine electricity bill)
        def compute_economic_cost(bits_arr: List[int]) -> float:
            cost = 0.0
            for q, (i, ev_id, s, ch, grid_kwh, price) in enumerate(qubit_map):
                if bits_arr[q]:
                    cost += grid_kwh * price
            return round(cost, 2)

        # 5. Convert QUBO to Ising Pauli-Z
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

        # 6. Build QAOA Circuit
        reps = int(request.qaoa_reps)
        ansatz = QAOAAnsatz(cost_operator=cost_hamiltonian, reps=reps)
        ansatz.measure_all()

        circuit_depth = ansatz.depth()
        gate_counts = {str(k): int(v) for k, v in ansatz.count_ops().items()}

        # 7. Setup Sampler
        if AER_AVAILABLE:
            sampler = AerSampler()
            is_aer = True
        else:
            sampler = StatevectorSampler()
            is_aer = False

        # Loss function for parameter optimization
        def qaoa_loss(params):
            if is_aer:
                job = sampler.run([ansatz], parameter_values=[params], shots=int(request.shots))
                quasi = job.result().quasi_dists[0]
            else:
                job = sampler.run([(ansatz, params)], shots=int(request.shots))
                meas_counts = job.result()[0].data.meas.get_counts()
                tot = sum(meas_counts.values())
                quasi = {int(k, 2): v / tot for k, v in meas_counts.items()}

            avg_energy = 0.0
            for state_int, prob in quasi.items():
                bits_arr = [(state_int >> q) & 1 for q in range(num_qubits)]
                avg_energy += prob * compute_qubo_val(bits_arr)

            convergence_history.append(float(round(avg_energy, 3)))
            return avg_energy

        # 8. Classical Parameter Optimization
        initial_params = np.random.uniform(0.1, 0.8, 2 * reps).tolist()
        opt_res = minimize(
            qaoa_loss,
            initial_params,
            method="COBYLA",
            options={"maxiter": int(request.max_iter)}
        )
        optimal_params = opt_res.x

        # 9. Sample with optimal parameters
        final_shots = max(1024, int(request.shots))
        if is_aer:
            final_job = sampler.run([ansatz], parameter_values=[optimal_params], shots=final_shots)
            final_quasi = final_job.result().quasi_dists[0]
        else:
            final_job = sampler.run([(ansatz, optimal_params)], shots=final_shots)
            raw_counts = final_job.result()[0].data.meas.get_counts()
            tot = sum(raw_counts.values())
            final_quasi = {int(k, 2): v / tot for k, v in raw_counts.items()}

        # 10. Independent Feasibility Validator (TASK 4)
        def validate_candidate(bits_arr: List[int]) -> Tuple[bool, List[str]]:
            violations: List[str] = []
            for i, q_list in ev_slot_qubits.items():
                req_slots = ev_k_slots[i]
                act_slots = sum(bits_arr[q] for q in q_list)
                if act_slots != req_slots:
                    violations.append(
                        f"EV '{ev_records[i]['ev_id']}' required {req_slots} slots but got {act_slots}"
                    )
            # Charger conflict
            charger_slots: Dict[Tuple[str, int], List[str]] = {}
            for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map):
                if bits_arr[q]:
                    charger_slots.setdefault((ch, s), []).append(ev_id)
            for (ch, s), ev_list in charger_slots.items():
                if len(ev_list) > 1:
                    violations.append(f"Charger conflict at slot {s} on {ch}: {', '.join(ev_list)}")

            # Station capacity
            slot_occ: Dict[int, int] = {}
            for q, (i, ev_id, s, ch, _, _) in enumerate(qubit_map):
                if bits_arr[q]:
                    slot_occ[s] = slot_occ.get(s, 0) + 1
            for s, occ in slot_occ.items():
                if occ > station_capacity:
                    violations.append(f"Station capacity exceeded at slot {s} ({occ} > {station_capacity})")

            return (len(violations) == 0, violations)

        # 11. Decode Top States (TASK 3)
        top_states: List[QuantumStateDistribution] = []
        best_candidate_bits: Optional[List[int]] = None
        best_qubo_val = float("inf")

        sorted_states = sorted(final_quasi.items(), key=lambda x: -x[1])[:10]

        for state_int, prob in sorted_states:
            bits_arr = [(state_int >> q) & 1 for q in range(num_qubits)]
            var_str = "".join(str(b) for b in bits_arr)
            qiskit_str = f"{state_int:0{num_qubits}b}"

            qubo_e = compute_qubo_val(bits_arr)
            econ_c = compute_economic_cost(bits_arr)
            is_feas, viols = validate_candidate(bits_arr)

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

            if qubo_e < best_qubo_val:
                best_qubo_val = qubo_e
                best_candidate_bits = bits_arr

        if best_candidate_bits is None:
            best_candidate_bits = [0] * num_qubits

        opt_var_str = "".join(str(b) for b in best_candidate_bits)
        opt_qiskit_str = "".join(str(best_candidate_bits[num_qubits - 1 - q]) for q in range(num_qubits))
        opt_econ_cost = compute_economic_cost(best_candidate_bits)
        opt_qubo_energy = round(compute_qubo_val(best_candidate_bits), 2)
        overall_feasible, violations = validate_candidate(best_candidate_bits)

        # Decode optimal schedule
        decoded_schedules: List[DecodedQuantumSchedule] = []
        for i, ev in enumerate(ev_records):
            ev_id = str(ev["ev_id"])
            ch = str(ev["charger_id"])
            q_list = ev_slot_qubits[i]
            k_target = ev_k_slots[i]
            eff = float(ev.get("charging_efficiency", 0.92))

            sched_slots = [qubit_map[q][2] for q in q_list if best_candidate_bits[q] == 1]
            act_kwh = sum(qubit_map[q][4] for q in q_list if best_candidate_bits[q] == 1)
            ev_cost = sum(qubit_map[q][4] * qubit_map[q][5] for q in q_list if best_candidate_bits[q] == 1)

            decoded_schedules.append(DecodedQuantumSchedule(
                ev_id=ev_id,
                charger_id=ch,
                required_slots=k_target,
                scheduled_slots=sorted(sched_slots),
                is_demand_satisfied=(len(sched_slots) == k_target),
                energy_delivered_kwh=round(act_kwh * eff, 3),
                cost_inr=round(ev_cost, 2)
            ))

        # 12. Run CP-SAT on the EXACT same formulation for attached comparison
        cp_model_inst = cp_model.CpModel()
        x_cp = [cp_model_inst.NewBoolVar(f"x_{q}") for q in range(num_qubits)]

        for i, q_list in ev_slot_qubits.items():
            cp_model_inst.Add(sum(x_cp[q] for q in q_list) == ev_k_slots[i])

        for (q1, q2), val in quad.items():
            if val >= B_ch or val >= B_cap:
                cp_model_inst.Add(x_cp[q1] + x_cp[q2] <= 1)

        cp_obj = sum(
            int(round(qubit_map[q][4] * qubit_map[q][5] * 100)) * x_cp[q]
            for q in range(num_qubits)
        )
        cp_model_inst.Minimize(cp_obj)

        cp_solver = cp_model.CpSolver()
        cp_start = time.time()
        cp_status = cp_solver.Solve(cp_model_inst)
        cp_time = time.time() - cp_start

        classical_comparison = None
        if cp_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            cp_bits = [int(cp_solver.Value(x_cp[q])) for q in range(num_qubits)]
            cp_var_bitstr = "".join(str(b) for b in cp_bits)
            cp_cost = sum(qubit_map[q][4] * qubit_map[q][5] * cp_bits[q] for q in range(num_qubits))

            matched = (cp_var_bitstr == opt_var_str)
            classical_comparison = {
                "status": cp_solver.StatusName(cp_status),
                "optimal_bitstring": cp_var_bitstr,
                "optimal_cost_inr": round(cp_cost, 2),
                "solve_time_seconds": round(cp_time, 4),
                "matched_quantum": matched
            }

        elapsed = time.time() - start_time

        return QuantumOptResponse(
            success=True,
            error=None,
            execution_time_seconds=round(elapsed, 4),
            qubit_count=num_qubits,
            circuit_depth=circuit_depth,
            gate_counts=gate_counts,
            optimal_variable_bitstring=opt_var_str,
            optimal_qiskit_bitstring=opt_qiskit_str,
            optimal_bitstring=opt_var_str,
            optimal_economic_cost_inr=opt_econ_cost,
            optimal_cost_inr=opt_econ_cost,
            optimal_qubo_energy=opt_qubo_energy,
            is_feasible=overall_feasible,
            constraint_violations=violations,
            schedules=decoded_schedules,
            top_states=top_states,
            qubit_mappings=qubit_mappings,
            optimization_convergence=convergence_history[-20:] if len(convergence_history) > 20 else convergence_history,
            classical_comparison=classical_comparison
        )

    except Exception as e:
        elapsed = time.time() - start_time
        err_msg = f"{type(e).__name__}: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        logger.error(f"QAOA execution error: {err_msg}")
        return QuantumOptResponse(
            success=False,
            error=err_msg,
            execution_time_seconds=round(elapsed, 4),
            qubit_count=0,
            circuit_depth=0,
            gate_counts={},
            optimal_variable_bitstring="",
            optimal_qiskit_bitstring="",
            optimal_bitstring="",
            optimal_economic_cost_inr=0.0,
            optimal_cost_inr=0.0,
            optimal_qubo_energy=0.0,
            is_feasible=False,
            constraint_violations=[str(e)],
            schedules=[],
            top_states=[],
            qubit_mappings=[],
            optimization_convergence=[],
            classical_comparison=None
        )
