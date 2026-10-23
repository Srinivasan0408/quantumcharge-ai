import pandas as pd
from typing import List, Tuple, Dict, Any
from .models import ValidationErrorItem, ValidationResponse

REQUIRED_TARIFF_COLS = [
    "operator_id", "operator_name", "price_profile", "slot",
    "start_time", "end_time", "price_inr_per_kwh", "currency", "is_synthetic"
]

REQUIRED_EV_COLS = [
    "arrival_slot", "battery_capacity_kwh", "charger_id", "charging_efficiency",
    "departure_slot", "ev_id", "initial_soc_percent", "maximum_charging_power_kw",
    "required_energy_kwh", "target_soc_percent"
]

def validate_tariffs_dataframe(df: pd.DataFrame) -> Tuple[List[ValidationErrorItem], List[ValidationErrorItem]]:
    errors: List[ValidationErrorItem] = []
    warnings: List[ValidationErrorItem] = []

    # Check missing columns
    missing_cols = [c for c in REQUIRED_TARIFF_COLS if c not in df.columns]
    if missing_cols:
        errors.append(ValidationErrorItem(
            field="columns",
            message=f"Missing required tariff columns: {', '.join(missing_cols)}"
        ))
        return errors, warnings

    if df.empty:
        errors.append(ValidationErrorItem(message="Tariff dataset is empty"))
        return errors, warnings

    # Row-level validation
    for idx, row in df.iterrows():
        row_num = idx + 1
        # Slot validation
        try:
            slot = int(row["slot"])
            if not (0 <= slot <= 23):
                errors.append(ValidationErrorItem(
                    row=row_num, field="slot",
                    message=f"Slot must be between 0 and 23, found {slot}"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(
                row=row_num, field="slot", message="Slot must be an integer"
            ))

        # Price validation
        try:
            price = float(row["price_inr_per_kwh"])
            if price < 0:
                errors.append(ValidationErrorItem(
                    row=row_num, field="price_inr_per_kwh",
                    message=f"Price cannot be negative, found {price}"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(
                row=row_num, field="price_inr_per_kwh", message="Price must be a valid number"
            ))

    # Profile completeness
    for profile, group in df.groupby("price_profile"):
        slots = set(group["slot"].astype(int))
        if len(slots) < 24:
            missing_slots = sorted(list(set(range(24)) - slots))
            warnings.append(ValidationErrorItem(
                field="price_profile",
                severity="WARNING",
                message=f"Profile '{profile}' has only {len(slots)}/24 slots. Missing slots: {missing_slots}"
            ))

    return errors, warnings

def validate_ev_sessions_dataframe(df: pd.DataFrame) -> Tuple[List[ValidationErrorItem], List[ValidationErrorItem]]:
    errors: List[ValidationErrorItem] = []
    warnings: List[ValidationErrorItem] = []

    missing_cols = [c for c in REQUIRED_EV_COLS if c not in df.columns]
    if missing_cols:
        errors.append(ValidationErrorItem(
            field="columns",
            message=f"Missing required EV session columns: {', '.join(missing_cols)}"
        ))
        return errors, warnings

    if df.empty:
        errors.append(ValidationErrorItem(message="EV session dataset is empty"))
        return errors, warnings

    ev_ids_seen = set()

    for idx, row in df.iterrows():
        row_num = idx + 1
        ev_id = str(row["ev_id"]).strip()
        if not ev_id:
            errors.append(ValidationErrorItem(row=row_num, field="ev_id", message="EV ID cannot be empty"))
        elif ev_id in ev_ids_seen:
            warnings.append(ValidationErrorItem(
                row=row_num, field="ev_id", severity="WARNING",
                message=f"Duplicate EV ID '{ev_id}' encountered"
            ))
        ev_ids_seen.add(ev_id)

        try:
            arr = int(row["arrival_slot"])
            dep = int(row["departure_slot"])
            if not (0 <= arr <= 23):
                errors.append(ValidationErrorItem(row=row_num, field="arrival_slot", message=f"Arrival slot must be 0-23, found {arr}"))
            if not (1 <= dep <= 24):
                errors.append(ValidationErrorItem(row=row_num, field="departure_slot", message=f"Departure slot must be 1-24, found {dep}"))
            if arr >= dep:
                errors.append(ValidationErrorItem(
                    row=row_num, field="departure_slot",
                    message=f"Departure slot ({dep}) must be strictly greater than arrival slot ({arr})"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_num, field="slots", message="Arrival and departure slots must be integers"))

        try:
            init_soc = float(row["initial_soc_percent"])
            target_soc = float(row["target_soc_percent"])
            if not (0.0 <= init_soc <= 100.0):
                errors.append(ValidationErrorItem(row=row_num, field="initial_soc_percent", message=f"Initial SOC must be between 0 and 100, found {init_soc}"))
            if not (0.0 <= target_soc <= 100.0):
                errors.append(ValidationErrorItem(row=row_num, field="target_soc_percent", message=f"Target SOC must be between 0 and 100, found {target_soc}"))
            if init_soc > target_soc:
                errors.append(ValidationErrorItem(
                    row=row_num, field="target_soc_percent",
                    message=f"Target SOC ({target_soc}%) cannot be less than initial SOC ({init_soc}%)"
                ))
        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_num, field="soc", message="SOC values must be numeric"))

        try:
            batt = float(row["battery_capacity_kwh"])
            if batt <= 0:
                errors.append(ValidationErrorItem(row=row_num, field="battery_capacity_kwh", message=f"Battery capacity must be positive, found {batt}"))
            
            p_max = float(row["maximum_charging_power_kw"])
            if p_max <= 0:
                errors.append(ValidationErrorItem(row=row_num, field="maximum_charging_power_kw", message=f"Max charging power must be positive, found {p_max}"))

            eff = float(row["charging_efficiency"])
            if not (0.0 < eff <= 1.0):
                errors.append(ValidationErrorItem(row=row_num, field="charging_efficiency", message=f"Charging efficiency must be in (0, 1], found {eff}"))

            req_e = float(row["required_energy_kwh"])
            if req_e < 0:
                errors.append(ValidationErrorItem(row=row_num, field="required_energy_kwh", message=f"Required energy cannot be negative, found {req_e}"))

            # Feasibility check on maximum possible energy delivery in stay window
            duration = dep - arr
            max_possible_energy = duration * p_max * eff
            if req_e > max_possible_energy:
                warnings.append(ValidationErrorItem(
                    row=row_num, field="required_energy_kwh", severity="WARNING",
                    message=f"Required energy ({req_e:.2f} kWh) exceeds theoretical maximum charge in stay window ({max_possible_energy:.2f} kWh)"
                ))

        except (ValueError, TypeError):
            errors.append(ValidationErrorItem(row=row_num, field="numeric_specs", message="Specs (battery, power, efficiency, energy) must be numeric"))

    return errors, warnings

def validate_datasets(tariffs_df: pd.DataFrame, evs_df: pd.DataFrame) -> ValidationResponse:
    t_errs, t_warns = validate_tariffs_dataframe(tariffs_df)
    ev_errs, ev_warns = validate_ev_sessions_dataframe(evs_df)

    all_errors = t_errs + ev_errs
    all_warnings = t_warns + ev_warns

    profiles = sorted(list(tariffs_df["price_profile"].unique())) if "price_profile" in tariffs_df.columns else []
    chargers = sorted(list(evs_df["charger_id"].unique())) if "charger_id" in evs_df.columns else []

    return ValidationResponse(
        valid=(len(all_errors) == 0),
        total_tariff_records=len(tariffs_df),
        total_ev_records=len(evs_df),
        tariff_profiles_found=profiles,
        chargers_found=chargers,
        errors=all_errors,
        warnings=all_warnings
    )
