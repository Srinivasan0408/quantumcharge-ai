# QiBits — Quantum & Classical EV Smart Charging Optimizer

QiBits is a hybrid quantum-classical optimization platform for electric vehicle (EV) charging fleet scheduling. It features:
- **FastAPI Backend**: Endpoints for dataset ingestion, schema validation, fleet telemetry, classical constraint programming, and genuine quantum execution.
- **Classical Optimization**: Google OR-Tools CP-SAT (Constraint Programming - Satisfiability) scheduling EVs across hourly time slots, minimizing total electricity cost while respecting charger capacity and substation grid limits.
- **Genuine Quantum Optimization**: Qiskit QAOA (Quantum Approximate Optimization Algorithm) formulating the EV charging schedule as a Quadratic Unconstrained Binary Optimization (QUBO) problem mapped to an Ising Pauli-$Z$ Hamiltonian. Executed on real parameterized circuits via Qiskit Aer / Statevector simulators.
- **Side-by-Side Benchmark**: Rigorous, mathematically consistent comparison between Classical CP-SAT and Quantum QAOA over identical immutable inputs with consistent economic cost units (kWh × ₹/kWh = ₹) and independent constraint validation.
- **Interactive Web UI**: A cyber-quantum dashboard connected to every backend endpoint with Chart.js telemetry, live Gantt schedule heatmaps, manual EV CRUD, and genuine solver error telemetry (0% fabricated data).

---

## 🚀 Windows PowerShell Installation & Startup

Follow these exact Windows PowerShell commands to set up and run QiBits:

### 1. Navigate to Project Directory
```powershell
cd C:\Users\srini\OneDrive\Documents\Qibits
```

### 2. Create and Activate Python Virtual Environment (Recommended)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### 3. Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the Automated Test Suite (Unit & Benchmark Regression)
```powershell
pytest -v
```

### 5. Run Live HTTP Integration Verification
```powershell
python run_integration_test.py
```

### 6. Start the FastAPI Application Server
```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 7. Open the Web Application
Open your web browser and navigate to:
```
http://127.0.0.1:8000
```
API Swagger documentation is available at: `http://127.0.0.1:8000/docs`

---

## 🔍 Root Cause Analysis of Previous Discrepancy (₹9.00 vs ₹65.70)

The observed benchmark discrepancy was caused by an **inconsistency in energy scaling and decoding between the classical subproblem formulation and the quantum decoding logic**:

1. **Unit Power vs Maximum Power Mismatch**:
   - In the previous classical CP-SAT subproblem, the objective was formulated assuming 1 kWh per slot:
     $$\text{Obj}_{\text{CP-SAT}} = \sum_{q} \text{Price}_s \cdot x_q \implies 4.50 + 4.50 = \text{₹}9.00$$
   - In the QAOA cost decoder, the code multiplied the slot tariff by each EV's maximum charging power $P_i^{\max}$:
     $$\text{Cost}_{\text{QAOA}} = \sum \text{Price}_s \cdot P_i^{\max} \implies (4.50 \times 7.2) + (4.50 \times 7.4) = 32.40 + 33.30 = \text{₹}65.70$$
   - However, the QAOA QUBO Hamiltonian linear coefficients did *not* include $P_i^{\max}$ either, creating a disconnect between what the quantum circuit was optimizing and how the final bill was displayed.

2. **Station Capacity Constraint**:
   - Station-level simultaneous unit limits were omitted from the subproblem QUBO, which only checked individual charger IDs. When EVs were assigned to different chargers, concurrent charging across the station was unconstrained.

3. **Bitstring Endianness**:
   - Qiskit standard measurement bitstrings follow little-endian ordering ($|q_{n-1} \dots q_0\rangle$), whereas Python lists are indexed left-to-right ($x_0 \dots x_{n-1}$). Variable-to-qubit mapping is now explicitly documented and verified.

---

## 🛠 Fixes Implemented

1. **Dedicated Benchmark Engine (`backend/comparison.py`)**:
   - Both solvers now receive an identical, immutable `problem_def` with identical EV specifications, candidate slots, tariffs, and station capacity.
   - Economic cost is strictly defined in consistent physical units:
     $$\text{Economic Cost} = \sum_{q} E_q^{\text{grid}} (\text{kWh}) \times \text{Tariff}_q (\text{₹/kWh}) \times x_q$$
2. **Economic Cost vs QUBO Energy Separation**:
   - QUBO objective values ($\text{Cost} + \text{Penalties}$) are tracked and displayed separately. The displayed electricity bill is strictly the economic tariff cost.
3. **Explicit Variable-to-Qubit Mapping & Endianness**:
   - Each decision variable $x_q$ explicitly maps to $(\text{EV}_i, \text{Slot}_t, \text{Charger}_c, E_q^{\text{grid}}, \text{Tariff}_q)$. Both variable bitstrings ($x_0 \dots x_{n-1}$) and Qiskit states ($|q_{n-1} \dots q_0\rangle$) are reported.
4. **Independent Feasibility Validation**:
   - Decoded QAOA candidates are independently checked against energy targets, stay windows, charger exclusivity, and station capacity limits without silent mutation. Infeasible solutions are flagged and their constraint violations reported.
5. **Reproducible Reference Test Case (Task 6)**:
   - Endpoint `/api/benchmark/reference-test` executes the reference test: EV001, EV003, tariffs $[8, 3, 6]$ ₹/kWh, station capacity 1 unit, unit energy mode (1 kWh/slot). CP-SAT finds the global minimum of **₹9.00** ($3 + 6$). QAOA evaluates the exact same formulation.

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/api/health` | Health status & Qiskit Aer availability |
| `POST` | `/api/presets/load-sample` | Loads built-in 96 tariffs and 25 EV sessions |
| `POST` | `/api/upload/tariffs` | Multipart CSV upload for tariffs |
| `POST` | `/api/upload/ev-sessions` | Multipart CSV upload for EV sessions |
| `POST` | `/api/validate` | Validates loaded datasets |
| `POST` | `/api/analyze` | Computes telemetry & contention |
| `POST` | `/api/optimize/classical` | Google OR-Tools CP-SAT full fleet scheduler |
| `POST` | `/api/optimize/quantum` | Genuine Qiskit QAOA quantum optimizer |
| `POST` | `/api/optimize/compare` | Mathematically consistent side-by-side benchmark |
| `POST` | `/api/benchmark/reference-test` | Task 6 reproducible test case (expected min ₹9.00) |
| `POST` | `/api/ev-sessions` | Add / edit an EV session |
| `DELETE` | `/api/ev-sessions/{ev_id}` | Delete an EV session |

---

## 🧪 Verification & Test Results

```
tests/test_analyzer.py::test_analyze_dataset PASSED                      [  5%]
tests/test_api.py::test_api_health PASSED                                [ 11%]
tests/test_api.py::test_load_sample_preset PASSED                        [ 17%]
tests/test_api.py::test_api_validate PASSED                              [ 23%]
tests/test_api.py::test_api_analyze PASSED                               [ 29%]
tests/test_api.py::test_api_optimize_classical PASSED                    [ 35%]
tests/test_api.py::test_api_optimize_quantum PASSED                      [ 41%]
tests/test_api.py::test_api_optimize_compare PASSED                      [ 47%]
tests/test_api.py::test_api_reproducible_reference_test PASSED           [ 52%]
tests/test_api.py::test_api_manual_ev_crud PASSED                        [ 58%]
tests/test_benchmark_regression.py::test_identical_benchmark_inputs PASSED [ 64%]
tests/test_benchmark_regression.py::test_reproducible_task6_reference_test PASSED [ 70%]
tests/test_benchmark_regression.py::test_economic_cost_versus_qubo_penalty_separation PASSED [ 76%]
tests/test_benchmark_regression.py::test_bitstring_endianness_and_mapping PASSED [ 82%]
tests/test_classical.py::test_classical_cpsat_solver PASSED              [ 88%]
tests/test_quantum.py::test_genuine_qaoa_execution PASSED                [ 94%]
tests/test_quantum.py::test_qaoa_infeasible_or_exceeded_error_handling PASSED [100%]

====================== 17 passed in 14.30s =======================
```
