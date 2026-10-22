"""Experimental prior-only efficiency; physical yards and selection weights stay separate."""
from copy import deepcopy
from pathlib import Path
import hashlib
import math

import pandas as pd

from .evaluation_record import digest

VERSION = 'role_efficiency_yards_v1'
WEIGHTS = {'passing_yards': .04, 'rushing_yards': .10, 'receiving_yards': .10}
CHANNELS = {'passing_yards': 'pass_attempts', 'rushing_yards': 'rush_attempts', 'receiving_yards': 'targets'}
PRIOR_ATTEMPTS = {'passing_yards': 80., 'rushing_yards': 30., 'receiving_yards': 20.}
ROLE_COUNT = {'QB': ('pass_attempts', 20.), 'RB': ('rush_attempts', 10.),
              'WR': ('targets', 5.), 'TE': ('targets', 5.)}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def role(rows, position):
    channel, threshold = ROLE_COUNT[position]
    recent = rows.tail(3)
    if recent.empty or recent[channel].isna().any():
        return 'unknown'
    return 'higher_usage' if recent[channel].mean() >= threshold else 'rotational_usage'


def history_frame(weekly, *, before_period, cutoff):
    """Validate identity/time, then label each observed role from earlier games only."""
    frame = weekly.copy()
    frame = frame.loc[frame.period.lt(before_period)].copy()
    clocks = pd.to_datetime(frame.imported_at, utc=True, errors='coerce')
    if clocks.isna().any() or (clocks > pd.Timestamp(cutoff)).any():
        raise ValueError('Efficiency evidence has missing/future import clocks')
    frame = frame.loc[frame.player_master_id.notna() & frame.position.isin(ROLE_COUNT)].copy()
    if frame.duplicated(['player_master_id', 'period']).any():
        raise ValueError('Duplicate canonical efficiency player-game evidence')
    if frame.empty:
        raise ValueError('No canonical prior efficiency evidence')
    if any((frame[channel].dropna().map(number).isna() | frame[channel].dropna().lt(0)).any() for channel in CHANNELS.values()):
        raise ValueError('Invalid historical efficiency opportunity counts')
    frame['season'] = frame.period.astype(int) // 100
    frame = frame.sort_values(['period', 'player_master_id']).reset_index(drop=True)
    frame['prior_role'] = 'unknown'
    for _, rows in frame.groupby(['player_master_id', 'team', 'position', 'season'], sort=True):
        for offset, index in enumerate(rows.index):
            frame.at[index, 'prior_role'] = role(rows.iloc[:offset], rows.iloc[offset].position)
    return frame


class Efficiency:
    def __init__(self, history, before_period):
        self.history = history.loc[history.period.lt(before_period)]
        self.before_period = before_period
        self.references = {}
        self.player_windows = {}
        self.position_rates = {}

    def estimate(self, actor, yard):
        position = actor['position']
        if position not in ROLE_COUNT or (yard == 'passing_yards' and position != 'QB'):
            return None
        count = CHANNELS[yard]
        prior = self.history
        player_key=(actor['player_master_id'],actor['team'],position)
        if player_key not in self.player_windows:
            same=prior.loc[prior.player_master_id.eq(player_key[0]) & prior.team.eq(player_key[1])
                           & prior.position.eq(position) & prior.season.eq(self.before_period // 100)].tail(8)
            self.player_windows[player_key]=(same,role(same,position))
        same,current_role=self.player_windows[player_key]
        reference_key=(position,current_role,yard)
        if reference_key not in self.references:
            population=prior.loc[prior.position.eq(position)]
            valid=population[count].notna() & population[yard].notna() & population[count].gt(0)
            population=population.loc[valid]
            cohort=population.loc[population.prior_role.eq(current_role)] if current_role!='unknown' else population.iloc[:0]
            fallback=len(cohort)<10 or cohort[count].sum()<40
            reference=population if fallback else cohort
            self.references[reference_key]=None if len(reference)<10 or reference[count].sum()<40 else dict(
                rate=float(reference[yard].sum()/reference[count].sum()),fallback=fallback,rows=len(reference),
                attempts=float(reference[count].sum()),
                sha256=digest(reference[['source_id',count,yard,'prior_role']].to_dict('records')))
        reference=self.references[reference_key]
        if reference is None:
            return None
        baseline=reference['rate']
        paired = same.loc[same[count].map(number).notna() & same[yard].map(number).notna() & same[count].gt(0)]
        attempts = float(paired[count].sum())
        yards = float(paired[yard].sum())
        prior_size = PRIOR_ATTEMPTS[yard]
        return dict(value=(yards + prior_size * baseline) / (attempts + prior_size),
                    role=current_role, role_basis='last3_observed_same_team_position_season_games',
                    role_threshold=dict(channel=ROLE_COUNT[position][0], count=ROLE_COUNT[position][1]),
                    reference='position_only_sparse_role' if reference['fallback'] else 'prior_position_and_prior_usage_role',
                    reference_rate=baseline, reference_rows=reference['rows'],
                    reference_attempts=reference['attempts'], player_rows=len(paired),
                    player_attempts=attempts, player_yards=yards, prior_attempts=prior_size,
                    player_source_ids=paired.source_id.astype(int).tolist(),
                    reference_sha256=reference['sha256'],
                    missing_player_pairs=int((same[count].isna() | same[yard].isna()).sum()),
                    zero_opportunity_rows=int(same[count].eq(0).sum()))

    def position_rate(self, position, yard):
        # Explicit residual population estimate, never an invented player forecast.
        key=(position,yard)
        if key not in self.position_rates:
            actor=dict(player_master_id='__unallocated__', team='__unallocated__', position=position)
            evidence=self.estimate(actor,yard)
            self.position_rates[key]=evidence['value'] if evidence else None
        return self.position_rates[key]


def add_yards(receipt, weekly, *, before_period, cutoff):
    """New immutable receipt; original learned counts/projections are never modified."""
    if not receipt.get('learned_opportunities'):
        raise ValueError('Yard comparison requires published learned opportunities')
    if receipt.get('yardage_model'):
        raise ValueError('Yards already attached; reprepare from original learned counts')
    history = history_frame(weekly, before_period=before_period, cutoff=cutoff)
    model = Efficiency(history, before_period)
    result = deepcopy(receipt)
    original_sha = receipt['sha256']
    for actor in result['players']:
        actor['count_utility'] = actor.get('utility')
        actor['efficiency'] = {}; actor['projected_yards'] = dict.fromkeys(CHANNELS)
        actor['utility'] = None
        if actor['position'] not in ROLE_COUNT:
            continue
        for yard, channel in CHANNELS.items():
            count = number(actor['counts'].get(channel))
            if yard == 'passing_yards' and actor['position'] != 'QB':
                actor['projected_yards'][yard] = 0.
            elif yard == 'receiving_yards' and actor['position'] == 'QB':
                # QB targets are outside this count head; not assumed observed zero.
                continue
            elif count is not None and count >= 0:
                evidence = model.estimate(actor, yard)
                actor['efficiency'][yard] = evidence
                actor['projected_yards'][yard] = count * evidence['value'] if evidence else (0. if count == 0 else None)
        actor['raw_projected_yards'] = deepcopy(actor['projected_yards'])
    accounting = {}
    for team, budget in result['teams'].items():
        actors = [a for a in result['players'] if a['team'] == team]
        qbs = [a for a in actors if a['position'] == 'QB' and a['projected_yards']['passing_yards'] is not None]
        receivers = [a for a in actors if a['position'] in {'RB', 'WR', 'TE'} and a['projected_yards']['receiving_yards'] is not None]
        pass_budget = number((budget or {}).get('pass_attempts'))
        target_budget = number((budget or {}).get('targets'))
        if pass_budget is None or target_budget is None or target_budget > pass_budget:
            raise ValueError('Yard accounting requires supported team pass/target budgets')
        pass_residual = pass_budget - sum(float(a['counts']['pass_attempts']) for a in qbs)
        target_residual = target_budget - sum(float(a['counts']['targets']) for a in receivers)
        if min(pass_residual, target_residual) < -1e-6:
            raise ValueError('Known player counts exceed team budget')
        pass_residual=max(0.,pass_residual);target_residual=max(0.,target_residual)
        pass_rate = model.position_rate('QB', 'passing_yards')
        # Unattributed targets have unknown role mix; use all receiving positions.
        reference=history.loc[history.targets.gt(0) & history.receiving_yards.notna()]
        target_rate=float(reference.receiving_yards.sum()/reference.targets.sum()) if len(reference)>=10 else None
        total = (sum(a['projected_yards']['passing_yards'] for a in qbs) + pass_residual*pass_rate) if pass_rate is not None else None
        raw = sum(a['projected_yards']['receiving_yards'] for a in receivers)
        denominator = raw + target_residual*target_rate if target_rate is not None else None
        factor=total/denominator if total is not None and total>=0 and denominator is not None and denominator>0 else None
        for actor in receivers:
            actor['projected_yards']['receiving_yards'] = actor['raw_projected_yards']['receiving_yards']*factor if factor is not None else None
            actor['receiving_team_reconciliation_factor'] = factor
        accounting[team]=dict(passing_yards=total, known_qb_passing_yards=sum(a['projected_yards']['passing_yards'] for a in qbs),
            unallocated_pass_attempts=pass_residual, unallocated_passing_yards=pass_residual*pass_rate if pass_rate is not None else None,
            raw_receiving_yards=raw, unallocated_targets=target_residual,
            unallocated_receiving_yards=target_residual*target_rate*factor if factor is not None else None,
            receiving_yards=sum(a['projected_yards']['receiving_yards'] for a in receivers) if factor is not None else None,
            receiving_factor=factor, residual_rate=target_rate,
            interpretation='Shared passing/receiving physical yards, including explicit unallocated actors; not independent yards.',
            sensitivity_warning=bool(factor is None or factor<2/3 or factor>1.5))
    for actor in result['players']:
        if actor['position'] not in ROLE_COUNT:
            continue
        required=('passing_yards','rushing_yards') if actor['position']=='QB' else ('rushing_yards','receiving_yards')
        if all(actor['projected_yards'][key] is not None for key in required):
            actor['utility']=sum(actor['projected_yards'][key]*WEIGHTS[key] for key in required)
        else:
            actor['reasons'].append('Missing supported efficiency, learned count or shared-yard accounting; no points fallback')
    result['yardage_model']=dict(version=VERSION,code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        policy_sha256=digest(dict(version=VERSION,weights=WEIGHTS,prior_attempts=PRIOR_ATTEMPTS,role_counts=ROLE_COUNT)),
        training_min_period=int(history.period.min()),selection_weights=WEIGHTS,original_count_receipt_sha256=original_sha,
        method='last8_same_team_position_season_pooled_yards_shrunk_to_prior_role_cohort',
        prior_attempts=PRIOR_ATTEMPTS,history_sha256=digest(history.to_dict('records')),
        source_ids=history.source_id.astype(int).tolist(),training_max_period=int(history.period.max()),
        accounting=accounting, status='experimental_unvalidated_tournament_value',
        limitations=['Conditional on learned count/active role forecasts; no opponent or air/depth adjustment.',
                    'Yards per target already includes incompletions; catch rate is not applied twice.',
                    'QB receiving opportunities unsupported; retained in team unallocated targets.',
                    'Rushing combines designed runs, scrambles and kneels; receiving depth/YAC are not separated.',
                    'Partial DK yard scoring weights are policy, not fitted weights; no receptions/TD/bonus scoring.',
                    'Shared QB/receiver yards may score both positions; team physical totals are not duplicated.',
                    'Revised source history is not proof of original pregame availability.'])
    result['yardage_model']['validation']=validate_efficiency(history,before_period=before_period)
    result['objective']='highest_declared_weighted_projected_yards'
    result['normalization_policy']='no_position_count_normalization; explicit_yardage_weights'
    result['sha256']=digest({k:v for k,v in result.items() if k!='sha256'})
    return result


def validate_efficiency(history, *, before_period):
    """Six-period chronological diagnostic using actual counts, not end-to-end proof."""
    periods=sorted(p for p in history.period.unique() if p<before_period)[-6:]
    errors={key:[] for key in CHANNELS}
    for period in periods:
        model=Efficiency(history,int(period))
        for actor in history.loc[history.period.eq(period)].to_dict('records'):
            for yard,channel in CHANNELS.items():
                if yard=='passing_yards' and actor['position']!='QB':continue
                if yard=='receiving_yards' and actor['position']=='QB':continue
                count=number(actor[channel]);actual=number(actor[yard])
                if count is None or count<=0 or actual is None:continue
                estimate=model.estimate(actor,yard);baseline=model.position_rate(actor['position'],yard)
                if estimate is not None and baseline is not None:
                    errors[yard].append((count*estimate['value']-actual,count*baseline-actual))
    summary={}
    for yard,rows in errors.items():
        summary[yard]=dict(rows=len(rows),mae=sum(abs(a) for a,b in rows)/len(rows) if rows else None,
            baseline_mae=sum(abs(b) for a,b in rows)/len(rows) if rows else None,
            bias=sum(a for a,b in rows)/len(rows) if rows else None)
    return dict(status='retrospective_conditional_efficiency_diagnostic',periods=[int(p) for p in periods],summary=summary,
        policy_searches=0,limitations=[
            'Observed attempts/targets evaluate efficiency only, not end-to-end learned count or reconciled-yard forecasts.',
            'Revised source rows do not prove original pregame availability; outcomes were previously inspected.',
            'Mixed diagnostic results, not fresh held-out calibration or proven lineup/tournament improvement.'])
