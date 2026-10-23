import os
import io
import time
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    TariffRecord,
    EVSessionRecord,
    ValidationResponse,
    AnalysisResponse,
    ClassicalOptRequest,
    ClassicalOptResponse,
    QuantumOptRequest,
    QuantumOptResponse,
    ComparisonBenchmarkResponse
)
from .validator import validate_datasets
from .analyzer import analyze_dataset
from .classical_optimizer import solve_classical_cpsat
from .quantum_optimizer import run_genuine_qaoa, AER_AVAILABLE
from .comparison import run_rigorous_comparison_benchmark

app = FastAPI(
    title="QiBits EV Smart Charging Optimization API",
    description="Constraint-optimal classical (OR-Tools CP-SAT) and quantum (Qiskit QAOA) charging scheduler",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for active datasets
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TARIFFS_PATH = os.path.join(DATA_DIR, "tariffs.csv")
EVS_PATH = os.path.join(DATA_DIR, "ev_sessions.csv")

current_tariffs_df: pd.DataFrame = pd.DataFrame()
current_evs_df: pd.DataFrame = pd.DataFrame()

def load_initial_datasets():
    global current_tariffs_df, current_evs_df
    try:
        if os.path.exists(TARIFFS_PATH):
            current_tariffs_df = pd.read_csv(TARIFFS_PATH)
        if os.path.exists(EVS_PATH):
            current_evs_df = pd.read_csv(EVS_PATH)
    except Exception as e:
        print(f"Warning: Could not load initial CSVs: {e}")

load_initial_datasets()

# Mount static files
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "QiBits API is running. index.html not found in static folder."}

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "QiBits EV Smart Charging Optimizer",
        "aer_simulator_available": AER_AVAILABLE,
        "tariffs_records": len(current_tariffs_df),
        "ev_records": len(current_evs_df)
    }

@app.post("/api/presets/load-sample")
def load_sample_data():
    load_initial_datasets()
    return {
        "message": "Sample datasets successfully loaded.",
        "tariffs_count": len(current_tariffs_df),
        "evs_count": len(current_evs_df),
        "profiles": list(current_tariffs_df["price_profile"].unique()) if not current_tariffs_df.empty else [],
        "chargers": list(current_evs_df["charger_id"].unique()) if not current_evs_df.empty else []
    }

@app.post("/api/upload/tariffs")
async def upload_tariffs(file: UploadFile = File(...)):
    global current_tariffs_df
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
        current_tariffs_df = df
        return {
            "message": "Tariffs CSV successfully uploaded and loaded into active memory.",
            "filename": file.filename,
            "total_rows": len(df),
            "columns": list(df.columns)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

@app.post("/api/upload/ev-sessions")
async def upload_ev_sessions(file: UploadFile = File(...)):
    global current_evs_df
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
        current_evs_df = df
        return {
            "message": "EV Sessions CSV successfully uploaded and loaded into active memory.",
            "filename": file.filename,
            "total_rows": len(df),
            "columns": list(df.columns)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

@app.get("/api/data/tariffs")
def get_tariffs(profile: Optional[str] = None):
    if current_tariffs_df.empty:
        return []
    df = current_tariffs_df
    if profile:
        df = df[df["price_profile"].str.lower() == profile.lower()]
    return df.to_dict("records")

@app.get("/api/data/ev-sessions")
def get_ev_sessions():
    if current_evs_df.empty:
        return []
    return current_evs_df.to_dict("records")

@app.post("/api/ev-sessions")
def add_or_update_ev_session(ev: EVSessionRecord):
    global current_evs_df
    ev_dict = ev.model_dump()
    if current_evs_df.empty:
        current_evs_df = pd.DataFrame([ev_dict])
    else:
        # Check if exists
        idx = current_evs_df[current_evs_df["ev_id"] == ev.ev_id].index
        if len(idx) > 0:
            for k, v in ev_dict.items():
                current_evs_df.loc[idx[0], k] = v
        else:
            current_evs_df = pd.concat([current_evs_df, pd.DataFrame([ev_dict])], ignore_index=True)

    return {
        "message": f"EV {ev.ev_id} successfully saved to active dataset.",
        "total_evs": len(current_evs_df)
    }

@app.delete("/api/ev-sessions/{ev_id}")
def delete_ev_session(ev_id: str):
    global current_evs_df
    if current_evs_df.empty:
        raise HTTPException(status_code=404, detail="No EVs exist.")
    before_count = len(current_evs_df)
    current_evs_df = current_evs_df[current_evs_df["ev_id"] != ev_id].reset_index(drop=True)
    if len(current_evs_df) == before_count:
        raise HTTPException(status_code=404, detail=f"EV '{ev_id}' not found.")
    return {
        "message": f"EV '{ev_id}' removed.",
        "remaining_count": len(current_evs_df)
    }

@app.post("/api/validate", response_model=ValidationResponse)
def validate_active_datasets():
    if current_tariffs_df.empty or current_evs_df.empty:
        raise HTTPException(status_code=400, detail="Both Tariffs and EV Sessions datasets must be loaded before validation.")
    return validate_datasets(current_tariffs_df, current_evs_df)

@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_active_datasets():
    if current_tariffs_df.empty or current_evs_df.empty:
        raise HTTPException(status_code=400, detail="Both Tariffs and EV Sessions datasets must be loaded before analysis.")
    return analyze_dataset(current_tariffs_df, current_evs_df)

@app.post("/api/optimize/classical", response_model=ClassicalOptResponse)
def run_classical_optimizer(request: ClassicalOptRequest):
    if current_tariffs_df.empty or current_evs_df.empty:
        raise HTTPException(status_code=400, detail="Both Tariffs and EV Sessions datasets must be loaded before optimization.")
    return solve_classical_cpsat(current_tariffs_df, current_evs_df, request)

@app.post("/api/optimize/quantum", response_model=QuantumOptResponse)
def run_quantum_optimizer(request: QuantumOptRequest):
    if current_tariffs_df.empty or current_evs_df.empty:
        raise HTTPException(status_code=400, detail="Both Tariffs and EV Sessions datasets must be loaded before optimization.")
    return run_genuine_qaoa(current_tariffs_df, current_evs_df, request)

@app.post("/api/optimize/compare", response_model=ComparisonBenchmarkResponse)
def run_comparison_benchmark(request: QuantumOptRequest):
    """
    Solves the EXACT same small feasible problem with both Classical OR-Tools CP-SAT and Quantum QAOA.
    Ensures identical inputs, consistent objective formulations, and independent feasibility validation.
    """
    global current_tariffs_df, current_evs_df
    if current_tariffs_df.empty or current_evs_df.empty:
        load_initial_datasets()
    if current_tariffs_df.empty or current_evs_df.empty:
        raise HTTPException(status_code=400, detail="Datasets must be loaded before running benchmark.")

    try:
        return run_rigorous_comparison_benchmark(current_tariffs_df, current_evs_df, request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Comparison benchmark error: {str(e)}")

@app.api_route("/api/benchmark/reference-test", methods=["GET", "POST"], response_model=ComparisonBenchmarkResponse)
@app.api_route("/api/benchmark/reference", methods=["GET", "POST"], response_model=ComparisonBenchmarkResponse)
@app.api_route("/api/reference-test", methods=["GET", "POST"], response_model=ComparisonBenchmarkResponse)
def run_reproducible_reference_test(reps: int = 1, shots: int = 1024, max_iter: int = 30):
    """
    TASK 6: Reproducible reference test case.
    EV001: arr=0, dep=3, req=1.0 kWh, charger=CH01
    EV003: arr=0, dep=3, req=1.0 kWh, charger=CH03
    Hourly electricity prices: [8, 3, 6] INR/kWh (slots 0, 1, 2)
    Station capacity: 1 simultaneous charging unit.
    Expected global minimum cost: INR 9.00 (one EV in slot 1 at INR 3, one EV in slot 2 at INR 6).
    """
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
        price_profile="CustomReference",
        qaoa_reps=reps,
        shots=shots,
        max_iter=max_iter,
        penalty_demand=25.0,
        penalty_conflict=30.0,
        unit_energy_mode=True,
        station_capacity_units=1
    )

    dummy_tariffs = pd.DataFrame()
    dummy_evs = pd.DataFrame()

    return run_rigorous_comparison_benchmark(
        dummy_tariffs,
        dummy_evs,
        req,
        override_prices=override_prices,
        override_evs=override_evs
    )
