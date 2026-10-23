import time
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from ortools.sat.python import cp_model

from .models import (
    ClassicalOptRequest,
    ClassicalOptResponse,
    EVClassicalSchedule,
    HourlyGridMetric
)

def solve_classical_cpsat(
    tariffs_df: pd.DataFrame,
    evs_df: pd.DataFrame,
    request: ClassicalOptRequest
) -> ClassicalOptResponse:
    start_time = time.time()

    # Filter tariffs by profile
    profile_df = tariffs_df[tariffs_df["price_profile"].str.lower() == request.price_profile.lower()]
    if profile_df.empty:
        # fallback to first available profile
        profile_df = tariffs_df

    prices_dict: Dict[int, float] = {}
    time_labels: Dict[int, Tuple[str, str]] = {}
    for _, r in profile_df.iterrows():
        s = int(r["slot"])
        prices_dict[s] = float(r["price_inr_per_kwh"])
        time_labels[s] = (str(r.get("start_time", f"{s:02d}:00")), str(r.get("end_time", f"{s+1:02d}:00")))

    for s in range(24):
        if s not in prices_dict:
            prices_dict[s] = 8.0
            time_labels[s] = (f"{s:02d}:00", f"{(s+1)%24:02d}:00")

    # Filter EV subset if requested
    fleet = evs_df.copy()
    if request.ev_subset_ids:
        fleet = fleet[fleet["ev_id"].isin(request.ev_subset_ids)]

    if fleet.empty:
        return ClassicalOptResponse(
            status="EMPTY_FLEET",
            is_optimal=False,
            objective_cost_inr=0.0,
            execution_time_seconds=0.0,
            grid_peak_power_kw=0.0,
            grid_power_limit_kw=request.grid_power_limit_kw,
            total_energy_delivered_kwh=0.0,
            total_energy_required_kwh=0.0,
            overall_fulfillment_percent=0.0,
            ev_schedules=[],
            hourly_metrics=[],
            solver_status_code=0
        )

    model = cp_model.CpModel()
    SCALE = 1000 # 1 kW = 1000 units for integer precision

    # Map EVs
    ev_records = fleet.to_dict("records")
    p_vars = {} # (ev_idx, slot) -> IntVar power
    u_vars = {} # (ev_idx, slot) -> BoolVar charging state

    grid_limit_units = int(request.grid_power_limit_kw * SCALE)

    for i, ev in enumerate(ev_records):
        arr = int(ev["arrival_slot"])
        dep = int(ev["departure_slot"])
        p_max_units = int(float(ev["maximum_charging_power_kw"]) * SCALE)

        for t in range(24):
            if arr <= t < dep:
                u_vars[i, t] = model.NewBoolVar(f"u_{i}_{t}")
                p_vars[i, t] = model.NewIntVar(0, p_max_units, f"p_{i}_{t}")
                # Link power to indicator: p <= p_max * u
                model.Add(p_vars[i, t] <= p_max_units * u_vars[i, t])
            else:
                # Outside stay window
                p_vars[i, t] = model.NewConstant(0)
                u_vars[i, t] = model.NewConstant(0)

        # Energy requirement constraint
        eff = float(ev.get("charging_efficiency", 0.92))
        req_energy = float(ev["required_energy_kwh"])
        # Maximum energy deliverable in window
        window_hours = dep - arr
        max_possible = window_hours * float(ev["maximum_charging_power_kw"]) * eff
        target_energy = min(req_energy, max_possible)

        target_energy_units = int(target_energy * SCALE)
        # Sum of power * eff >= target_energy_units
        # Multiply by integer eff factor: int(eff * 1000)
        eff_scaled = int(round(eff * 1000))
        # sum(p) * eff_scaled >= target_energy_units * 1000
        window_p = [p_vars[i, t] for t in range(arr, dep)]
        if window_p:
            model.Add(sum(window_p) * eff_scaled >= target_energy_units * 1000)

    # Charger exclusivity constraints: at most one EV per charger per slot
    charger_evs: Dict[str, List[int]] = {}
    for i, ev in enumerate(ev_records):
        ch = str(ev["charger_id"])
        charger_evs.setdefault(ch, []).append(i)

    for ch, ev_indices in charger_evs.items():
        if len(ev_indices) > 1:
            for t in range(24):
                model.Add(sum(u_vars[i, t] for i in ev_indices) <= 1)

    # Grid transformer limit per slot
    for t in range(24):
        slot_p = [p_vars[i, t] for i in range(len(ev_records))]
        model.Add(sum(slot_p) <= grid_limit_units)

    # Peak demand tracking variable for load smoothing
    peak_var = model.NewIntVar(0, grid_limit_units, "peak_demand")
    for t in range(24):
        slot_p = [p_vars[i, t] for i in range(len(ev_records))]
        model.Add(peak_var >= sum(slot_p))

    # Objective: Minimize electricity cost + peak demand penalty
    # Cost = sum_t (Price_t * sum_i p_i,t)
    cost_terms = []
    for t in range(24):
        price_paise = int(round(prices_dict[t] * 100)) # in paise (0.01 INR)
        for i in range(len(ev_records)):
            cost_terms.append(p_vars[i, t] * price_paise)

    # Peak penalty in objective
    peak_penalty_scaled = int(round(request.peak_penalty_weight * 100))
    if peak_penalty_scaled > 0:
        total_objective = sum(cost_terms) + peak_var * peak_penalty_scaled
    else:
        total_objective = sum(cost_terms)

    model.Minimize(total_objective)

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = request.time_limit_seconds
    solver.parameters.num_workers = 4
    status_code = solver.Solve(model)
    solve_duration = time.time() - start_time

    status_name = solver.StatusName(status_code)
    is_optimal = (status_code == cp_model.OPTIMAL)
    is_feasible = (status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE))

    if not is_feasible:
        return ClassicalOptResponse(
            status=status_name,
            is_optimal=False,
            objective_cost_inr=0.0,
            execution_time_seconds=round(solve_duration, 4),
            grid_peak_power_kw=0.0,
            grid_power_limit_kw=request.grid_power_limit_kw,
            total_energy_delivered_kwh=0.0,
            total_energy_required_kwh=float(fleet["required_energy_kwh"].sum()),
            overall_fulfillment_percent=0.0,
            ev_schedules=[],
            hourly_metrics=[],
            solver_status_code=int(status_code)
        )

    # Extract Schedules
    ev_schedules: List[EVClassicalSchedule] = []
    total_delivered_all = 0.0
    total_required_all = float(fleet["required_energy_kwh"].sum())
    total_cost_all = 0.0

    for i, ev in enumerate(ev_records):
        arr = int(ev["arrival_slot"])
        dep = int(ev["departure_slot"])
        eff = float(ev.get("charging_efficiency", 0.92))
        batt = float(ev["battery_capacity_kwh"])
        init_soc = float(ev["initial_soc_percent"])
        req_energy = float(ev["required_energy_kwh"])

        hourly_p: List[float] = []
        active_slots: List[int] = []
        ev_energy_grid = 0.0
        ev_cost = 0.0

        for t in range(24):
            val_units = solver.Value(p_vars[i, t])
            kw = round(val_units / SCALE, 3)
            hourly_p.append(kw)
            if kw > 0.001:
                active_slots.append(t)
                ev_energy_grid += kw
                ev_cost += kw * prices_dict[t]

        ev_energy_batt = ev_energy_grid * eff
        added_soc = (ev_energy_batt / batt) * 100.0 if batt > 0 else 0.0
        final_soc = min(100.0, round(init_soc + added_soc, 2))
        fulfillment = min(100.0, round((ev_energy_batt / req_energy) * 100.0, 1)) if req_energy > 0 else 100.0

        total_delivered_all += ev_energy_batt
        total_cost_all += ev_cost

        ev_schedules.append(EVClassicalSchedule(
            ev_id=str(ev["ev_id"]),
            charger_id=str(ev["charger_id"]),
            arrival_slot=arr,
            departure_slot=dep,
            initial_soc_percent=init_soc,
            final_soc_percent=final_soc,
            required_energy_kwh=round(req_energy, 2),
            delivered_energy_kwh=round(ev_energy_batt, 2),
            energy_fulfillment_percent=fulfillment,
            charging_cost_inr=round(ev_cost, 2),
            charging_slots=active_slots,
            hourly_power_kw=hourly_p
        ))

    # Compute hourly grid metrics
    hourly_metrics: List[HourlyGridMetric] = []
    peak_power = 0.0

    for t in range(24):
        slot_total_p = sum(ev_schedules[i].hourly_power_kw[t] for i in range(len(ev_records)))
        if slot_total_p > peak_power:
            peak_power = slot_total_p

        headroom = max(0.0, request.grid_power_limit_kw - slot_total_p)
        slot_cost = slot_total_p * prices_dict[t]
        active_count = sum(1 for i in range(len(ev_records)) if ev_schedules[i].hourly_power_kw[t] > 0.001)

        t_start, t_end = time_labels.get(t, (f"{t:02d}:00", f"{(t+1)%24:02d}:00"))
        hourly_metrics.append(HourlyGridMetric(
            slot=t,
            start_time=t_start,
            end_time=t_end,
            price_inr=round(prices_dict[t], 2),
            total_power_kw=round(slot_total_p, 2),
            grid_limit_kw=round(request.grid_power_limit_kw, 2),
            grid_headroom_kw=round(headroom, 2),
            slot_cost_inr=round(slot_cost, 2),
            active_ev_count=active_count
        ))

    overall_fulfillment = min(100.0, round((total_delivered_all / total_required_all) * 100.0, 1)) if total_required_all > 0 else 100.0

    return ClassicalOptResponse(
        status=status_name,
        is_optimal=is_optimal,
        objective_cost_inr=round(total_cost_all, 2),
        execution_time_seconds=round(solve_duration, 4),
        grid_peak_power_kw=round(peak_power, 2),
        grid_power_limit_kw=request.grid_power_limit_kw,
        total_energy_delivered_kwh=round(total_delivered_all, 2),
        total_energy_required_kwh=round(total_required_all, 2),
        overall_fulfillment_percent=overall_fulfillment,
        ev_schedules=ev_schedules,
        hourly_metrics=hourly_metrics,
        solver_status_code=int(status_code)
    )
