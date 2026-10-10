"""Conservative Classic pool scope, independent of prices and user preferences."""
from copy import deepcopy

from .showdown_player_context import CONTEXT_CONTRACT, assess_availability, is_excluded_specialist
from .slate_preparation import aware


def assess_pool_player(row, *, cutoff, evaluated_at, max_age_hours):
    """Unknown offensive opportunity blocks; existing role exclusions can quarantine.

    A backup receiver, RB or TE is still potentially material. Only the existing
    non-scoring specialist / backup-QB-without-package policies prove that a
    player cannot participate in this strategy, without needing a fabricated
    projection or an availability assumption. Recompute from source facts on
    every build; a saved quarantine is never an input to this decision.
    """
    state, reasons = assess_availability(row, cutoff=cutoff, evaluated_at=evaluated_at,
                                       max_age_hours=max_age_hours)
    if row.get('position') != 'DST' and row.get('canonical_context_contract') != CONTEXT_CONTRACT:
        state, reasons = 'UNKNOWN', ['player_status_canonical_evidence_missing']
    role_reasons = [r for r in row.get('canonical_context_reason_codes') or [] if r.startswith('player_role')]
    role_current = bool(row.get('canonical_context_contract') == CONTEXT_CONTRACT
        and row.get('role_source') and row.get('role_source_ids') and not role_reasons
        and row.get('canonical_role') not in {None, '', 'uncertain', 'unknown', 'UNKNOWN'}
        and not row.get('role_uncertain') and not row.get('pregame_role_uncertain'))
    try:
        at = aware(row['role_observed_at'])
        role_current = role_current and at <= aware(cutoff) and at <= aware(evaluated_at) and (
            aware(evaluated_at) - at).total_seconds() <= max_age_hours * 3600
    except (KeyError, TypeError, ValueError, AttributeError):
        role_current = False
    policy = None
    if is_excluded_specialist(row, cutoff=cutoff, evaluated_at=evaluated_at, max_age_hours=max_age_hours):
        policy = 'unsupported_non_scoring_specialist_role'
    elif (role_current and row.get('position') == 'QB' and row.get('canonical_role') == 'expected_backup'
          and row.get('is_starting_qb') is not True
          and row.get('expected_qb_package') is not True
          and ((row.get('workload_context') or {}).get('evidence_json') or {}).get('expected_qb_package') is not True):
        policy = 'backup_qb_without_sourced_expected_package'
    proof = {k: deepcopy(row.get(k)) for k in ('canonical_role', 'role_source', 'role_source_ids',
        'role_observed_at', 'role_source_position', 'canonical_context_reason_codes')}
    proof.update(policy=policy, reassessment='Recompute after each source refresh; never reuse a saved exclusion.')
    return dict(availability_state=state, availability_reasons=reasons,
        materiality='nonmaterial_by_existing_role_policy' if policy else 'potentially_material' if role_current else 'unknown',
        role_exclusion_policy=policy, materiality_evidence=proof if policy else None,
        quarantine=bool(state == 'UNKNOWN' and policy), role_current=role_current)
