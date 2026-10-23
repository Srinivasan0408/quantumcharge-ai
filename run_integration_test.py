import sys
import threading
import time
import requests
import uvicorn
from backend.main import app

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(2)

BASE_URL = "http://127.0.0.1:8001"
print(f"Server started at {BASE_URL}. Running end-to-end HTTP integration tests...")

# 1. Health check
res = requests.get(f"{BASE_URL}/api/health")
assert res.status_code == 200, res.text
print("[OK] Health check:", res.json())

# 2. Static files
res_root = requests.get(f"{BASE_URL}/")
assert res_root.status_code == 200
assert "QiBits Optimization Hub" in res_root.text
print("[OK] Root index.html served")

res_css = requests.get(f"{BASE_URL}/static/styles.css")
assert res_css.status_code == 200
print("[OK] static/styles.css served")

res_js = requests.get(f"{BASE_URL}/static/app.js")
assert res_js.status_code == 200
print("[OK] static/app.js served")

# 3. Presets
res_load = requests.post(f"{BASE_URL}/api/presets/load-sample")
assert res_load.status_code == 200
print("[OK] Load sample presets:", res_load.json()["message"])

# 4. Validation
res_val = requests.post(f"{BASE_URL}/api/validate")
assert res_val.status_code == 200
val_data = res_val.json()
assert val_data["valid"] is True
print(f"[OK] Validation: valid={val_data['valid']}, tariffs={val_data['total_tariff_records']}, EVs={val_data['total_ev_records']}")

# 5. Analysis
res_an = requests.post(f"{BASE_URL}/api/analyze")
assert res_an.status_code == 200
an_data = res_an.json()
print(f"[OK] Analysis: {len(an_data['tariffs'])} tariff profiles, {an_data['fleet']['total_evs']} EVs, {an_data['fleet']['total_required_energy_kwh']} kWh required")

# 6. Classical CP-SAT
res_c = requests.post(f"{BASE_URL}/api/optimize/classical", json={
    "price_profile": "TimeOfUse",
    "grid_power_limit_kw": 70.0,
    "peak_penalty_weight": 0.05,
    "time_limit_seconds": 5.0
})
assert res_c.status_code == 200
c_data = res_c.json()
print(f"[OK] CP-SAT Solved: status={c_data['status']}, cost=INR {c_data['objective_cost_inr']}, peak={c_data['grid_peak_power_kw']} kW, time={c_data['execution_time_seconds']}s")

# 7. Quantum QAOA
res_q = requests.post(f"{BASE_URL}/api/optimize/quantum", json={
    "ev_ids": ["EV001", "EV003"],
    "candidate_slots": [0, 1, 2],
    "price_profile": "TimeOfUse",
    "qaoa_reps": 1,
    "shots": 1024,
    "max_iter": 15
})
assert res_q.status_code == 200
q_data = res_q.json()
print(f"[OK] Genuine QAOA Solved: qubits={q_data['qubit_count']}, bitstring={q_data['optimal_bitstring']}, cost=INR {q_data['optimal_cost_inr']}, time={q_data['execution_time_seconds']}s")

# 8. Side-by-side benchmark
res_bm = requests.post(f"{BASE_URL}/api/optimize/compare", json={
    "ev_ids": ["EV001", "EV003"],
    "candidate_slots": [0, 1, 2],
    "price_profile": "TimeOfUse",
    "qaoa_reps": 1,
    "shots": 1024,
    "max_iter": 15,
    "unit_energy_mode": True
})
assert res_bm.status_code == 200
bm_data = res_bm.json()
assert "benchmark_inputs" in bm_data
assert "station_capacity_units" in bm_data
assert "qubit_mappings" in bm_data
print(f"[OK] Comparison Benchmark: {bm_data['summary']}")

# 8b. Reproducible Reference Test via POST
res_ref_post = requests.post(f"{BASE_URL}/api/benchmark/reference-test?reps=1&shots=512&max_iter=10")
assert res_ref_post.status_code == 200, res_ref_post.text
ref_post_data = res_ref_post.json()
assert ref_post_data["classical_cpsat"]["economic_cost_inr"] == 9.00
assert ref_post_data["station_capacity_units"] == 1
assert len(ref_post_data["qubit_mappings"]) == 6
print(f"[OK] Reference Test (POST): Classical cost=INR {ref_post_data['classical_cpsat']['economic_cost_inr']}, QAOA cost=INR {ref_post_data['quantum_qaoa']['economic_cost_inr']}")

# 8c. Reproducible Reference Test via GET
res_ref_get = requests.get(f"{BASE_URL}/api/benchmark/reference-test")
assert res_ref_get.status_code == 200, res_ref_get.text
ref_get_data = res_ref_get.json()
assert ref_get_data["classical_cpsat"]["economic_cost_inr"] == 9.00
print(f"[OK] Reference Test (GET): Classical cost=INR {ref_get_data['classical_cpsat']['economic_cost_inr']}")

# 9. Manual EV CRUD
new_ev = {
    "arrival_slot": 1,
    "battery_capacity_kwh": 9.0,
    "charger_id": "CH04",
    "charging_efficiency": 0.93,
    "departure_slot": 6,
    "ev_id": "EV_INTEGRATION_TEST",
    "initial_soc_percent": 20.0,
    "maximum_charging_power_kw": 11.0,
    "required_energy_kwh": 6.5,
    "target_soc_percent": 85.0
}
res_add = requests.post(f"{BASE_URL}/api/ev-sessions", json=new_ev)
assert res_add.status_code == 200
print("[OK] Manual EV added:", res_add.json()["message"])

res_del = requests.delete(f"{BASE_URL}/api/ev-sessions/EV_INTEGRATION_TEST")
assert res_del.status_code == 200
print("[OK] Manual EV deleted:", res_del.json()["message"])

print("\n=======================================================")
print("ALL LIVE HTTP SERVER ENDPOINTS & INTEGRATION CHECKS PASSED!")
print("=======================================================")
