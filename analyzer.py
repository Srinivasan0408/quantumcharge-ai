import pandas as pd
import numpy as np
from typing import List, Dict, Any
from .models import AnalysisResponse, TariffProfileStats, EVFleetStats

def analyze_dataset(tariffs_df: pd.DataFrame, evs_df: pd.DataFrame) -> AnalysisResponse:
    tariff_stats: List[TariffProfileStats] = []
    
    if not tariffs_df.empty and "price_profile" in tariffs_df.columns and "price_inr_per_kwh" in tariffs_df.columns:
        for profile, group in tariffs_df.groupby("price_profile"):
            prices = group["price_inr_per_kwh"].astype(float).values
            slots = group["slot"].astype(int).values
            max_idx = int(np.argmax(prices))
            min_idx = int(np.argmin(prices))
            tariff_stats.append(TariffProfileStats(
                profile_name=str(profile),
                slots_count=len(group),
                min_price=float(np.min(prices)),
                max_price=float(np.max(prices)),
                mean_price=float(np.mean(prices)),
                peak_slot=int(slots[max_idx]),
                peak_price=float(prices[max_idx]),
                off_peak_slot=int(slots[min_idx]),
                off_peak_price=float(prices[min_idx])
            ))

    total_evs = len(evs_df)
    charger_allocs: Dict[str, int] = {}
    arrival_dist: Dict[int, int] = {s: 0 for s in range(24)}
    departure_dist: Dict[int, int] = {s: 0 for s in range(25)}
    feasibility_notes: List[str] = []
    total_energy = 0.0
    avg_batt = 0.0
    avg_init_soc = 0.0
    avg_target_soc = 0.0
    avg_p_max = 0.0
    avg_duration = 0.0
    theo_peak_kw = 0.0

    if not evs_df.empty:
        total_energy = float(evs_df["required_energy_kwh"].sum())
        avg_batt = float(evs_df["battery_capacity_kwh"].mean())
        avg_init_soc = float(evs_df["initial_soc_percent"].mean())
        avg_target_soc = float(evs_df["target_soc_percent"].mean())
        avg_p_max = float(evs_df["maximum_charging_power_kw"].mean())
        theo_peak_kw = float(evs_df["maximum_charging_power_kw"].sum())

        durations = evs_df["departure_slot"].astype(int) - evs_df["arrival_slot"].astype(int)
        avg_duration = float(durations.mean())

        for ch, count in evs_df["charger_id"].value_counts().items():
            charger_allocs[str(ch)] = int(count)

        for arr in evs_df["arrival_slot"].astype(int):
            if 0 <= arr < 24:
                arrival_dist[arr] += 1

        for dep in evs_df["departure_slot"].astype(int):
            if 0 <= dep <= 24:
                departure_dist[dep] += 1

        # Check charger slot contention
        contention_count = 0
        for ch, group in evs_df.groupby("charger_id"):
            slot_occupancy = [0] * 24
            for _, r in group.iterrows():
                for s in range(int(r["arrival_slot"]), min(24, int(r["departure_slot"]))):
                    slot_occupancy[s] += 1
            max_occ = max(slot_occupancy) if slot_occupancy else 0
            if max_occ > 1:
                contention_count += 1
                feasibility_notes.append(
                    f"Charger '{ch}' has overlapping EV stay windows (peak {max_occ} EVs queued simultaneously). Solver must sequence charges."
                )

        if contention_count == 0:
            feasibility_status = "OPTIMAL_CAPACITY (No charger contention detected)"
        else:
            feasibility_status = f"CONTENTION_DETECTED ({contention_count} chargers have overlapping demand)"
    else:
        feasibility_status = "NO_EV_DATA"

    fleet_stats = EVFleetStats(
        total_evs=total_evs,
        total_required_energy_kwh=round(total_energy, 2),
        avg_battery_capacity_kwh=round(avg_batt, 2),
        avg_initial_soc=round(avg_init_soc, 1),
        avg_target_soc=round(avg_target_soc, 1),
        avg_max_power_kw=round(avg_p_max, 2),
        avg_stay_duration_slots=round(avg_duration, 2),
        charger_allocations=charger_allocs,
        arrival_distribution=arrival_dist,
        departure_distribution=departure_dist
    )

    return AnalysisResponse(
        tariffs=tariff_stats,
        fleet=fleet_stats,
        feasibility_status=feasibility_status,
        feasibility_notes=feasibility_notes,
        theoretical_peak_demand_kw=round(theo_peak_kw, 2)
    )
