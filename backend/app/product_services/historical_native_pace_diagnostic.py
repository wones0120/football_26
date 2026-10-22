"""Minimal historical native-clock diagnostic; not reviewed/serving features."""
from collections import defaultdict, Counter
from .evaluation_record import digest
from .participation_source_components import _int
from .personnel_package_continuity import physical_membership, PHYSICAL_VERSION
from .game_clock_pace_catalog import VERSION as PACE_VERSION, native_order_proof
from .shared_game_covariance import VERSION as PAIR_VERSION
from .joint_pace_play_budgets import build_joint_pace_play_budgets
from .market_snapshots import canonical_team
from .defense_context_evidence import _number

VERSION = 'historical_native_pace_diagnostic_v1'
COLUMNS = ('game_id','play_id','season','week','season_type','order_sequence','fixed_drive','qtr','game_seconds_remaining')


def _key(row, season, boundary):
    year, week, play = (_int(row.get(k)) for k in ('season','week','play_id'))
    if year != season or week is None or not 1 <= week <= 18 or play is None:
        raise ValueError('Native source period/play required')
    gid = row['game_id']; parts = gid.split('_')
    if len(parts) != 4 or parts[:2] != [str(season),f'{week:02d}']:
        raise ValueError('Native game/period differs')
    return (gid, str(play)) if season*100+week < boundary else None


def _counter():
    return dict(eligible_events=0, known_outcome_events=0, unknown_outcome_events=0,
        unknown_eligibility_events=0, observed_outcome_sum=0.)


def build_historical_pace_diagnostic(projection, physical, schedule, *, season):
    """One fixed W1–3 / W4–17 comparison; no thresholds or windows searched."""
    boundary = season*100+18
    if physical.get('version') != PHYSICAL_VERSION or physical.get('season') != season or physical.get('pregame_serving_eligible') is not False:
        raise ValueError('Approved same-season historical physical cache required')
    if len(projection)>100000 or len(physical['rows'])>100000:
        raise ValueError('Bounded source rows required')
    expected = {}; teams = {}
    for game in schedule:
        if game['season'] != season or game['game_type'] != 'REG' or season*100+game['week'] >= boundary:
            continue
        gid=game['game_id']; home=canonical_team(game['home_team']);away=canonical_team(game['away_team']);parts=gid.split('_')
        if gid in expected or parts[:2] != [str(season),f"{game['week']:02d}"] or (canonical_team(parts[3]),canonical_team(parts[2])) != (home,away):
            raise ValueError('Unique native scheduled orientation required')
        expected[gid]={**game,'home_team':home,'away_team':away};teams[gid]={home,away}
    raw_index={};projected={}
    for rows,index in ((physical['rows'],raw_index),(projection,projected)):
        for row in rows:
            if row.get('season_type') != 'REG':continue
            key=_key(row,season,boundary)
            if key is None:continue
            if key in index:raise ValueError('Duplicate native source key')
            if key[0] not in expected:raise ValueError('Source game outside native schedule')
            index[key]=row
    if set(raw_index)!=set(projected):
        raise ValueError('Entire REG native key universe including controls must match physical cache')
    proof=native_order_proof(list(projected.values()),before_period=boundary)
    unknown_order={p['game_id'] for p in proof['game_proofs'] if any(p[k] for k in ('missing_play_ids','missing_order_sequences','duplicate_play_ids','duplicate_order_sequences'))}
    groups=defaultdict(list);pace={};owned=Counter();known_snaps=Counter();unknown_snaps=Counter();rejections=Counter()
    for gid in expected:
        for team in teams[gid]:pace[gid,team]=_counter()
    for key,row in projected.items():
        gid,play=key;raw=raw_index[key];team=canonical_team(raw['posteam']) if raw.get('posteam') else None
        if team is not None and team not in teams[gid]:raise ValueError('Native offense outside game')
        snap=physical_membership(raw)
        if team is not None:owned[gid,team]+=1
        if snap is True and team is not None:known_snaps[gid,team]+=1
        elif snap is not False:
            for side in teams[gid] if team is None else {team}:unknown_snaps[gid,side]+=1
        groups[gid].append(dict(key=key,order=_number(row.get('order_sequence')),team=team,snap=snap,
            drive=_number(row.get('fixed_drive')),quarter=_number(row.get('qtr')),clock=_number(row.get('game_seconds_remaining'))))
    for gid,rows in groups.items():
        rows.sort(key=lambda r:(r['order'] if r['order'] is not None else -1,r['key'][1]))
        previous=None
        for current in rows:
            elapsed=None;eligible=None;reason=None
            if gid in unknown_order:reason='native_order_unknown'
            elif previous is None:eligible=False;reason='first_native_row'
            elif previous['snap'] is False or current['snap'] is False:eligible=False;reason='known_control_break'
            elif previous['team'] is not None and current['team'] is not None and previous['team']!=current['team']:eligible=False;reason='known_offense_change'
            elif previous['team'] is None or current['team'] is None:reason='possible_unknown_offense'
            elif previous['snap'] is None or current['snap'] is None:reason='unknown_snap'
            elif any(v is None or v<0 or int(v)!=v for v in (previous['drive'],current['drive'])):reason='unknown_drive'
            elif previous['drive']!=current['drive']:eligible=False;reason='drive_change'
            elif previous['quarter'] not in (1,2,3,4,5) or current['quarter'] not in (1,2,3,4,5):reason='unknown_quarter'
            elif previous['quarter']!=current['quarter']:eligible=False;reason='quarter_change'
            elif previous['clock'] is None or current['clock'] is None:reason='unknown_clock'
            elif not 0<=current['clock']<=previous['clock']<=3600:reason='clock_out_of_range_or_nonmonotonic'
            else:eligible=True;elapsed=previous['clock']-current['clock']
            if current['snap'] is not False:
                for team in teams[gid] if current['team'] is None else {current['team']}:
                    c=pace[gid,team]
                    if eligible is None:c['unknown_eligibility_events']+=1
                    elif eligible:
                        c['eligible_events']+=1;c['known_outcome_events']+=1;c['observed_outcome_sum']+=elapsed
            rejections[reason or 'known_interval']+=1;previous=current
    pace_rows=[];pair_rows=[]
    for gid,g in sorted(expected.items()):
        vals=[]
        for team in (g['home_team'],g['away_team']):
            c=pace[gid,team];order_known=gid not in unknown_order and gid in groups
            if not owned[gid,team]:c['unknown_eligibility_events']+=1
            n=c['known_outcome_events'];known=c['observed_outcome_sum']/n if n else None
            c.update(value=known if order_known and not c['unknown_eligibility_events'] else None,native_order_verified=order_known)
            pace_rows.append(dict(game_id=gid,season=season,week=g['week'],team=team,metrics={'G01-M04':c}))
            vals.append(known_snaps[gid,team] if owned[gid,team] and not unknown_snaps[gid,team] else None)
        pair_rows.append(dict(game_id=gid,season=season,week=g['week'],home_team=g['home_team'],away_team=g['away_team'],values=vals))
    # Compatible schema views for a pure existing transform; no High approval is implied.
    pace_view=dict(version=PACE_VERSION,before_period=boundary,pregame_serving_eligible=False,game_rows=pace_rows,semantic_sha256=digest(pace_rows))
    pair_view=dict(version=PAIR_VERSION,before_period=boundary,pregame_serving_eligible=False,game_rows=pair_rows,semantic_sha256=digest(pair_rows))
    joint=build_joint_pace_play_budgets(pace_view,pair_view,schedule)
    return dict(version=VERSION,season=season,before_period=boundary,source_keys=len(projected),native_order_proof=proof,
        pace_rows=pace_rows,physical_pair_rows=pair_rows,interval_rejections=dict(rejections),joint_diagnostic=joint,
        exact_team_game_pace_rows=sum(r['metrics']['G01-M04']['value'] is not None for r in pace_rows),
        definition='Minimal native-order physical-start elapsed game-clock intervals; all controls/source unknowns retained; fixed historical W4–17 evaluation and W1–3 reference/prior8',
        qualification='Unreviewed coverage diagnostic only, zero catalog promotions',pregame_serving_eligible=False,models=0)
