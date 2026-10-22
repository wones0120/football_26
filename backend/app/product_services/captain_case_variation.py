"""Prior, current-QB-compatible joint role and passing sensitivity profiles.

Profiles are conditional examples, not estimated frequencies. Missing rows are
never evidence of zero work. User preferences are deliberately absent here.
"""
import math

from .evaluation_record import digest

UNKNOWN = '__unallocated__'
CHANNELS = ('pass_attempts', 'rush_attempts', 'targets')


def profiles(history, games, *, team, starter_id, members, before_period):
    rows = [r for r in history if r['team'] == team and r['period']//100 == before_period//100]
    by_period = {}
    for row in rows:
        by_period.setdefault(row['period'], {})[row['player_master_id'] or row['source_player_id']] = row
    compatible = []
    missing = []
    for game in games:
        actors = by_period.get(game['period'], {})
        starter = actors.get(starter_id)
        if game['team'] != team or not starter or not (starter.get('pass_attempts') or 0) > 0:
            continue
        values = [game.get(k) for k in ('completions', 'passing_yards', 'pass_attempts', 'rush_attempts')]
        if any(v is None for v in values) or not 0 < game['completions'] <= game['pass_attempts'] or game['passing_yards'] <= 0:
            missing.append(dict(period=game['period'], reason='Missing/invalid joint completion-yard profile'))
            continue
        compatible.append({**game, 'actors': actors})
    compatible = sorted(compatible, key=lambda g:g['period'])[-8:]
    if len(compatible) < 3:
        raise ValueError('Three complete current-starter QB games required for shared role/passing variation')
    average = {key:sum(g[key] for g in compatible)/len(compatible) for key in ('pass_attempts','rush_attempts')}
    reference_completion = sum(g['completions'] for g in compatible)/sum(g['pass_attempts'] for g in compatible)
    reference_ypc = sum(g['passing_yards'] for g in compatible)/sum(g['completions'] for g in compatible)
    reference_shares = {}
    for pid, actor in members.items():
        reference_shares[pid] = {}
        for channel in CHANNELS:
            denominator = 'pass_attempts' if channel == 'targets' else channel
            observed = [(g['actors'][pid].get(channel), g[denominator]) for g in compatible
                        if pid in g['actors'] and g['actors'][pid].get(channel) is not None and g[denominator] > 0]
            reference_shares[pid][channel] = (sum(v/d for v,d in observed)/len(observed)) if observed else None
    ordered = sorted(compatible,key=lambda g:(g['passing_yards']/g['pass_attempts'],g['period']))
    # The fourth stratum explicitly examines a sourced low-backup-work game.
    backups = {pid for pid,a in members.items() if a.get('canonical_role') == 'expected_backup' and a.get('world_activity') is not False and
               sum(a['counts'].get(k) or 0 for k in ('rush_attempts','targets'))>0}
    def low_backup(g):
        observed = [g['actors'][pid] for pid in backups if pid in g['actors'] and
                    g['actors'][pid].get('rush_attempts') is not None and g['actors'][pid].get('targets') is not None]
        return (-sum(r['rush_attempts']+r['targets']==0 for r in observed),-len(observed),sum(r['rush_attempts']+r['targets'] for r in observed),g['period'])
    selected = [ordered[0],ordered[(len(ordered)-1)//2],ordered[-1],min(compatible,key=low_backup)]
    result = []
    for label, game in zip(('low_passing','middle_passing','high_passing','low_backup_work'),selected):
        offense=[row for row in game['actors'].values() if row.get('position')!='K']
        if any(row.get('pass_attempts') is None for row in offense):
            raise ValueError('Missing full-source passer observations; no residual-to-starter fallback')
        passers=[dict(player_master_id=row['player_master_id'],source_player_id=row['source_player_id'],
            position=row.get('position'),source_id=row['source_id'],attempts=row['pass_attempts'])
            for row in offense if row['pass_attempts']>0]
        if not math.isclose(sum(row['attempts'] for row in passers),game['pass_attempts'],abs_tol=1e-6):
            raise ValueError('Full-source passer shares do not reconcile with donor team attempts')
        multipliers = {}; evidence = {}; unknowns = []
        for pid, actor in members.items():
            row = game['actors'].get(pid); multipliers[pid] = {}
            for channel in CHANNELS:
                if actor['counts'].get(channel) is None: continue
                denominator = game['pass_attempts' if channel == 'targets' else channel]
                reference = reference_shares[pid][channel]
                value = row.get(channel) if row else None
                if value is None or denominator <= 0 or reference is None:
                    factor = 1.; unknowns.append(dict(player_master_id=pid,channel=channel,reason='Missing donor observation; anchor retained, no observed zero inferred'))
                elif reference > 0:
                    factor = (value/denominator)/reference
                elif value == 0 and actor.get('canonical_role') == 'expected_backup':
                    factor = 0.
                else:
                    factor = 1.; unknowns.append(dict(player_master_id=pid,channel=channel,reason='No positive role-share reference; expansion uncertainty remains'))
                multipliers[pid][channel] = factor
            if row:
                evidence[pid] = dict(source_id=row['source_id'], observed_counts={k:row.get(k) for k in CHANNELS})
        result.append(dict(stratum=label,period=game['period'],source_ids=game['source_ids'],
            passing_roles=dict(starter_id=starter_id,observed_team_attempts=game['pass_attempts'],passers=passers),
            volume_factors={k:game[k]/average[k] if average[k]>0 else 1. for k in average},
            completion_factor=(game['completions']/game['pass_attempts'])/reference_completion,
            yards_per_completion_factor=(game['passing_yards']/game['completions'])/reference_ypc,
            multipliers=multipliers,role_observations=evidence,unknowns=unknowns))
    return dict(starter_id=starter_id,compatible_periods=[g['period'] for g in compatible],
        reference_completion_rate=reference_completion,reference_yards_per_completion=reference_ypc,
        source_sha256=digest(compatible),excluded=missing,profiles=result)


def allocate_passers(total, profile, supported_ids):
    """Allocate a case's team attempts by full-source observed passer shares.

    Independent player/team forecast disagreement is not an observed backup.
    Unsupported/unlinked donor passers retain their share in an audited bucket;
    salary eligibility and user exclusions never donate it to the starter.
    """
    rows=profile.get('passers') or [];denominator=profile.get('observed_team_attempts')
    if (not isinstance(total,int) or total<0 or not rows or denominator is None or denominator<=0 or
        any(not math.isfinite(row['attempts']) or row['attempts']<=0 for row in rows) or
        len({row['source_player_id'] for row in rows})!=len(rows) or
        not any(row['player_master_id']==profile.get('starter_id') for row in rows) or
        not math.isclose(sum(row['attempts'] for row in rows),denominator,abs_tol=1e-6)):
        raise ValueError('Invalid sourced passer allocation; no residual-to-starter fallback')
    raw=[total*row['attempts']/denominator for row in rows];issued=[int(math.floor(value)) for value in raw]
    for index in sorted(range(len(rows)),key=lambda i:(-(raw[i]-issued[i]),rows[i]['source_player_id']))[:total-sum(issued)]:issued[index]+=1
    allocation={UNKNOWN:0};audit=[]
    for row,n in zip(rows,issued):
        pid=row['player_master_id'];recipient=pid if pid in supported_ids else UNKNOWN
        allocation[recipient]=allocation.get(recipient,0)+n
        audit.append(dict(**row,case_attempts=n,recipient=recipient,
            reason='source-supported modeled passer' if recipient!=UNKNOWN else 'source-observed passer outside supported model domain; work retained'))
    return allocation,audit


def allocation_plan(total, base_weights, residual, factors):
    """Expected opportunities conditional on one sourced joint role profile.

    Historical profiles already supply joint workload variation. Independent
    multinomial event noise on top has no calibrated support in these cases.
    Keep the unknown anchor share fixed; balance whole counts around the
    conditional shares instead of inventing another role-expansion draw.
    """
    if (not isinstance(total,int) or total < 0 or not math.isfinite(residual) or residual < -1e-6 or
        any(not math.isfinite(v) or v<0 for v in base_weights.values()) or
        any(not math.isfinite(factors.get(pid,1.)) or factors.get(pid,1.)<0 for pid in base_weights)):
        raise ValueError('Invalid variable-role allocation budget')
    denominator=sum(base_weights.values())+max(0.,residual)
    unknown=int(round(total*max(0.,residual)/denominator)) if denominator>0 else total
    weights={pid:v*factors.get(pid,1.) for pid,v in base_weights.items()}
    weight_sum=sum(weights.values())
    expected={pid:(total-unknown)*v/weight_sum if weight_sum>0 else 0. for pid,v in weights.items()}
    if weight_sum<=0:unknown=total
    return dict(version='profile_balanced_opportunities_v1',unknown_count=unknown,
        conditional_expected=expected,base_weights=dict(base_weights),role_factors={pid:factors.get(pid,1.) for pid in base_weights},
        additional_count_noise=False,interpretation='Sourced joint role variation plus balanced whole-count rounding; no calibrated extra opportunity tail')


def allocate(total, base_weights, residual, factors, rng):
    """Conserve budget/unknown work with deterministic largest-remainder rounding.

    Each known count is floor/ceil of its conditional profile expectation.
    Profile-supported expansion is retained, without a player-specific ceiling.
    rng remains in the interface for callers; this allocation consumes no draws.
    """
    plan=allocation_plan(total,base_weights,residual,factors)
    expected=plan['conditional_expected'];counts={pid:int(math.floor(v)) for pid,v in expected.items()}
    remaining=total-plan['unknown_count']-sum(counts.values())
    for pid in sorted(expected,key=lambda pid:(-(expected[pid]-counts[pid]),pid))[:remaining]:counts[pid]+=1
    return {**counts,UNKNOWN:plan['unknown_count']}
