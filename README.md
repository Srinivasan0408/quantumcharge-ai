# ⚛️ QuantiSpark — QuantumCharge AI

**VTU-QFF-HC-0154 | Tier: Online | VTU-Qiskit Fall Fest 2026**

### Hybrid Quantum-Classical EV Fleet Smart Charging Optimization Using Google OR-Tools CP-SAT and Qiskit QAOA

---

## 📌 Table of Contents

- [Team Members](#-team-members)
- [Problem Statement](#-problem-statement)
- [Proposed Solution](#-proposed-solution)
- [Approach & Architecture](#-approach--architecture)
- [Tech Stack](#️-tech-stack)
- [Project Structure](#-project-structure)
- [Datasets](#-datasets)
- [How to Run](#-how-to-run)
- [API Endpoints](#-api-endpoints)
- [Benchmarking and Evaluation](#-benchmarking-and-evaluation)
- [How to Push Code](#-how-to-push-code)
- [Submission Checklist](#-submission-checklist)
- [Resources](#-resources)
- [License](#-license)

---

## 👥 Team Members

| # | Name | GitHub Username | Role |
|---|---|---|---|
| 1 | Srinivasan V | [@Srinivasan0408](https://github.com/Srinivasan0408) | Team Lead |
| 2 | Sherin Raj R | Not provided | Developer |

**Team Name:** QuantiSpark  
**Team ID:** VTU-QFF-HC-0154  
**Tier:** Online  
**Event:** VTU-Qiskit Fall Fest 2026  
**Repository:** [vtu-hc-quantispark](https://github.com/vtu-qiskit-fall-fest-2026/vtu-hc-quantispark)

---

## ❓ Problem Statement

### Problem

Electric vehicle (EV) charging stations must schedule charging sessions while considering vehicle arrival and departure times, battery energy requirements, charger availability, station power limits, and time-varying electricity tariffs.

Uncoordinated charging can increase electricity costs, create coincident peak demand, and cause charging conflicts.

### Why It Matters

As EV adoption grows, charging operators need intelligent scheduling systems that deliver the required energy before vehicles depart while controlling operating costs and respecting grid capacity.

Optimization can help improve charger utilization, reduce unnecessary peak demand, and support more efficient charging infrastructure.

### Track and Category

- **Event:** VTU-Qiskit Fall Fest 2026
- **Tier:** Online
- **Project Domain:** Quantum Computing and Hybrid Optimization
- **Application:** EV Fleet Energy Management

---

## 💡 Proposed Solution

### QuantumCharge AI

QuantumCharge AI is a hybrid quantum-classical optimization platform that analyzes EV charging sessions and electricity tariff profiles to generate cost-aware charging schedules.

The platform uses Google OR-Tools CP-SAT to solve larger fleet scheduling problems and Qiskit QAOA to explore smaller binary optimization instances using a quantum-circuit simulator.

An interactive web dashboard supports CSV uploads, manual EV entry, data validation, telemetry visualization, schedule analysis, and side-by-side solver comparisons.

### Key Idea

> Combine reliable classical constraint optimization with experimental QAOA-based search to investigate hybrid approaches to EV charging scheduling.

### Key Features

- Models EV charging as a constrained scheduling problem.
- Uses electricity tariffs to calculate charging costs.
- Considers vehicle availability windows and energy targets.
- Supports charger constraints and station power limits.
- Uses classical optimization for larger fleet instances.
- Uses QAOA to explore smaller binary optimization problems.
- Independently validates candidate schedules and calculates economic costs.
- Separates electricity costs from QUBO penalty objectives.
- Displays solver status, execution time, feasibility, and benchmark results.
- Provides an interactive dashboard for analyzing and comparing results.

**Important:** QAOA runs using classical quantum-circuit simulation. This project investigates quantum optimization methods and does not claim a demonstrated quantum advantage.

---

## 🧩 Approach & Architecture

### 1. Input

The system accepts two principal CSV datasets.

#### EV Charging Sessions

Vehicle-level information can include:

- EV ID
- Arrival and departure slots
- Battery capacity
- Initial state of charge (SoC)
- Target SoC
- Required charging energy
- Maximum charging power
- Charging efficiency
- Charger ID

#### Electricity Tariff Profiles

Tariff information can include:

- Tariff profile
- Time slot
- Start and end time
- Electricity price in ₹/kWh

Users can also enter EV session details manually through the web interface.

### 2. Preprocessing and Validation

The backend parses uploaded CSV files and validates:

- Required columns and data types
- Missing or invalid values
- Arrival and departure time windows
- Energy and power ranges
- Tariff values and slot consistency
- Feasibility of the requested charging schedule

Validated records are used by the analysis and optimization modules.

### 3. Telemetry and Analysis

The analytics module calculates and visualizes:

- Total fleet energy requirement
- Number of active EVs
- Arrival and departure distributions
- Average parking duration
- Theoretical coincident peak demand
- Tariff variation across time slots
- Charger contention
- Grid capacity considerations

### 4. Classical Optimization — Google OR-Tools CP-SAT

The classical optimizer formulates charging decisions as a constrained scheduling model.

Its objective is to minimize electricity procurement cost, with optional peak-demand smoothing penalties.

The model can enforce:

- Vehicle arrival and departure windows
- Required charging energy
- Charger exclusivity
- Maximum charging power
- Station-level grid power limits
- Charging compatibility and scheduling constraints

The optimizer returns the solution status, charging schedule, economic cost, energy fulfillment, and peak-load metrics.

### 5. Quantum Optimization — Qiskit QAOA

The quantum module formulates a small binary charging problem as a Quadratic Unconstrained Binary Optimization (QUBO) model.

The workflow is:

1. Create binary decision variables for EV-slot charging assignments.
2. Construct the economic objective using grid energy and electricity tariffs.
3. Add penalty terms for constraint violations.
4. Map binary variables to Pauli operators using the QUBO-to-Ising transformation.
5. Construct a parameterized QAOA circuit.
6. Optimize circuit parameters using a classical optimizer such as COBYLA.
7. Sample measurement outcomes using a Qiskit-compatible simulator.
8. Decode measurement bitstrings into EV charging schedules.
9. Independently validate feasibility and calculate the actual economic cost.

QAOA explores candidate solutions but does not guarantee that every execution finds the global optimum.

### 6. Post-processing and Benchmarking

The comparison module evaluates classical and quantum approaches using the same benchmark input.

It distinguishes between:

- Economic electricity cost in INR
- QUBO penalized objective energy
- Solver status and feasibility
- Execution time
- Decision-variable ordering
- Qiskit measurement bitstrings
- Constraint violations
- Cost difference relative to the classical optimum, when comparable

Invalid candidates are identified rather than silently repaired and presented as valid results.

### 7. Output

The dashboard presents:

- Validated input datasets
- Fleet telemetry and tariff charts
- Classical charging schedules
- QAOA measurement results
- EV-slot allocation visualizations
- Solver performance metrics
- Side-by-side benchmark results

### Architecture Diagram

```text
EV Session CSV ─────┐
                    │
Tariff CSV ─────────┤
                    ├──> FastAPI Backend
Manual EV Entry ────┘         |
                              v
                    Validation and Analysis
                              |
                    ┌─────────┴─────────┐
                    v                   v
             OR-Tools CP-SAT       Qiskit QAOA
             Classical Solver      QUBO / Ising
                    |                   |
                    v                   v
             Classical Schedule   Sampled Candidate
                    |             + Feasibility Checks
                    └─────────┬─────────┘
                              v
                    Benchmark and Comparison
                              |
                              v
                    Interactive Web Dashboard
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Programming Language | Python 3.11+ |
| Quantum SDK | Qiskit |
| Quantum Optimization | Qiskit Optimization and QAOA |
| Quantum Simulation | Qiskit Aer or compatible Qiskit simulator |
| Classical Optimization | Google OR-Tools CP-SAT |
| Classical Optimizer | COBYLA through Qiskit Algorithms |
| Backend API | FastAPI |
| ASGI Server | Uvicorn |
| Frontend | HTML5, CSS3, JavaScript |
| Data Processing | Pandas and Python |
| Visualization | Chart.js |
| Data Format | CSV |
| Testing | Pytest |
| Development Environment | VS Code and Python virtual environment |
| Version Control | Git and GitHub |

The exact Qiskit and dependency versions should match the committed `requirements.txt`.

---

## 📁 Project Structure

```text
vtu-hc-quantispark/
├── README.md
├── requirements.txt
├── .gitignore
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── comparison.py
│   ├── classical_optimizer.py
│   ├── quantum_optimizer.py
│   ├── analyzer.py
│   ├── validation.py
│   └── static/
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── data/
│   ├── quantumcharge_ev_charging_dataset.csv
│   └── quantumcharge_operator_price_profiles.csv
├── tests/
│   ├── test_analyzer.py
│   ├── test_api.py
│   ├── test_benchmark_regression.py
│   ├── test_classical.py
│   ├── test_quantum.py
│   └── test_validation.py
└── test_integration.py
```

*Note: This is the intended project structure. Adjust the tree to match the files actually committed to the repository.*

---

## 📊 Datasets

### EV Charging Dataset

The EV dataset describes the charging requirements and availability of each vehicle.

Example fields:

```text
ev_id
arrival_slot
departure_slot
battery_capacity_kwh
initial_soc_percent
target_soc_percent
required_energy_kwh
maximum_charging_power_kw
charging_efficiency
charger_id
```

### Operator Price Profile Dataset

The tariff dataset contains electricity prices across different time slots and pricing profiles.

Example fields:

```text
profile
slot
start_time
end_time
tariff_price_inr_per_kwh
```

The exact CSV headers must match the schema accepted by the backend.

### Sample Data and Reproducibility

The application supports loading sample datasets for demonstration and testing.

The benchmark also includes a small reference instance intended to check cost calculations, bitstring decoding, and constraint handling.

Synthetic dataset results should be identified as demonstration results rather than real-world operational measurements.

---

## 🚀 How to Run

### Prerequisites

- Python 3.11 or newer
- Git
- Windows PowerShell, Linux terminal, or macOS terminal
- Access to the project repository

### 1. Clone the Repository

```bash
git clone https://github.com/vtu-qiskit-fall-fest-2026/vtu-hc-quantispark.git
cd vtu-hc-quantispark
```

You must have access to the repository if it is private.

### 2. Create a Virtual Environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, configure the appropriate local execution policy or run the virtual environment's Python executable directly.

**Linux/macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run Automated Tests

```bash
pytest -v
```

### 5. Run Integration Tests

If the repository contains `test_integration.py`, run:

```bash
python test_integration.py
```

If the actual integration test file has a different name, use that filename instead.

### 6. Start the Web Application

From the repository root:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the dashboard:

**http://127.0.0.1:8000**

FastAPI interactive API documentation:

**http://127.0.0.1:8000/docs**

### 7. Use the Dashboard

1. Upload the EV charging dataset.
2. Upload the operator tariff profile dataset.
3. Validate the uploaded data.
4. Review fleet energy and tariff telemetry.
5. Configure and run the classical CP-SAT optimizer.
6. Run the QAOA experiment on a supported small instance.
7. Run the reference benchmark.
8. Compare decoded schedules, costs, solver statuses, and feasibility.

**Note:** The QAOA simulator runs on classical hardware unless a separately configured quantum backend is explicitly used.

---

## 🔌 API Endpoints

The following endpoints are part of the intended application API. Confirm the actual route names and HTTP methods in `backend/main.py` or at `/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/upload/tariffs` | Upload electricity tariff CSV |
| POST | `/api/upload/ev-sessions` | Upload EV charging sessions CSV |
| POST | `/api/presets/load-sample` | Load demonstration datasets |
| GET | `/api/data/tariffs` | Retrieve tariff data |
| GET | `/api/data/ev-sessions` | Retrieve EV session data |
| POST | `/api/ev-sessions` | Add a manual EV session |
| DELETE | `/api/ev-sessions/{ev_id}` | Delete an EV session |
| POST | `/api/validate` | Validate active input data |
| POST | `/api/analyze` | Analyze fleet and tariff data |
| POST | `/api/optimize/classical` | Run classical CP-SAT optimization |
| POST | `/api/optimize/quantum` | Run QAOA optimization |
| POST | `/api/optimize/compare` | Compare classical and quantum results |
| POST | `/api/benchmark/reference-test` | Run the reproducible reference test |

---

## 📈 Benchmarking and Evaluation

### Full-Fleet Classical Optimization

The current development report describes a synthetic 25-EV scenario with the following reported results.

| Metric | Reported Result |
|---|---:|
| EV Count | 25 |
| Fleet Energy Requirement | 165.78 kWh |
| Substation Limit | 70 kW |
| Classical Solver Status | OPTIMAL |
| Total Electricity Cost | ₹808.10 |
| Coincident Peak Grid Load | 38.23 kW |
| Energy Demand Fulfillment | 100% |

These figures are reported development results. Reproduce them using the committed code and datasets before treating them as final benchmark evidence.

### Small Reference Benchmark

The reference instance uses two EVs, three time slots, tariffs of ₹8, ₹3, and ₹6 per kWh, and a one-unit simultaneous charging limit.

| Metric | Classical CP-SAT | QAOA |
|---|---|---|
| Problem Size | 6 binary variables | 6 qubits |
| Objective | Economic electricity cost | QUBO objective with penalties |
| Result | Reports an optimum when proven | Samples candidate solutions |
| Feasibility | Independently validated | Independently validated |
| Optimality Guarantee | Yes, if status is `OPTIMAL` | Not guaranteed |

For the simplified reference case, the expected classical minimum economic cost is **₹9.00**.

QAOA may sample the optimal schedule or a higher-cost feasible schedule. Report the measured result rather than forcing it to match the classical optimum.

### Evaluation Metrics

- Economic electricity cost (INR)
- Total energy delivered (kWh)
- Required-energy fulfillment
- Peak grid demand (kW)
- Charger and station constraint violations
- Classical solver status
- QAOA feasibility and sampled objective
- Runtime and circuit telemetry
- Cost gap relative to the classical optimum

### Limitations

- Sample datasets are synthetic.
- QAOA simulation cost and runtime depend on problem size and simulator configuration.
- QAOA does not guarantee global optimality for every run.
- Classical simulation is not equivalent to execution on physical quantum hardware.
- Claims of quantum advantage require controlled experiments, appropriate baselines, and reproducible evidence.

---

## 🔁 How to Push Code

### Configure Git (First Time Only)

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Use the email associated with your GitHub account if appropriate.

### Check Your Changes

```bash
git status
git diff
```

### Commit Your Work

```bash
git add README.md backend tests requirements.txt
git commit -m "docs: update QuantumCharge AI project documentation"
```

Add other required project files as appropriate.

Do not commit `.venv`, credentials, API keys, or other secrets.

### Push to GitHub

If you are working on a feature branch:

```bash
git checkout -b feature/final-benchmark-validation
git push -u origin feature/final-benchmark-validation
```

Then open a Pull Request on GitHub and request review.

If your team lead has instructed you to commit directly to `main`, follow the repository rules. Pull the latest changes and resolve conflicts before pushing.

### Commit Message Convention

| Prefix | Meaning |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation |
| `test:` | Tests added or corrected |
| `refactor:` | Code restructuring |
| `chore:` | Dependency or configuration changes |

---

## ✅ Submission Checklist

- [ ] Repository is accessible to hackathon judges.
- [ ] Correct team name and team ID are included.
- [ ] All team members and GitHub usernames are listed.
- [ ] Required collaborators have accepted repository invitations.
- [ ] README describes the actual implementation.
- [ ] `requirements.txt` contains the required dependencies.
- [ ] Project starts from a clean virtual environment.
- [ ] Automated tests have been run successfully.
- [ ] Integration tests have been run successfully.
- [ ] Both CSV datasets have documented schemas.
- [ ] Benchmark endpoint and frontend work together.
- [ ] Displayed economic costs match decoded schedules.
- [ ] Quantum feasibility checks are working.
- [ ] Screenshots or a demonstration video are linked.
- [ ] License file is present and consistent with repository requirements.
- [ ] Latest code has been pushed to the required branch.
- [ ] Submission summary has been completed on the hackathon portal.

---

## 📚 Resources

- **Project Repository:** [vtu-hc-quantispark](https://github.com/vtu-qiskit-fall-fest-2026/vtu-hc-quantispark)
- **Qiskit Documentation:** [https://docs.quantum.ibm.com/](https://docs.quantum.ibm.com/)
- **Qiskit Runtime:** [https://quantum.cloud.ibm.com/docs/](https://quantum.cloud.ibm.com/docs/)
- **Qiskit Aer Simulators:** [Qiskit Simulator Guide](https://docs.quantum.ibm.com/guides/simulators)
- **Qiskit Optimization:** [Qiskit Optimization Documentation](https://qiskit-community.github.io/qiskit-optimization/)
- **Google OR-Tools:** [Google Optimization Documentation](https://developers.google.com/optimization)
- **FastAPI:** [FastAPI Documentation](https://fastapi.tiangolo.com/)
- **Pytest:** [Pytest Documentation](https://docs.pytest.org/)
- **GitHub:** [GitHub Documentation](https://docs.github.com/)

---

## 📄 License

This project is intended to use the MIT License.

Include a `LICENSE` file containing the appropriate MIT License text before claiming that the repository is licensed under MIT.

---

**QuantiSpark · VTU-QFF-HC-0154 · Tier: Online**

*QuantumCharge AI — Hybrid quantum-classical optimization for smarter EV fleet charging.*

Built with Python, Google OR-Tools, FastAPI, and Qiskit for the VTU-Qiskit Fall Fest 2026 hackathon.

Websit link : https://quantumcharge-ai.onrender.com/
