"""Normal Captain role qualification; no player scores or FLEX eligibility change.

These conservative evidence floors are an operational football-role policy, not
calibrated winning probabilities. Allocated projection proxies, salary, P90 and
an Analyst narrative never establish a receiving workload or expanded role.
"""
from collections.abc import Mapping
import math

import pandas as pd

POLICY_ID = 'showdown_supported_captain_workload_v1'
FLOORS = dict(receiving_targets=5, receiving_share=.15, established_receiving_share=.20, latest_receiving_share=.15,
              rushing_carries=10, rushing_share=.35, latest_snap_share=.5)


def assess_captain_workload(row):
    features = row.get('workload_feature_evidence')
    facts = dict(features) if isinstance(features, Mapping) else {}
    # Original feature attribution takes precedence over later availability refresh.
    facts = {**dict(row), **facts}
    def number(key):
        value = facts.get(key)
        if isinstance(value, bool): return None
        try: value = float(value)
        except (TypeError, ValueError): return None
        return value if math.isfinite(value) else None
    def clock(value):
        try:
            result = pd.to_datetime(value, utc=True)
            return None if pd.isna(result) else result
        except (TypeError, ValueError): return None
    cutoff = clock(row.get('data_cutoff_at') or row.get('workload_feature_cutoff_at'))
    feature_at = clock(row.get('workload_feature_cutoff_at'))
    role_at = clock(facts.get('role_observed_at'))
    position = str(row.get('position') or '').upper()
    evidence = {key: number(key) for key in (
        'pregame_base_targets_mean_3', 'pregame_base_target_share_mean_3',
        'pregame_base_carries_mean_3', 'pregame_base_carry_share_mean_3',
        'target_share_last', 'snap_share_last', 'projected_targets', 'projected_carries',
        'pregame_expected_targets', 'pregame_expected_carries', 'pregame_target_share',
        'pregame_carry_share', 'pregame_expected_routes')}
    result = dict(policy_id=POLICY_ID, eligible=False, status='unknown',
        reason_code='captain_workload_unknown', evidence=evidence, floors=FLOORS,
        projection_proxies_used_for_qualification=False, flex_eligibility_unchanged=True,
        feature_run_id=row.get('workload_feature_run_id'),
        feature_cutoff_at=str(feature_at) if feature_at is not None else None,
        role_source=facts.get('role_source'), role_observed_at=facts.get('role_observed_at'),
        limitations=['Role qualification policy; not a calibrated Captain-success probability.',
                     'Latest target share is an observation, not a next-game forecast; routes may be unavailable.'])
    if cutoff is None or feature_at is None or feature_at > cutoff or role_at is None or role_at > cutoff or not facts.get('role_source'):
        return result
    if position == 'QB':
        valid = bool(row.get('is_starting_qb') and row.get('starting_qb_source'))
        result.update(eligible=valid,status='supported' if valid else 'unknown',
                      reason_code='sourced_starting_qb' if valid else 'captain_qb_role_unknown')
        return result
    if position not in {'WR','TE','RB'}:
        result.update(status='unsupported',reason_code='captain_offensive_workload_not_applicable')
        return result
    def at_least(key, floor):
        value = number(key)
        return value is not None and value >= floor
    measured_receiving = all(facts.get(key) is True for key in (
        'targets_mean_3_available','target_share_mean_3_available','snap_share_mean_3_available'))
    measured_rushing = all(facts.get(key) is True for key in (
        'carries_mean_3_available','carry_share_mean_3_available','snap_share_mean_3_available'))
    receiving = measured_receiving and all((
        at_least('pregame_base_targets_mean_3',FLOORS['receiving_targets']),
        at_least('pregame_base_target_share_mean_3',FLOORS['receiving_share']),
        # One quiet game cannot erase a sustained major receiving role. A
        # secondary role needs corroboration in the latest observed game.
        at_least('pregame_base_target_share_mean_3',FLOORS['established_receiving_share'])
            or at_least('target_share_last',FLOORS['latest_receiving_share']),
        at_least('snap_share_last',FLOORS['latest_snap_share'])))
    rushing = position == 'RB' and measured_rushing and all((
        at_least('pregame_base_carries_mean_3',FLOORS['rushing_carries']),
        at_least('pregame_base_carry_share_mean_3',FLOORS['rushing_share']),
        at_least('snap_share_last',FLOORS['latest_snap_share'])))
    # A genuine ingested, verified forecast can document role expansion. Ordinary
    # depth status, availability refresh and Captain-opinion text cannot do so.
    forecast_at = clock(facts.get('expected_workload_observed_at'))
    source_ids = facts.get('expected_workload_source_ids')
    verified_sources = (isinstance(source_ids,list) and bool(source_ids)
        and all(isinstance(source,str) and source.strip() for source in source_ids))
    context_id = number('pregame_context_row_id')
    forecast = (facts.get('expected_workload_status') == 'VERIFIED'
        and verified_sources
        and context_id is not None and context_id > 0
        and bool(facts.get('pregame_context_source'))
        and forecast_at is not None and forecast_at <= cutoff)
    expanded_receiving = forecast and at_least('pregame_expected_targets',5) and at_least('pregame_target_share',.15)
    expanded_rushing = forecast and position == 'RB' and at_least('pregame_expected_carries',10) and at_least('pregame_carry_share',.35)
    current_forecast = forecast and (number('pregame_expected_targets') is not None
        or position == 'RB' and number('pregame_expected_carries') is not None)
    eligible = bool(expanded_receiving or expanded_rushing) if current_forecast else bool(receiving or rushing)
    result.update(eligible=eligible, status='supported' if eligible else 'unsupported' if measured_receiving or measured_rushing else 'unknown',
        reason_code=('verified_expanded_captain_workload' if expanded_receiving or expanded_rushing else
                     'verified_current_workload_below_captain_role' if current_forecast else
                     'supported_rushing_captain_role' if rushing else 'supported_receiving_captain_role' if receiving else
                     'insufficient_supported_captain_workload' if measured_receiving or measured_rushing else 'captain_workload_unknown'),
        qualification_basis='verified_explicit_workload' if expanded_receiving or expanded_rushing else 'observed_prior_role',
        forecast_observed_at=facts.get('expected_workload_observed_at'),
        forecast_source_ids=source_ids if verified_sources else [])
    return result
