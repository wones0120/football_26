"""Read-only historical GPP diagnostics; never train or promote a selector.

Choices are frozen from saved returned candidates before actuals are joined.
Historical DB clocks are screening evidence, not proof of immutable prelock capture.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
import re

from .contest_evidence import classify_contest_type
from .gpp_recommendation import evaluate_candidates
from .optimizer_effectiveness import (
    actual_points_by_player, candidate_signature, chronological_validation,
    extract_saved_pool, score_signature,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                    separators=(",", ":")).encode()).hexdigest()


def field_outcome(points, contest, histogram, tiers):
    """Compare with unchanged historical field; bounds do not assume tie splitting.

Payout evidence requires contiguous nonoverlapping ranks and prize-pool
reconciliation. Unknown prizes, gaps and incomplete fields remain unavailable.
"""
    size = int(contest.get("field_size") or 0)
    complete = bool(size and sum(row['entries'] for row in histogram) == size
                    and all(row['entry_points'] is not None and math.isfinite(float(row['entry_points']))
                            and row['entries'] > 0 for row in histogram))
    classification = classify_contest_type(contest.get('contest_name'), contest.get('contest_type'))
    if contest.get('contest_type_source'):
        classification['contest_type_source'] = contest['contest_type_source']
    payout = {}
    reason = None
    for tier in sorted(tiers, key=lambda t: t['min_rank']):
        lo, hi = int(tier['min_rank']), int(tier['max_rank'])
        amount = tier.get('payout')
        if (lo != len(payout) + 1 or hi < lo or hi > size or amount is None
                or not math.isfinite(float(amount)) or float(amount) < 0):
            reason = 'invalid_or_incomplete_payout_ladder'
            break
        payout.update({rank: float(amount) for rank in range(lo, hi + 1)})
    prize_pool = contest.get('prize_pool')
    if not payout:
        reason = 'missing_payout_ladder'
    elif prize_pool is None or not math.isfinite(float(prize_pool)) or float(prize_pool) <= 0:
        reason = reason or 'missing_prize_pool_reconciliation'
    elif abs(sum(payout.values()) - float(prize_pool)) > .01:
        reason = reason or 'payout_total_does_not_match_prize_pool'
    if classification['contest_type'] != 'gpp':
        reason = 'unverified_gpp_classification' if reason is None else reason + ';unverified_gpp_classification'
    paid_rank = contest.get('places_paid')
    paid_rank_valid = (contest.get('paid_places_source') == 'draftkings_entry_history'
                       and type(paid_rank) is int and 0 <= paid_rank <= size
                       and classification['contest_type'] == 'gpp')
    paid_cutoff = None
    if complete and paid_rank_valid and paid_rank:
        cumulative = 0
        for row in sorted(histogram, key=lambda row: -float(row['entry_points'])):
            cumulative += row['entries']
            if cumulative >= paid_rank:
                paid_cutoff = float(row['entry_points'])
                break
    result = dict(contest_name=contest.get('contest_name'), places_paid=paid_rank if paid_rank_valid else None,
                  paid_cutoff_points=paid_cutoff, paid_finish_evidence=paid_rank_valid and complete,
                  contest_id=str(contest['contest_id']), field_complete=complete,
                  classification=classification, payout_evidence_reason=reason,
                  paid_finish=None, net_return_bounds=None, rank_bounds=None,
                  top_one_percent=None, top_ten_percent=None,
                  evidence_sha256=digest([contest, histogram, tiers]))
    if points is None or not complete:
        result['placement_reason'] = 'missing_lineup_actuals' if points is None else 'incomplete_field'
        return result
    above = sum(row['entries'] for row in histogram if float(row['entry_points']) > points + .005)
    tied = sum(row['entries'] for row in histogram if abs(float(row['entry_points']) - points) <= .005)
    best, worst = above + 1, above + tied + 1
    result.update(rank_bounds=[best, worst], top_one_percent=worst <= max(1, math.ceil(size * .01)),
                  top_ten_percent=worst <= max(1, math.ceil(size * .1)))
    if paid_rank_valid:
        result['paid_finish'] = True if worst <= paid_rank else False if best > paid_rank else None
    if reason is None:
        amounts = [payout.get(rank, 0.) for rank in range(best, worst + 1)]
        low, high = min(amounts), max(amounts)
        result['paid_finish'] = True if low > 0 else False if high == 0 else None
        result['payout_bounds'] = [low, high]
        fee = contest.get('entry_fee')
        if fee is not None and math.isfinite(float(fee)) and float(fee) >= 0:
            result['net_return_bounds'] = [low - float(fee), high - float(fee)]
    return result


def freeze_choice(run, lineups):
    """Invoke the deployed selector before reading outcomes, retaining its validation."""
    return evaluate_candidates(lineups, run_id=str(run['optimizer_run_id']),
        season=run['season'], week=run['week'], slate=run['slate_id'],
        contest_format=run['contest_format'], projection_run_id=str(run['projection_run_id']),
        data_cutoff_at=run['data_cutoff_at'])


def evaluate_run(run, lineups, choice, observations, contests, histograms, tiers):
    fmt = run['contest_format']
    pool = extract_saved_pool(run['constraint_config_json'], fmt)
    # Returned rosters cover the actual selector's inputs, unlike the hidden search pool.
    returned = [dict(players=roster, games_represented=sorted({str(p.get('game_id') or '') for p in roster}))
                for roster in lineups]
    timing = chronological_validation(run, dict(status='slate_source_pool', candidates=returned))
    reasons = []
    if not contests and not observations:
        reasons.append('historical_results_not_imported')
    if any({'postgame', 'actual_points', 'actual_score', 'actual_rank'}.intersection(p)
           for roster in lineups for p in roster):
        reasons.append('postgame_data_in_saved_returned_candidate')
    if any(not re.search(r'\b\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M ET\b', str(p.get('game_id') or ''))
           for roster in lineups for p in roster):
        reasons.append('incomplete_saved_kickoff_evidence')
    if timing['status'] != 'predecision':
        reasons.append(timing['reason'])
    else:
        updated = run.get('updated_at')
        kickoff = datetime.fromisoformat(timing['first_saved_kickoff_at'])
        if not updated or not updated.tzinfo or updated >= kickoff:
            reasons.append('run_update_not_before_saved_kickoff')
    if not choice.get('recommended'):
        reasons.append('no_valid_returned_candidate')
    result = dict(run_id=str(run['optimizer_run_id']), optimizer_created_at=run['optimizer_created_at'].isoformat(), season=run['season'], week=run['week'],
                  slate=run['slate_id'], strategy=run['strategy'], timing=timing,
                  candidate_snapshot_sha256=digest(lineups),
                  choice_sha256=digest(choice), policy_id=choice['policy_id'],
                  returned_candidate_count=len(lineups), exceptions=choice['exceptions'],
                  excluded_reasons=reasons, eligibility='excluded' if reasons else 'exploratory',
                  promotion_eligible=False,
                  provenance_limitation='Database timestamps do not independently prove immutable prelock capture.',
                  pool_evidence={k:v for k,v in pool.items() if k != 'candidates'})
    if reasons:
        return result
    actuals = actual_points_by_player(observations, fmt)
    def score(roster):
        signature = candidate_signature(roster, fmt)
        return score_signature(signature, actuals) if signature else (None, ['invalid_canonical_roster'])
    selected = choice['recommended']
    selected_score, missing = score(returned[selected['lineup_number'] - 1])
    valid_indexes = {row['lineup_number'] - 1 for row in choice['candidates']}
    returned_scores = [score(row)[0] for i, row in enumerate(returned) if i in valid_indexes]
    pool_scores = [score(row)[0] for row in pool.get('candidates', [])]
    def coverage(scores):
        values = [value for value in scores if value is not None]
        return dict(count=len(scores), scoreable=len(values), best_observed=max(values, default=None),
                    ceiling_complete=bool(scores) and len(values) == len(scores))
    result.update(selected=selected, selected_actual_points=selected_score, missing_actual_player_ids=missing,
                  returned_coverage=coverage(returned_scores), search_pool_coverage=coverage(pool_scores),
                  first_returned_actual_points=score(returned[0])[0] if 0 in valid_indexes else None,
                  field_outcomes=[field_outcome(selected_score, c, histograms.get(str(c['contest_id']), []),
                                              tiers.get(str(c['contest_id']), [])) for c in contests])
    best = result['returned_coverage']['best_observed']
    result['selection_gap_points_lower_bound'] = (max(0., best - selected_score)
        if best is not None and selected_score is not None else None)
    result['stage_diagnostics'] = []
    for contest, outcome in zip(contests, result['field_outcomes']):
        cid = str(contest['contest_id'])
        returned_best = field_outcome(result['returned_coverage']['best_observed'], contest, histograms.get(cid, []), tiers.get(cid, []))
        pool_best = field_outcome(result['search_pool_coverage']['best_observed'], contest, histograms.get(cid, []), tiers.get(cid, []))
        chosen, finalist, discovery = outcome['paid_finish'], returned_best['paid_finish'], pool_best['paid_finish']
        diagnosis = 'unavailable_or_tied'
        if chosen is True:
            diagnosis = 'recommended_paid'
        elif chosen is False and finalist is True:
            diagnosis = 'final_selection_miss'
        elif chosen is False and discovery is True:
            diagnosis = 'candidate_shortlisting_miss'
        elif (chosen is False and discovery is False and result['search_pool_coverage']['ceiling_complete']):
            diagnosis = 'generation_miss'
        elif chosen is False:
            diagnosis = 'no_observed_paid_candidate_incomplete_pool'
        result['stage_diagnostics'].append(dict(contest_id=cid, contest_name=contest.get('contest_name'),
            diagnosis=diagnosis, selected_paid=chosen, best_returned_paid=finalist, best_search_pool_paid=discovery,
            paid_cutoff_points=outcome['paid_cutoff_points'],
            selected_top_one_percent=outcome['top_one_percent'], selected_top_ten_percent=outcome['top_ten_percent']))
    result['generation_diagnostic'] = 'Best observed saved pool score is a hindsight ceiling, not an attainable selection policy.'
    return result


def summarize(results, contest_evidence):
    groups = defaultdict(list)
    for row in results:
        if row['eligibility'] == 'exploratory':
            groups[f"{row['season']}-W{row['week']}-{row['slate']}"].append(row)
    return dict(run_count=len(results), excluded_runs=sum(r['eligibility']=='excluded' for r in results),
        exploratory_runs=sum(len(rows) for rows in groups.values()),
        slate_blocks=[dict(slate=key, runs=len(rows), scoreable_selections=sum(r['selected_actual_points'] is not None for r in rows))
                      for key, rows in sorted(groups.items())],
        verified_paid_finish_evaluations=sum(o['paid_finish'] is not None for rows in groups.values()
            for r in rows for o in r['field_outcomes']), promotion_eligible=False,
        contest_count=len(contest_evidence),
        payout_ready_contests=sum(c['payout_evidence_reason'] is None for c in contest_evidence),
        paid_finish_ready_contests=sum(c['paid_finish_evidence'] for c in contest_evidence),
        note='Related runs and contests are not independent trials. No pooled win-rate or expected-return estimate is reported.')
