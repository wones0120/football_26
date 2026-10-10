"""Optional Large-GPP controls; omitted values preserve production behavior."""
from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR
from math import isfinite

LARGE_GPP_CONTROL_KEYS = ("max_lineup_overlap", "elevated_player_max_exposure",
                          "max_elevated_players_per_lineup")


def validate_large_gpp_controls(values, strategy="classic_large_gpp_v1"):
    if strategy in {"captain_single_lineup_v1", "classic_single_lineup_v1"}:
        # Active strategies validate shared user controls during normalization.
        return
    for key in LARGE_GPP_CONTROL_KEYS:
        value = values.get(key)
        if value is None:
            continue
        if strategy != "classic_large_gpp_v1":
            raise ValueError(f"{key} is a Classic Large-GPP control; Small Field uses its separate policy")
        if key == "elevated_player_max_exposure":
            if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{key} must be a finite rate from 0 through 1")
        elif type(value) is not int or not 0 <= value <= (8 if key == "max_lineup_overlap" else 9):
            raise ValueError(f"{key} must be a whole number from 0 through {8 if key == 'max_lineup_overlap' else 9}")


def apply_large_gpp_controls(config, options):
    validate_large_gpp_controls(options)
    overlap = options.get("max_lineup_overlap")
    rate = options.get("elevated_player_max_exposure")
    if overlap is None and rate is None:
        return config
    config = deepcopy(config)
    if overlap is not None:
        config.uniqueness_overlap = overlap
    if rate is not None:
        caps = config.portfolio_targets.player_exposure_caps
        for pid in options.get("elevated_player_ids") or []:
            caps[pid] = min(caps.get(pid, 1.0), rate)
    return config


def explicit_appearance_limit(entries, rate):
    """Mathematical floor, avoiding 50 * .58 becoming 28.999999999999996."""
    return int((Decimal(entries) * Decimal(str(rate))).to_integral_value(rounding=ROUND_FLOOR))


def validate_requested_overlap(requested, contract):
    """Fail before solving/persisting when an explicit request loses its cap."""
    value = requested.get("max_lineup_overlap")
    if value is None:
        return
    effective = contract["effective"]
    if (contract["requested"].get("max_lineup_overlap") != value
            or effective.get("max_lineup_overlap") != value
            or effective["resolved_config"].get("uniqueness_overlap") != value
            or contract["sources"].get("max_lineup_overlap") != "request"):
        raise ValueError("Large-GPP overlap consistency failure: explicit request disagrees with strategy contract")


def saved_portfolio_submission_trace(params):
    trace = params.get("portfolio_submission_trace")
    if not isinstance(trace, dict):
        return None
    contract = params.get("effective_strategy_contract") or {}
    return {**trace, "saved_contract_requested_value": (contract.get("requested") or {}).get("max_lineup_overlap")}
