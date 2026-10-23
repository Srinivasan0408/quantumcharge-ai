import pandas as pd
import pytest
from backend.analyzer import analyze_dataset

def test_analyze_dataset():
    tariffs_df = pd.read_csv("data/tariffs.csv")
    evs_df = pd.read_csv("data/ev_sessions.csv")
    res = analyze_dataset(tariffs_df, evs_df)

    assert len(res.tariffs) == 4 # Flat, Peak_OffPeak, TimeOfUse, SolarSurplus
    profiles = {t.profile_name: t for t in res.tariffs}
    assert "TimeOfUse" in profiles
    assert profiles["TimeOfUse"].slots_count == 24
    assert profiles["TimeOfUse"].min_price == 4.5
    assert profiles["TimeOfUse"].max_price == 13.0

    assert res.fleet.total_evs == 25
    assert res.fleet.total_required_energy_kwh > 0
    assert "CH01" in res.fleet.charger_allocations
    assert len(res.fleet.arrival_distribution) == 24
    assert res.theoretical_peak_demand_kw > 100.0
