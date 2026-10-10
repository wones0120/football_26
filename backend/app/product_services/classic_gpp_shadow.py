"""Offline-only Classic recommendation challenger. Never imported by live selection.

Fixed before outcome evaluation: retain >=98% of the highest mean, then maximize
summed marginal P90. This is not a calibrated paid-finish probability or joint P90.
"""
from .gpp_recommendation import evaluate_candidates
from .gpp_historical_audit import digest

POLICY = {'policy_id':'classic_gpp_mean_guarded_upside_shadow_v1',
          'minimum_mean_fraction':.98,'primary_metric':'marginal_upside_sum',
          'tie_breakers':['projected_points_desc','candidate_id_asc'],
          'scope':'same_valid_returned_candidates','deployment':'offline_only'}


def freeze_shadow(lineups, **scope):
    baseline=evaluate_candidates(lineups,**scope)
    candidates=baseline['candidates']
    result=dict(policy=POLICY.copy(),policy_sha256=digest(POLICY),baseline=baseline['recommended'],
                challenger=None,status='unavailable',candidates=candidates,
                candidate_input_sha256=digest(lineups),scope=scope,
                reason='No complete, comparable candidate set')
    if not candidates:
        return result
    # Do not allow missing upside to silently change the challenger comparison set.
    if any(c['marginal_upside_sum'] is None for c in candidates):
        result['reason']='Missing or inconsistent upside in valid returned candidates'
        return result
    top=baseline['recommended']['projected_points']
    if top <= 0:
        result['reason']='Nonpositive best projected points'
        return result
    eligible=[c for c in candidates if c['projected_points'] >= POLICY['minimum_mean_fraction']*top]
    eligible.sort(key=lambda c:(-c['marginal_upside_sum'],-c['projected_points'],c['candidate_id']))
    result.update(status='shadow_only',challenger=eligible[0],eligible_count=len(eligible),
                  mean_floor=POLICY['minimum_mean_fraction']*top,
                  changed=eligible[0]['candidate_id']!=baseline['recommended']['candidate_id'],
                  reason='Highest summed player P90 within the fixed 98% projected-points band')
    return result
