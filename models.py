from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator

class TariffRecord(BaseModel):
    operator_id: str = Field(..., description="Unique operator code")
    operator_name: str = Field("Charging Operator", description="Operator display name")
    price_profile: str = Field(..., description="Tariff profile: Flat, Peak_OffPeak, TimeOfUse, SolarSurplus")
    slot: int = Field(..., ge=0, le=23, description="Hourly time slot [0-23]")
    start_time: str = Field(..., description="Slot start time (HH:MM)")
    end_time: str = Field(..., description="Slot end time (HH:MM)")
    price_inr_per_kwh: float = Field(..., ge=0.0, description="Electricity price in INR per kWh")
    currency: str = Field("INR", description="Currency code")
    is_synthetic: bool = Field(True, description="Whether data is synthetic")

class EVSessionRecord(BaseModel):
    ev_id: str = Field(..., description="Unique EV identifier")
    charger_id: str = Field(..., description="Designated charger ID (e.g. CH01)")
    arrival_slot: int = Field(..., ge=0, le=23, description="Arrival time slot [0-23]")
    departure_slot: int = Field(..., ge=1, le=24, description="Departure time slot [1-24]")
    battery_capacity_kwh: float = Field(..., gt=0.0, description="Battery total capacity in kWh")
    initial_soc_percent: float = Field(..., ge=0.0, le=100.0, description="Initial State of Charge (%)")
    target_soc_percent: float = Field(..., ge=0.0, le=100.0, description="Target State of Charge (%)")
    maximum_charging_power_kw: float = Field(..., gt=0.0, description="Maximum charging rate in kW")
    charging_efficiency: float = Field(0.92, gt=0.0, le=1.0, description="Charging efficiency factor (0.0-1.0]")
    required_energy_kwh: float = Field(..., ge=0.0, description="Required energy to reach target SOC")

    @field_validator('target_soc_percent')
    @classmethod
    def check_soc(cls, v, info):
        if 'initial_soc_percent' in info.data and v < info.data['initial_soc_percent']:
            raise ValueError('target_soc_percent must be >= initial_soc_percent')
        return v

    @field_validator('departure_slot')
    @classmethod
    def check_departure(cls, v, info):
        if 'arrival_slot' in info.data and v <= info.data['arrival_slot']:
            raise ValueError('departure_slot must be strictly greater than arrival_slot')
        return v

class ValidationErrorItem(BaseModel):
    row: Optional[int] = None
    field: Optional[str] = None
    message: str
    severity: str = "ERROR" # ERROR or WARNING

class ValidationResponse(BaseModel):
    valid: bool
    total_tariff_records: int
    total_ev_records: int
    tariff_profiles_found: List[str]
    chargers_found: List[str]
    errors: List[ValidationErrorItem]
    warnings: List[ValidationErrorItem]

class TariffProfileStats(BaseModel):
    profile_name: str
    slots_count: int
    min_price: float
    max_price: float
    mean_price: float
    peak_slot: int
    peak_price: float
    off_peak_slot: int
    off_peak_price: float

class EVFleetStats(BaseModel):
    total_evs: int
    total_required_energy_kwh: float
    avg_battery_capacity_kwh: float
    avg_initial_soc: float
    avg_target_soc: float
    avg_max_power_kw: float
    avg_stay_duration_slots: float
    charger_allocations: Dict[str, int]
    arrival_distribution: Dict[int, int]
    departure_distribution: Dict[int, int]

class AnalysisResponse(BaseModel):
    tariffs: List[TariffProfileStats]
    fleet: EVFleetStats
    feasibility_status: str
    feasibility_notes: List[str]
    theoretical_peak_demand_kw: float

class ClassicalOptRequest(BaseModel):
    price_profile: str = "TimeOfUse"
    grid_power_limit_kw: float = Field(60.0, gt=0.0, description="Total substation grid power limit in kW")
    peak_penalty_weight: float = Field(0.05, ge=0.0, description="Penalty coefficient for peak demand smoothing")
    time_limit_seconds: float = Field(10.0, gt=0.1, le=120.0, description="Solver timeout in seconds")
    ev_subset_ids: Optional[List[str]] = Field(None, description="Optional subset of EV IDs to optimize (defaults to all)")

class EVClassicalSchedule(BaseModel):
    ev_id: str
    charger_id: str
    arrival_slot: int
    departure_slot: int
    initial_soc_percent: float
    final_soc_percent: float
    required_energy_kwh: float
    delivered_energy_kwh: float
    energy_fulfillment_percent: float
    charging_cost_inr: float
    charging_slots: List[int]
    hourly_power_kw: List[float]

class HourlyGridMetric(BaseModel):
    slot: int
    start_time: str
    end_time: str
    price_inr: float
    total_power_kw: float
    grid_limit_kw: float
    grid_headroom_kw: float
    slot_cost_inr: float
    active_ev_count: int

class ClassicalOptResponse(BaseModel):
    status: str
    is_optimal: bool
    objective_cost_inr: float
    execution_time_seconds: float
    grid_peak_power_kw: float
    grid_power_limit_kw: float
    total_energy_delivered_kwh: float
    total_energy_required_kwh: float
    overall_fulfillment_percent: float
    ev_schedules: List[EVClassicalSchedule]
    hourly_metrics: List[HourlyGridMetric]
    solver_name: str = "Google OR-Tools CP-SAT"
    solver_status_code: int

class QubitVariableMapping(BaseModel):
    qubit_index: int
    ev_id: str
    slot: int
    charger_id: str
    grid_energy_kwh: float
    tariff_inr_per_kwh: float
    cost_coefficient_inr: float

class QuantumOptRequest(BaseModel):
    ev_ids: Optional[List[str]] = Field(None, description="2 to 4 EV IDs for the quantum problem")
    candidate_slots: Optional[List[int]] = Field(None, description="Candidate slots to consider (e.g. [0, 1, 2])")
    price_profile: str = "TimeOfUse"
    qaoa_reps: int = Field(1, ge=1, le=4, description="Number of QAOA layers (p)")
    shots: int = Field(1024, ge=100, le=8192, description="Quantum measurement shots")
    max_iter: int = Field(30, ge=5, le=100, description="Classical optimizer max iterations")
    penalty_demand: float = Field(25.0, gt=0.0, description="QUBO penalty for violating energy demand")
    penalty_conflict: float = Field(30.0, gt=0.0, description="QUBO penalty for charger conflict / station limit")
    classical_optimizer: str = "COBYLA"
    unit_energy_mode: bool = Field(False, description="Whether each slot is treated as exactly 1 kWh (benchmark test mode)")
    station_capacity_units: int = Field(1, ge=1, description="Max simultaneous charging units across station")

class QuantumStateDistribution(BaseModel):
    variable_bitstring: str = Field(..., description="Bitstring in variable index order (x_0 x_1 ... x_{n-1})")
    qiskit_bitstring: str = Field(..., description="Bitstring in Qiskit standard little-endian order (q_{n-1} ... q_0)")
    bitstring: str = Field(..., description="Backward-compatible bitstring field (matches variable_bitstring)")
    probability: float
    shots_count: int
    economic_cost_inr: float
    qubo_energy: float
    is_feasible: bool
    constraint_violations: List[str] = []

class DecodedQuantumSchedule(BaseModel):
    ev_id: str
    charger_id: str
    required_slots: int
    scheduled_slots: List[int]
    is_demand_satisfied: bool
    energy_delivered_kwh: float
    cost_inr: float

class QuantumOptResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    execution_time_seconds: float
    qubit_count: int
    circuit_depth: int
    gate_counts: Dict[str, int]
    optimal_variable_bitstring: str = ""
    optimal_qiskit_bitstring: str = ""
    optimal_bitstring: str = ""
    optimal_economic_cost_inr: float = 0.0
    optimal_cost_inr: float = 0.0
    optimal_qubo_energy: float = 0.0
    is_feasible: bool = False
    constraint_violations: List[str] = []
    schedules: List[DecodedQuantumSchedule] = []
    top_states: List[QuantumStateDistribution] = []
    qubit_mappings: List[QubitVariableMapping] = []
    optimization_convergence: List[float] = []
    classical_comparison: Optional[Dict[str, Any]] = None

class ComparisonBenchmarkResponse(BaseModel):
    instance_description: str
    ev_ids: List[str]
    candidate_slots: List[int]
    station_capacity_units: int
    benchmark_inputs: Dict[str, Any]
    qubit_mappings: List[QubitVariableMapping]
    classical_cpsat: Dict[str, Any]
    quantum_qaoa: Dict[str, Any]
    cost_difference_inr: float
    exact_match: bool
    runtime_speedup_ratio: float
    classical_optimality_gap_inr: float = 0.0
    qaoa_objective_gap_inr: float = 0.0
    summary: str
