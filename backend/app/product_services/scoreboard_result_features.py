"""Explicit completed scoreboard facts and observed opponent TEAM real points."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal,InvalidOperation
import csv,hashlib,json,tempfile
from pathlib import Path
from urllib.request import Request,urlopen
from .espn_markets import scoreboard_url
from .factual_designation import clock
from .market_snapshots import canonical_team
from .market_environment_features import record_clock
from .evaluation_record import digest

VERSION='scoreboard_result_features_v1'
SOURCE_VERSION='espn_completed_scoreboard_source_v1'
MAX_BYTES=4*1024*1024


def _score(value):
    if value is None or isinstance(value,bool):return None
    try:n=Decimal(str(value))
    except InvalidOperation:return None
    return int(n)if n.is_finite()and n==int(n)and 0<=n<=200 else None


def capture_scoreboard_results(service,*,season,week,slate_lock_at,fetcher=None):
    if type(season)is not int or type(week)is not int or not 1<=week<=18:raise ValueError('Explicit native REG period required')
    url=scoreboard_url(season,week)
    if fetcher is None:
        with urlopen(Request(url,headers={'Accept':'application/json','Cache-Control':'no-cache'}),timeout=30)as response:
            raw=response.read(MAX_BYTES+1)
    else:raw=fetcher(url)
    if not isinstance(raw,bytes)or len(raw)>MAX_BYTES:raise ValueError('Bounded original HTTP response bytes required')
    payload=json.loads(raw)
    if not isinstance(payload,dict)or not isinstance(payload.get('events'),list):raise ValueError('Native scoreboard response required')
    if any(type(v)is not int for v in (payload['season']['year'],payload['season']['type'],payload['week']['number']))or payload['season']['year']!=season or payload['season']['type']!=2 or payload['week']['number']!=week:raise ValueError('Response period differs from requested URL')
    with tempfile.TemporaryDirectory()as directory:
        p=Path(directory)/f'espn_results_{season}_w{week}.json';p.write_bytes(raw)
        return service.capture_file(p,source_system='espn',dataset='completed_game_scoreboard',season=season,week=week,
            slate='offline_completed_score_features',source_license='public ESPN scoreboard; no paid access',source_uri=url,
            slate_lock_at=slate_lock_at,observation_basis='capture_clock',row_count=len(payload['events']),media_type='application/json',
            metadata=dict(contract_id=SOURCE_VERSION,original_http_response_bytes=True,publication_at=None,
                use='Revised retrospectively observed completed-result evidence; not original historical pregame availability'))


def read_indexed_scoreboard(snapshot,*,actual_read_at):
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at)
    if read is None or read>datetime.now(UTC):raise ValueError('Actual nonfuture read required')
    if snapshot.source_system!='espn'or snapshot.source_uri!=scoreboard_url(snapshot.season,snapshot.week):raise ValueError('Indexed native ESPN endpoint required')
    if not record_clock(snapshot.observed_at)<=record_clock(snapshot.captured_at)<=read or snapshot.byte_count>MAX_BYTES:raise ValueError('Source availability/bound differs')
    verify_snapshot_artifact(snapshot)
    path=Path(snapshot.artifact_path)
    if snapshot.dataset=='completed_game_scoreboard'and snapshot.media_type=='application/json'and (snapshot.metadata_json or {}).get('contract_id')==SOURCE_VERSION:
        payload=json.loads(path.read_bytes());observed=record_clock(snapshot.observed_at)
        if snapshot.row_count!=len(payload['events']):raise ValueError('Indexed native event row count differs')
    elif snapshot.dataset=='schedule_market_snapshot'and snapshot.media_type=='text/csv':
        old=csv.field_size_limit()
        try:
            csv.field_size_limit(MAX_BYTES)
            with path.open()as stream:rows=list(csv.DictReader(stream))
        finally:csv.field_size_limit(old)
        if len(rows)!=1 or snapshot.row_count!=1:raise ValueError('One original native envelope required')
        observed=clock(rows[0]['capture_observed_at'])
        if observed is None or observed>record_clock(snapshot.observed_at):raise ValueError('Original envelope clock differs')
        payload=json.loads(rows[0]['response_json'])
    else:raise ValueError('Unsupported immutable scoreboard contract')
    return dict(payload=payload,observed_at=observed,source_ref=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,
        bytes=snapshot.byte_count,source_uri=snapshot.source_uri,captured_at=record_clock(snapshot.captured_at).isoformat(),
        observed_at=observed.isoformat(),publication_at=None))


def normalize_completed_scores(payload,schedule,*,season,week,observed_at,source_ref):
    observed=clock(observed_at)
    if observed is None or any(type(v)is not int for v in (payload['season']['year'],payload['season']['type'],payload['week']['number']))or payload['season']['year']!=season or payload['season']['type']!=2 or payload['week']['number']!=week:raise ValueError('Explicit source REG period/clock required')
    expected={r['game_id']:r for r in schedule['game_rows']if r['game_type']=='REG'and r['season']==season and r['week']==week}
    native={};seen_ids=set()
    for event in payload['events']:
        eid=str(event.get('id')or'')
        if not eid.isdigit()or eid in seen_ids:raise ValueError('Unique native ESPN event identity required')
        seen_ids.add(eid)
        for competition in event.get('competitions',[]):
            cs=competition.get('competitors',[])
            if len(cs)!=2 or {c.get('homeAway')for c in cs}!={'home','away'}:raise ValueError('Native two-sided team identity required')
            teams={c['homeAway']:canonical_team(c['team']['abbreviation'])for c in cs}
            matches=[r for r in expected.values()if (r['home_team'],r['away_team'])==(teams['home'],teams['away'])]
            if len(matches)!=1:raise ValueError('Missing/ambiguous native schedule binding')
            game=matches[0];gid=game['game_id']
            if gid in native:raise ValueError('Duplicate native game competition')
            status=competition.get('status',{}).get('type',{});outer=event.get('status',{}).get('type')
            reason=None
            if not(status.get('state')=='post'and status.get('completed')is True and status.get('name')=='STATUS_FINAL'):reason='No explicit completed/post/final source contract'
            if outer is not None and {k:outer.get(k)for k in ('state','completed','name')}!={k:status.get(k)for k in ('state','completed','name')}:reason='Event/competition terminal statuses disagree'
            played=clock(competition.get('date')or event.get('date'))
            if played is None or played>observed:reason='Game date not proven before observed final result'
            scores={c['homeAway']:_score(c.get('score'))for c in cs}
            if None in scores.values():reason='Unknown/invalid nonnegative integer final points'
            if competition.get('id')not in (None,eid):reason='Event/competition native IDs differ'
            native[gid]=dict(game_id=gid,season=season,week=week,home_team=teams['home'],away_team=teams['away'],source_game_id=eid,
                provider_reported_home_score=scores['home'],provider_reported_away_score=scores['away'],completed_score_eligible=reason is None,
                completion_status=deepcopy(status),unknown_reason=reason,source_ref=deepcopy(source_ref))
    for gid,game in expected.items():
        if gid not in native:native[gid]=dict(game_id=gid,season=season,week=week,home_team=game['home_team'],away_team=game['away_team'],
            source_game_id=None,provider_reported_home_score=None,provider_reported_away_score=None,completed_score_eligible=False,
            completion_status=None,unknown_reason='No native source game',source_ref=deepcopy(source_ref))
    return sorted(native.values(),key=lambda r:r['game_id'])


def build_opponent_team_point_distributions(score_rows,corroboration,*,before_period):
    grouped=defaultdict(list)
    for row in score_rows:
        parts=row['game_id'].split('_')
        if len(parts)!=4 or parts[:2]!=[str(row['season']),f"{row['week']:02d}"] or (canonical_team(parts[3]),canonical_team(parts[2]))!=(row['home_team'],row['away_team']):raise ValueError('Native source game/home-away scope differs')
        if row['season']*100+row['week']>=before_period:raise ValueError('Strict prior completed score scope required')
        grouped[row['game_id']].append(row)
    for gid in corroboration:
        if gid not in grouped:
            parts=gid.split('_');grouped[gid]=[dict(game_id=gid,season=int(parts[0]),week=int(parts[1]),home_team=canonical_team(parts[3]),away_team=canonical_team(parts[2]),
                source_game_id=None,provider_reported_home_score=None,provider_reported_away_score=None,completed_score_eligible=False,completion_status=None,unknown_reason='No completed-score source available',source_ref=None)]
    games=[];teams=defaultdict(list)
    for gid,rows in sorted(grouped.items()):
        eligible=[r for r in rows if r['completed_score_eligible']]
        pairs={(r['provider_reported_home_score'],r['provider_reported_away_score'])for r in eligible}
        home,away=rows[0]['home_team'],rows[0]['away_team']
        if any((r['home_team'],r['away_team'])!=(home,away)for r in rows):raise ValueError('Source home/away identity disagreement')
        proof=corroboration.get(gid);scores=next(iter(pairs))if len(pairs)==1 else None
        valid=bool(scores is not None and proof is not None and proof.get('eligible')is True
            and tuple(proof['schedule_scores'])==scores and tuple(proof['pbp_final_scores'])==scores and tuple(proof['pbp_terminal_scores'])==scores)
        reason=None if valid else 'Missing/conflicting completed-status and schedule/PBP terminal corroboration'
        game=dict(game_id=gid,season=rows[0]['season'],week=rows[0]['week'],home_team=home,away_team=away,
            opponent_team_reported_final_scores=dict(home=scores[0],away=scores[1])if scores is not None else None,
            exact_completed_score=scores if valid else None,unknown_reason=reason,source_observations=deepcopy(rows),corroboration=deepcopy(proof))
        games.append(game)
        for team,opponent,index in ((home,away,1),(away,home,0)):
            teams[(game['season'],team)].append(dict(game_id=gid,opponent=opponent,
                opponent_team_reported_final_score=scores[index]if scores is not None else None,
                exact_opponent_team_real_points=scores[index]if valid else None,unknown_reason=reason))
    profiles=[]
    for (season,team),logs in sorted(teams.items()):
        values=[r['exact_opponent_team_real_points']for r in logs if r['exact_opponent_team_real_points']is not None];n=len(values);unknown=len(logs)-n
        mean=sum(values)/n if n else None;var=sum((v-mean)**2 for v in values)/n if n else None
        hist=[dict(opponent_real_points=k,games=v,known_sample_frequency=v/n,all_observed_games_frequency=v/n if not unknown else None)for k,v in sorted(Counter(values).items())]
        profiles.append(dict(season=season,team=team,logs=logs,known_completed_games=n,unknown_games=unknown,
            known_sample_mean_opponent_real_points=mean,known_sample_population_variance=var,
            mean_opponent_real_points=mean if not unknown else None,population_variance=var if not unknown else None,observed_histogram=hist))
    semantic_games=[]
    for game in games:
        observations={json.dumps({k:r[k]for k in ('provider_reported_home_score','provider_reported_away_score','completed_score_eligible','completion_status','unknown_reason')},sort_keys=True)for r in game['source_observations']}
        proof=game['corroboration']
        semantic_games.append({k:v for k,v in game.items()if k not in {'source_observations','corroboration'}}|dict(provider_fact_set=sorted(observations),corroboration={k:proof.get(k)for k in ('eligible','schedule_scores','pbp_final_scores','pbp_terminal_scores','native_terminal_play_id','positive_offense_after_terminal')}if proof else None))
    core=dict(version=VERSION,before_period=before_period,game_rows=games,team_distributions=profiles,
        definition='Opponent TEAM reported final points, including all of that team offense/defense/special-teams scoring; not defensive-unit-only concessions or DST fantasy points')
    semantic_basis={**core,'game_rows':semantic_games}
    return dict(**core,semantic_sha256=digest(semantic_basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Current retrospective source observation is not original historical pregame availability',
            'Completed/post/final native provider status must be corroborated with schedule and PBP terminal totals',
            'Unproven/conflicting games are unknown, never an observed zero; DST scoring deductions are not applied',
            'Observed integer-score frequencies are not a next-game distribution or calibrated prediction'])


def read_score_corroboration(schedule_snapshot,pbp_snapshot,*,before_period,actual_read_at):
    """Independent native schedule/final/terminal totals; no finalness inferred alone."""
    from backend.app.services.source_capture import verify_snapshot_artifact
    from .schedule_context_features import load_schedule_context
    schedule=load_schedule_context(schedule_snapshot,cutoff=actual_read_at)
    read=clock(actual_read_at);metadata=pbp_snapshot.metadata_json or {}
    verify_snapshot_artifact(pbp_snapshot)
    if (pbp_snapshot.source_system!='nflreadpy'or pbp_snapshot.dataset!='play_by_play'or pbp_snapshot.media_type!='text/csv'
        or metadata.get('contract_id')!='operational_opportunity_source_v1'or metadata.get('loader')!='load_pbp'
        or pbp_snapshot.source_uri!=f'nflreadpy://pbp/{pbp_snapshot.season}'or before_period!=pbp_snapshot.season*100+pbp_snapshot.week
        or pbp_snapshot.byte_count>64*1024*1024 or not record_clock(pbp_snapshot.observed_at)<=record_clock(pbp_snapshot.captured_at)<=read):
        raise ValueError('Indexed bounded native PBP corroboration required')
    expected={r['game_id']:r for r in schedule['game_rows']if r['game_type']=='REG'and r['season']==before_period//100 and r['season']*100+r['week']<before_period}
    native_scores={};seen_schedule=set()
    with Path(schedule_snapshot.artifact_path).open(newline='')as stream:
        for row in csv.DictReader(stream):
            gid=row['game_id']
            if gid not in expected:continue
            if gid in seen_schedule:raise ValueError('Duplicate native schedule score')
            seen_schedule.add(gid);native_scores[gid]=(_score(row.get('home_score')),_score(row.get('away_score')))
    seen=set();events=defaultdict(list);pairs=defaultdict(set);order_seen=defaultdict(set)
    required={'game_id','play_id','season','week','season_type','home_team','away_team','home_score','away_score','total_home_score','total_away_score','order_sequence','play_type_nfl','desc',*('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')}
    with Path(pbp_snapshot.artifact_path).open(newline='')as stream:
        reader=csv.DictReader(stream)
        if not required<=set(reader.fieldnames or []):raise ValueError('Native final/terminal corroboration fields absent')
        for index,row in enumerate(reader):
            if index>=100000:raise ValueError('PBP source row bound exceeded')
            if row['season_type']!='REG':continue
            gid=row['game_id']
            season=Decimal(row['season']);week=Decimal(row['week'])
            if not season.is_finite()or not week.is_finite()or season!=int(season)or week!=int(week)or season!=pbp_snapshot.season or not 1<=week<=18:raise ValueError('PBP corroboration native period differs')
            if int(season)*100+int(week)>=before_period:continue
            if gid not in expected:raise ValueError('PBP game missing native schedule binding')
            game=expected[gid]
            if (int(season),int(week))!=(game['season'],game['week']):raise ValueError('PBP native game period differs')
            if (canonical_team(row['home_team']),canonical_team(row['away_team']))!=(game['home_team'],game['away_team']):raise ValueError('PBP home/away contradicts native schedule')
            play=Decimal(row['play_id']);seq=Decimal(row['order_sequence'])
            if not play.is_finite()or play!=int(play)or not seq.is_finite():raise ValueError('Native play/order required')
            key=(gid,str(int(play)))
            if key in seen or seq in order_seen[gid]:raise ValueError('Duplicate native play/order')
            seen.add(key);order_seen[gid].add(seq)
            final=(_score(row['home_score']),_score(row['away_score']))
            if None not in final:pairs[gid].add(final)
            indicators=[row.get(k)for k in ('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')]
            positive=any(v not in (None,'')and Decimal(v)!=0 for v in indicators)
            terminal=(row['play_type_nfl']=='END_GAME'or row['desc']=='END GAME')and not positive
            events[gid].append(dict(play_id=key[1],order=seq,positive_offense=positive,terminal=terminal,
                terminal_scores=(_score(row['total_home_score']),_score(row['total_away_score']))))
    proof={}
    for gid,game in sorted(expected.items()):
        rows=events.get(gid,[]);ends=[r for r in rows if r['terminal']]
        end=ends[0]if len(ends)==1 else None
        terminal=end['terminal_scores']if end and None not in end['terminal_scores']else None
        after=[r for r in rows if end and r['order']>end['order']and r['positive_offense']]
        final=next(iter(pairs[gid]))if len(pairs[gid])==1 else None
        scheduled=native_scores.get(gid)
        eligible=bool(terminal is not None and final is not None and scheduled is not None and None not in scheduled
            and not after and scheduled==final==terminal)
        proof[gid]=dict(eligible=eligible,schedule_scores=scheduled,pbp_final_scores=final,pbp_terminal_scores=terminal,
            native_terminal_play_id=end['play_id']if end else None,positive_offense_after_terminal=len(after),
            meaning='Corroboration only; native completed/post/final scoreboard status is separately required')
    return schedule,proof,dict(schedule_snapshot_id=str(schedule_snapshot.snapshot_id),schedule_sha256=schedule_snapshot.content_sha256,
        pbp_snapshot_id=str(pbp_snapshot.snapshot_id),pbp_sha256=pbp_snapshot.content_sha256,actual_read_at=read.isoformat())
