"""User-invoked, pinned Classic construction comparisons through _build_lineup.

Never writes a run or portfolio, fetches a new pool, or disables scoring rules.
"""
from copy import deepcopy
from collections import Counter
from dataclasses import replace
from math import ceil, floor

from .classic_construction import classify_roster, RESEARCH_SCOPE, DEFINITIONS
from .classic_primary_game import canonical_primary_game
from .classic_strategy_contract import config_from_dict, digest, implementation_fingerprints, portfolio_audit
from .classic_portfolio_controls import explicit_appearance_limit
from .classic_small_field import describe_candidate
from .gpp_optimizer import Player, _build_lineup, tag_players

FAMILIES = (
    ('RB FLEX / three RBs', {'flex': 'RB'}),
    ('WR FLEX / four WRs', {'flex': 'WR'}),
    ('TE FLEX / two TEs', {'flex': 'TE'}),
    ('Exactly one WR/TE with QB', {'pc': 1}),
    ('Exactly two WR/TE with QB', {'pc': 2}),
    ('No offensive bring-back', {'bb': 0}),
    ('Exactly one offensive bring-back', {'bb': 1}),
    ('Exactly two offensive bring-backs', {'bb': 2}),
    ('QB + two WR/TE + one offensive bring-back', {'pc': 2, 'bb': 1}),
    ('Opposing RB bring-back', {'opposing_rb': True}),
    ('QB with same-team RB and WR/TE', {'same_team_rb': True}),
    ('QB with same-team RB without WR/TE', {'same_team_rb': True, 'pc': 0}),
    ('True unrelated one-off', {'true_oneoff': True}),
    ('Secondary opposing mini-stack', {'secondary_mini': True}),
)


def review_constructions(contract, selected_ids, *, entry=1, enforce_single_te=None):
    if not contract:
        return {'status': 'unavailable', 'code': 'frozen_inputs_missing', 'reason': 'Pinned Large-GPP effective strategy inputs unavailable; no solves searched'}
    if not isinstance(contract, dict) or contract.get('strategy_id') != 'classic_large_gpp_v1':
        return {'status': 'unavailable', 'code': 'incompatible_contract', 'reason': 'Saved contract is not a supported Classic Large-GPP contract; no solves searched'}
    effective = contract.get('effective')
    if not isinstance(effective, dict) or any(not effective.get(key) for key in ('players', 'resolved_config', 'pipeline_options')):
        return {'status': 'unavailable', 'code': 'frozen_inputs_missing', 'reason': 'Saved eligible-player frame, resolved configuration or pipeline options are missing; no solves searched'}
    if digest({k: v for k, v in contract.items() if k != 'sha256'}) != contract.get('sha256') or digest(contract['effective']) != contract.get('effective_sha256'):
        raise ValueError('Pinned strategy checksum mismatch')
    effective = contract['effective']; options = dict(effective['pipeline_options'])
    saved_single_te = bool(options.get('enforce_single_te', False))
    if enforce_single_te is not None:
        if type(enforce_single_te) is not bool:
            raise ValueError('Single TE review preference must be an explicit boolean')
        options['enforce_single_te'] = enforce_single_te
    review_single_te = bool(options.get('enforce_single_te', False))
    changed_settings = ({'enforce_single_te': {'saved': saved_single_te, 'review': review_single_te,
        'reason': 'Explicit user choice from the existing single-TE control; all other saved settings retained'}}
        if review_single_te != saved_single_te else {})
    review_contract = deepcopy(contract)
    review_contract['effective']['pipeline_options']['enforce_single_te'] = review_single_te
    review_contract['requested']['enforce_single_te'] = review_single_te
    review_contract['sources']['enforce_single_te'] = 'explicit_user_review_choice'

    if not 1 <= entry <= len(selected_ids): raise ValueError('Select an existing entry to review')
    config = config_from_dict(effective['resolved_config'])
    players = [Player(**{**row, 'tags': set(row['tags'])}) for row in effective['players']]
    tag_players(players, config.tag_thresholds)  # Same production tag stage, full normalization frame.
    index = {p.player_id: i for i, p in enumerate(players)}
    if any(len(ids) != 9 or len(set(ids)) != 9 or set(ids) - set(index) for ids in selected_ids):
        return {'status': 'unavailable', 'code': 'frozen_inputs_missing', 'reason': 'Selected canonical rosters unavailable or incompatible with pinned frame; no solves searched'}
    if any(classify_roster([players[index[pid]] for pid in ids])['status'] != 'available' for ids in selected_ids):
        return {'status': 'unavailable', 'code': 'incompatible_contract', 'reason': 'Saved rosters have invalid positional composition or missing game context; no solves searched'}
    template = config.stack_templates[(entry - 1) % len(config.stack_templates)] if config.stack_templates else (config.stack_rules.min_pass_catchers, config.stack_rules.min_bring_backs)
    rules = replace(config.stack_rules, min_pass_catchers=int(template[0]), min_bring_backs=int(template[1]))
    others = [ids for i, ids in enumerate(selected_ids) if i != entry - 1]
    counts = Counter(pid for ids in others for pid in ids)
    maximums = config.portfolio_targets.player_exposure_caps
    minimums = config.portfolio_targets.player_exposure_mins
    elevated = set(options.get('elevated_player_ids') or [])
    n = options['num_lineups']
    remaining = {}
    for p in players:
        global_limit = max(1, ceil(n * options['max_exposure']))
        personal = (explicit_appearance_limit(n, maximums.get(p.player_id, 1))
            if p.player_id in elevated and options.get('elevated_player_max_exposure') is not None
            else floor(n * maximums.get(p.player_id, 1)))
        remaining[p.player_id] = min(personal, max(global_limit, ceil(n * minimums.get(p.player_id, 0)))) - counts[p.player_id]
    required = {pid for pid, rate in minimums.items() if ceil(n * rate) > counts[pid]}
    primary = Counter(canonical_primary_game(next(players[index[pid]] for pid in ids if players[index[pid]].position == 'QB').team,
        next(players[index[pid]] for pid in ids if players[index[pid]].position == 'QB').opponent) for ids in others)
    cap = options.get('max_lineups_per_primary_game')
    blocked = {game for game, count in primary.items() if cap is not None and count >= cap}
    groups = [(set(ids), limit) for ids, limit in options.get('maximum_player_groups') or []]
    if elevated and options.get('max_elevated_players_per_lineup') is not None:
        groups.append((elevated, options['max_elevated_players_per_lineup']))
    individual_remaining = {pid: 0 if budget + counts[pid] <= 0 else 1 for pid, budget in remaining.items()}
    individual_required = {pid for pid, rate in minimums.items() if rate == 1}

    def describe(ids, audit=None):
        roster = [players[index[pid]] for pid in ids]
        row = describe_candidate(roster, all_players=players, config=config, pool_by_id={},
            ownership_available=options['ownership_available'], game_totals=[])
        return {**row, 'construction': classify_roster(roster), 'solver': audit,
            'component_sum_matches_solver': (abs(row['objective_score'] - audit['objective_score']) < 1e-6 if audit and ids else None)}

    def solve(change, replacement):
        if replacement and review_single_te and any(sum(players[index[pid]].position == 'TE' for pid in ids) > 1 for ids in others):
            return {'status': 'infeasible', 'reason': 'A retained entry has two TEs and violates the explicitly reviewed single-TE preference; one replacement cannot repair other entries',
                'solver': {'solver_status': 'Not searched', 'binding_exclusion': 'enforce_single_te_in_retained_entry'}}
        if replacement and any(ceil(n * rate) - counts[pid] > 1 for pid, rate in minimums.items()):
            return {'status': 'infeasible', 'reason': 'One replacement cannot satisfy the remaining explicit minimum appearances'}
        if replacement and len(selected_ids) != n:
            return {'status': 'not_searched', 'reason': 'Saved portfolio is underfilled; full-portfolio replacement cannot be certified'}
        audit = {}
        idxs = _build_lineup(players, config,
            remaining if replacement else individual_remaining,
            [set(index[pid] for pid in ids) for ids in others] if replacement else [],
            stack_rules=rules, construction=change,
            exact_pass_catchers=change.get('pc'), exact_bring_backs=change.get('bb'),
            enforce_single_te=bool(options.get('enforce_single_te', False)),
            avoid_dst_opponents=bool(options.get('avoid_dst_opponents', False)),
            required_player_ids=required if replacement else individual_required,
            maximum_player_groups=groups, excluded_primary_games=blocked if replacement else set(),
            solver_backend=options.get('solver_backend', 'bundled'), solve_audit=audit)
        if idxs is None:
            return {'status': 'infeasible' if audit.get('solver_status') == 'Infeasible' else 'unavailable',
                'solver': audit, 'reason': 'Combined active constraints and requested construction; minimal binding constraint set not proven'}
        ids = [players[i].player_id for i in idxs]
        result = {'status': 'feasible', **describe(ids, audit)}
        if replacement:
            rosters = [[players[index[pid]] for pid in roster] for roster in selected_ids]
            rosters[entry - 1] = [players[index[pid]] for pid in ids]
            validation = portfolio_audit(review_contract, rosters)['validation']
            result['portfolio_validation'] = validation
            if validation['status'] != 'verified':
                result.update(status='infeasible', reason='Full replacement failed independent portfolio validation')
        return result

    baseline = describe(selected_ids[entry - 1])
    comparisons = []
    for label, change in FAMILIES:
        exclusion = None
        if change.get('flex') == 'TE' and options.get('enforce_single_te'):
            exclusion = ('excluded_by_user_preference', 'Enforce single TE explicitly excludes TE FLEX; turn off the existing UI control and explicitly review again to permit it on the pinned inputs')
        elif 'pc' in change and change['pc'] < config.stack_rules.min_pass_catchers:
            exclusion = ('excluded_by_strategy_eligibility', 'Large-GPP minimum WR/TE stack; same-team RB does not replace a pass catcher')
        elif ('pc' in change and change['pc'] < rules.min_pass_catchers) or ('bb' in change and change['bb'] < rules.min_bring_backs):
            exclusion = ('excluded_by_generation_template', f'Selected step uses minimum template {tuple(template)}; requested exact count conflicts')
        result = {'status': exclusion[0], 'reason': exclusion[1]} if exclusion else None
        individual = result or solve(change, False)
        replacement = result or solve(change, True)
        for alternative in (individual, replacement):
            if alternative['status'] == 'feasible':
                roster_ids = set(alternative['player_ids'])
                alternative['selection_treatment'] = ('matches_reviewed_saved_entry' if roster_ids == set(selected_ids[entry - 1]) else
                    'matches_another_saved_entry' if any(roster_ids == set(ids) for ids in selected_ids) else
                    'feasible_but_not_selected_in_saved_portfolio')
                alternative['deltas_vs_saved_entry'] = {key: alternative[key] - baseline[key] for key in ('mean', 'p90', 'objective_score')}
        comparisons.append({'family': label, 'changed_construction': change,
            'individual': individual, 'replacement': replacement})
    return {'status': 'completed', 'entry': entry, 'pinned_contract_sha256': contract['sha256'],
        'pinned_effective_sha256': contract['effective_sha256'], 'projection_run_id': contract.get('metadata', {}).get('projection_run_id'),
        'implementation_matches_saved': contract.get('implementation') == implementation_fingerprints(options.get('solver_backend', 'bundled')),
        'implementation': implementation_fingerprints(options.get('solver_backend', 'bundled')),
        'scoring_frame': 'Frozen ordered eligible players, saved resolved weights and normalization, current shared production builder; source fingerprints retained. Implementation differences are not historical replay parity.',
        'changed_settings': changed_settings, 'saved_enforce_single_te': saved_single_te, 'review_enforce_single_te': review_single_te,
        'active_template_minimums': list(template), 'active_constraints': {**options, 'maximum_player_groups': options.get('maximum_player_groups')},
        'replacement_budgets': {'remaining_player_appearances': remaining, 'required_player_ids': sorted(required), 'blocked_primary_games': sorted(blocked)},
        'baseline': baseline, 'comparisons': comparisons,
        'ceiling_label': 'Summed marginal P90 (NOT a lineup percentile)', 'research_scope': RESEARCH_SCOPE, 'definitions': DEFINITIONS,
        'interpretation': 'Each row restricts only the stated construction. All scoring terms remain enabled. Individual feasibility does not certify a replacement; replacement solves retain every other entry, exposure budgets, overlap, primary-game cap, locks/minimums and risk groups. No alternatives are saved or selected as a new portfolio. Finite family searches are not exhaustive discovery coverage.'}
