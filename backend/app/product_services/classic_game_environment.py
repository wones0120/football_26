"""Read-only Classic report over saved generation evidence. No solver consumers."""
from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite

from .classic_data_readiness import validate_frozen_evidence
from .market_snapshots import utc_time

CONTRACT = "classic_game_environment_review_v1"
TIER_CONVENTION = ("Rank games in the complete salary slate by tie-aware midrank percentile: "
    "(number of lower totals + half the number of equal totals) / number of games. "
    "Highest quarter >= .75; lowest quarter <= .25; otherwise middle half. "
    "Equal totals always receive the same tier; tier sizes can differ from 25%. "
    "Any unavailable game total makes slate-relative tiers unavailable.")


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) and not isinstance(value, bool) else None
    except (ValueError, TypeError):
        return None


def total_tiers(totals):
    """Same midrank convention as the historical study, including boundary ties."""
    values = list(totals.values())
    return {game: ("highest_quarter" if pct >= .75 else "lowest_quarter" if pct <= .25 else "middle_half")
            for game, total in totals.items()
            for pct in [(sum(v < total for v in values) + .5 * sum(v == total for v in values)) / len(values)]}


def _before(value, cutoff, frozen_at, lock, max_age):
    try:
        time = utc_time(value)
        return time <= cutoff and time < lock and 0 <= (frozen_at-time).total_seconds() <= max_age*3600
    except (ValueError, TypeError, AttributeError):
        return False


def build_review(lineup, frozen, *, run_id, season, week, slate, cutoff):
    """Use only canonical IDs and a whitelist of frozen prelock fields.

    Frozen READY evidence proves original raw-artifact verification. Recheck hash,
    scope, clocks and associations; never replace absent evidence with current DB
    data, roster-embedded market numbers, realized ownership or historical notes.
    Freshness is measured at the saved decision time, not at report download time.
    """
    reason = None
    try:
        ready = validate_frozen_evidence(frozen or {})
        cut, at = utc_time(cutoff), utc_time(frozen['frozen_at'])
        if (str(frozen['optimizer_run_id']) != str(run_id) or utc_time(frozen['evidence_cutoff']) != cut
                or (ready['season'], ready['week'], ready['slate'].upper()) != (season, week, slate.upper())
                or at < cut):
            raise ValueError("Frozen evidence scope mismatch")
        manifest = frozen['canonical_evidence']['source_manifest']
        games = {str(g['game_id']): g for g in manifest['games']}
        pool = {str(p['player_id']): p for p in frozen['player_pool']}
        if not games or len(pool) != len(frozen['player_pool']):
            raise ValueError("Frozen game or player identity is ambiguous")
        first_lock = min(utc_time(g['kickoff_at']) for g in games.values())
        if at >= first_lock or cut >= first_lock:
            raise ValueError("Saved evidence was frozen after slate lock")
        limits = ready['required_sources']
        if any(number(limits[k].get('max_age_hours')) is None or limits[k]['max_age_hours'] <= 0
               for k in ('market', 'ownership')):
            raise ValueError('Saved freshness limits missing')
        if len({frozenset((g['home_team'], g['away_team'])) for g in games.values()}) != len(games):
            raise ValueError('Ambiguous slate game pairs')
        if frozen['canonical_evidence'].get('artifact_error'):
            raise ValueError('Unverified raw artifacts')
    except (ValueError, KeyError, TypeError, AttributeError):
        reason = "Verified frozen prelock evidence unavailable or incompatible."
        games, pool, manifest = {}, {}, {}

    market_rows = defaultdict(list)
    for m in manifest.get('markets', []):
        market_rows[str(m.get('game_id'))].append(m)
    usable = {}
    for gid, game in games.items():
        choices = []
        for m in market_rows[gid]:
            total, spread = number(m.get('game_total')), number(m.get('home_spread'))
            if (not all(m.get(k) for k in ('market_snapshot_id','source_snapshot_id','content_sha256','source'))
                    or total is None or not 20 <= total <= 80
                    or (spread is not None and abs(spread) > total)
                    or any(m.get(k) is not None and m[k] != game[k] for k in ('home_team','away_team'))
                    or not all(_before(m.get(k), cut, at, first_lock, limits['market']['max_age_hours'])
                               for k in ('observed_at','ingested_at'))):
                continue
            choices.append(m)
        if choices:
            usable[gid] = max(choices, key=lambda m: (utc_time(m['observed_at']), utc_time(m['ingested_at']), str(m['market_snapshot_id'])))
    complete = bool(games) and len(usable) == len(games)
    tiers = total_tiers({gid: number(m['game_total']) for gid,m in usable.items()}) if complete else {}
    pairs = {frozenset((g['home_team'],g['away_team'])): gid for gid,g in games.items()}
    rows = []
    for selected in lineup:
        pid = str(selected.get('player_id'))
        p = pool.get(pid, {})
        team, opponent = p.get('player_team'), p.get('opponent_team')
        gid = pairs.get(frozenset((team, opponent)))
        game = games.get(gid, {})
        m = usable.get(gid, {})
        matched = bool(p and gid and p.get('canonical_game_id') == gid)
        market_matched = (matched and p.get('market_context_point_in_time_safe') is True
            and str(p.get('market_snapshot_row_id')) == str(m.get('market_snapshot_id')))
        if not market_matched: m = {}
        total, home_spread = number(m.get('game_total')), number(m.get('home_spread'))
        spread = home_spread if team == game.get('home_team') else -home_spread if home_spread is not None else None
        # Conventional team bet sign: favorite is negative. Both implied totals
        # sum exactly to total; no use of legacy expected-home-margin sign.
        implied = (total-spread)/2 if total is not None and spread is not None else None
        opposing = (total+spread)/2 if total is not None and spread is not None else None
        projection = number(p.get('projection'))
        try:
            projection_run = ((frozen or {}).get('canonical_evidence', {}).get('projection_lineage') or {}).get('run') or {}
            projection_safe = (p.get('projection_run_id')
                and str(p['projection_run_id']) == str(projection_run.get('projection_run_id'))
                and p.get('projection_inputs_complete') is True
                and utc_time(p['data_cutoff_at']) <= cut and utc_time(p['projection_observed_at']) <= cut
                and utc_time(p['projection_created_at']) <= at and utc_time(p['projection_created_at']) < first_lock)
        except (KeyError, TypeError, ValueError, AttributeError):
            projection_safe = False
        ownership = number(p.get('ownership'))
        own_proof = ((frozen or {}).get('canonical_evidence', {}).get('ownership_lineage', {}).get(str(p.get('ownership_run_id'))) or {})
        own_provenance = (own_proof.get('metrics_json') or {}).get('input_provenance') or {}
        own_safe = (own_proof.get('status') == 'completed'
            and str(own_provenance.get('target_projection_run_id')) == str(p.get('projection_run_id'))
            and p.get('ownership_run_id') and ownership is not None and 0 <= ownership <= 100
            and bool(games) and _before(p.get('ownership_observed_at'), cut, at, first_lock, limits['ownership']['max_age_hours']))
        rows.append({'player_id':pid, 'player': selected.get('name') or selected.get('player_name') or pid,
            'position':p.get('position') or selected.get('position'), 'slot': selected.get('roster_position') or selected.get('position'),
            'team':team or selected.get('player_team'), 'opponent':opponent or selected.get('opponent_team'),
            'game_id':gid if matched else None, 'game_total':total, 'team_spread':spread,
            'team_implied_points':implied, 'opponent_implied_points':opposing,
            'tier':tiers.get(gid) if m else None, 'projection':projection if projection_safe else None,
            'projected_ownership':ownership if own_safe else None,
            'ownership_run_id':p.get('ownership_run_id') if own_safe else None,
            'market_source':m.get('source'), 'market_snapshot_id':m.get('market_snapshot_id'),
            'source_snapshot_id':m.get('source_snapshot_id'), 'market_observed_at':m.get('observed_at'),
            'market_ingested_at':m.get('ingested_at'),
            'availability_reason':None if m else reason or 'Missing, stale, unverified or mismatched market evidence.'})
    offense = [r for r in rows if r['position'] != 'DST']
    roster_valid = (len(rows)==9 and len({r['player_id'] for r in rows})==9 and len(offense)==8
        and Counter(r['slot'] for r in rows)==Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1})
        and all(r['position'] in {'QB','RB','WR','TE'} for r in offense))
    counts = Counter(r['tier'] or 'unavailable' for r in offense)
    totals = [r['game_total'] for r in offense if r['game_total'] is not None]
    by_position = {pos:{'slots':sum(r['position']==pos for r in offense),
        **{tier:sum(r['position']==pos and r['tier']==tier for r in offense)
           for tier in ('highest_quarter','middle_half','lowest_quarter')},
        'unavailable':sum(r['position']==pos and r['tier'] is None for r in offense)} for pos in ('QB','RB','WR','TE')}
    observations = []
    if roster_valid:
        if complete:
            observations.append(f"This lineup uses {counts['highest_quarter']} offensive players from the slate's highest-total quarter.")
        if len(totals)==8:
            observations.append(f"The average selected offensive player's game total is {sum(totals)/8:.2f}.")
        projected = [r for r in offense if r['game_id'] and r['projection'] is not None]
        if len(projected)==8 and sum(r['projection'] for r in projected)>0:
            by_game = defaultdict(float)
            for r in projected: by_game[r['game_id']] += r['projection']
            gid,points = max(by_game.items(),key=lambda item:(item[1],item[0]))
            g=games[gid]
            observations.append(f"{points/sum(by_game.values()):.1%} of offensive projected points are in {g['away_team']} at {g['home_team']}.")
    return {'contract_id':CONTRACT, 'nonbinding':True, 'selection_effect':'none', 'primary_lineup_only':True,
        'status':'AVAILABLE' if roster_valid and complete and all(r['game_total'] is not None for r in rows) else 'PARTIAL' if usable else 'UNAVAILABLE',
        'frozen_at':(frozen or {}).get('frozen_at'), 'evidence_cutoff':str(cutoff) if cutoff else None,
        'evidence_sha256':(frozen or {}).get('sha256'), 'rows':rows,
        'roster_valid':roster_valid, 'slate_games':len(games), 'verified_market_games':len(usable),
        'tier_convention':TIER_CONVENTION,
        'spread_convention':'Selected team spread: negative = favorite, positive = underdog; implied points = (total - team spread) / 2.',
        'freshness_basis':'Saved generation time and saved source age limits. Provider observation time is available; quote publication time is unknown. This is a frozen review, not refreshed entry clearance.',
        'composition':({'offensive_slots':8, **{k:counts[k] for k in ('highest_quarter','middle_half','lowest_quarter','unavailable')},
            'mean_offensive_game_total':sum(totals)/8 if len(totals)==8 else None,
            'distinct_offensive_games':len({r['game_id'] for r in offense}) if all(r['game_id'] for r in offense) else None,
            'by_position':by_position} if roster_valid else None),
        'dst':next((r for r in rows if r['position']=='DST'),None), 'observations':observations,
        'limitations':[reason] if reason else ['Information only; no advantage, disadvantage, cash probability or selection weight is inferred.']}


def review_job(job):
    if job.strategy != 'classic_single_lineup_v1' or job.status != 'completed' or not job.results:
        return None
    try:
        return build_review(job.results[0], job.params.get('classic_evidence_snapshot'), run_id=job.job_id,
            season=job.season, week=job.week, slate=job.slate, cutoff=job.data_cutoff_at)
    except (KeyError, TypeError, ValueError, AttributeError):
        # A malformed legacy report cannot block reading the saved lineup.
        return build_review(job.results[0], None, run_id=job.job_id,
            season=job.season, week=job.week, slate=job.slate, cutoff=job.data_cutoff_at)
