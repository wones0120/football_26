"""Prior observed workload ratios, not forecasts or inferred missing zeros."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID

from research.game_progression_pilot_20261020.player_opportunity_accounting.allocation import CHANNELS, number, clock

VERSION = 'prior_full_team_workload_reference_v1'


def build_reference(rows, actors, official, *, periods, before_period, cutoff):
    if not periods or len(set(periods)) != len(periods) or any(p >= before_period or p//100 != before_period//100 for p in periods):
        raise ValueError('Distinct same-season prior periods required')
    by_native = {}; by_pid = {}; groups = defaultdict(list); seen = set()
    for actor in actors:
        pid=str(UUID(actor['player_master_id']));native=actor['source_player_id']
        if pid in by_pid or not native or native in by_native:
            raise ValueError('Unique canonical/native current roster required')
        by_pid[pid]=actor;by_native[native]=actor
    teams={a['team'] for a in actors}
    for row in rows:
        if row['period'] not in periods or row['team'] not in teams:
            raise ValueError('Source rows outside declared prior window/team')
        if not clock(row['received_at']) <= clock(cutoff):
            raise ValueError('Source received after decision cutoff')
        parts=row['game_id'].split('_')
        if len(parts)!=4 or parts[:2]!=[str(row['period']//100),f'{row["period"]%100:02d}'] or row['team'] not in parts[2:]:
            raise ValueError('Native source game/period/team differs')
        key=(row['period'],row['source_player_id'])
        if not row['source_player_id'] or key in seen:
            raise ValueError('Duplicate/missing native player-period')
        seen.add(key)
        if set(row['counts'])!=set(CHANNELS):raise ValueError('Exact count channels required')
        for value in row['counts'].values():
            n=number(value)
            if n is not None and n!=n.to_integral_value():raise ValueError('Original counts must be integral')
        groups[row['period'],row['team']].append(row)
    books={}
    for book in official:
        key=(book['period'],book['team'])
        if key in books or key[0] not in periods or key[1] not in teams:
            raise ValueError('Duplicate/out-of-scope official denominator')
        if not book['visual_review'] or book['stat_scope']!='FULL_GAME_INCLUDING_ANY_OVERTIME':
            raise ValueError('Reviewed, scope-compatible full-game denominator required')
        if clock(book['pdf_observed_at'])>clock(cutoff):raise ValueError('Official evidence after cutoff')
        counts=book['counts']
        for value in [*counts.values(),book['sacks'],book['physical_plays'],*book['receiving_target_rows']]:
            n=number(value)
            if n is None or n!=n.to_integral_value():raise ValueError('Known official integer count required')
        if (set(counts)!=set(CHANNELS) or counts['targets']>counts['pass_attempts']
                or sum(book['receiving_target_rows'])!=counts['targets']
                or counts['pass_attempts']+counts['rush_attempts']+book['sacks']!=book['physical_plays']):
            raise ValueError('Official football count accounting conflict')
        parts=book['game_id'].split('_')
        if len(parts)!=4 or parts[:2]!=[str(book['period']//100),f'{book["period"]%100:02d}']:
            raise ValueError('Official game/period differs')
        if book['team'] not in book['game_id'].split('_')[2:]:raise ValueError('Official game/team differs')
        books[key]=book
    reconciliation=[];lookup={};queue=[]
    for team in sorted(teams):
        for period in sorted(periods):
            group=groups[period,team];book=books.get((period,team));channels={}
            for channel in CHANNELS:
                lower=sum(r['counts'][channel] or 0 for r in group)
                missing=sum(r['counts'][channel] is None for r in group)
                denominator=book['counts'][channel] if book else None
                compatible=bool(book and group and not missing and lower==denominator
                    and {r['game_id'] for r in group}=={book['game_id']})
                current=sum(r['counts'][channel] or 0 for r in group
                    if r['source_player_id'] in by_native and by_native[r['source_player_id']]['team']==team)
                channels[channel]=dict(official_denominator=denominator,source_known_lower_bound=lower,
                    source_missing_component_rows=missing,source_actor_rows=len(group),
                    current_roster_known_count=current,other_native_actor_known_count=lower-current,
                    unaccounted_official_count=denominator-lower if denominator is not None else None,
                    status='RECONCILED_FULL_SOURCE_AND_OFFICIAL' if compatible else 'UNSUPPORTED_SOURCE_RECONCILIATION',
                    official_denominator_supported=book is not None)
                lookup[team,period,channel]=(compatible,denominator)
            reconciliation.append(dict(team=team,period=period,channels=channels))
            for row in group:
                actor=by_native.get(row['source_player_id'])
                if actor is None:queue.append(dict(team=team,period=period,source_player_id=row['source_player_id'],
                    reason='Native actor outside retained current canonical map; keep in full-team denominator'))
    players=[]
    for pid,actor in sorted(by_pid.items()):
        team=actor['team'];history={r['period']:r for r in rows
            if r['source_player_id']==actor['source_player_id'] and r['team']==team}
        channels={}
        for channel in CHANNELS:
            values=[history[p]['counts'][channel] if p in history else None for p in sorted(periods)]
            eligible=all(v is not None for v in values) and all(lookup[team,p,channel][0] for p in periods)
            denominator=sum(lookup[team,p,channel][1] for p in periods) if all(lookup[team,p,channel][1] is not None for p in periods) else None
            numerator=sum(values) if all(v is not None for v in values) else None
            channels[channel]=dict(observed_counts=values,missing_row_periods=[p for p in periods if p not in history],
                observed_window_sum=numerator,official_window_denominator=denominator,
                observed_mean=numerator/len(periods) if eligible else None,
                observed_share=numerator/denominator if eligible and denominator else None,
                status='SUPPORTED_OBSERVED_REFERENCE' if eligible else 'UNKNOWN_INCOMPLETE_REFERENCE',
                share_reason='zero_denominator' if eligible and denominator==0 else None)
        players.append(dict(player_master_id=pid,source_player_id=actor['source_player_id'],team=team,
            channels=channels,meaning='Observed same-team common-window reference; not conditional-active or replacement forecast'))
    return dict(version=VERSION,before_period=before_period,periods=sorted(periods),cutoff=cutoff,
        evidence_use='RETROSPECTIVE_PRIOR_PERIOD_REFERENCE_NOT_ORIGINAL_VINTAGE_REPLAY',
        source_rows=deepcopy(rows),team_reconciliation=reconciliation,players=players,
        identity_review_requests=queue,forecast=False,activation=False,allocation_consumer_connected=False,
        missingness='Absent actor rows and components remain unknown; no zero fill, renormalization or vacancy transfer')
