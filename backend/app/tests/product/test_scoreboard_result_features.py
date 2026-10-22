from copy import deepcopy
from datetime import datetime,UTC,timedelta
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from backend.app.product_services.scoreboard_result_features import normalize_completed_scores,build_opponent_team_point_distributions,capture_scoreboard_results,read_indexed_scoreboard,SOURCE_VERSION

OBS='2026-10-19T10:00:00Z';GID='2026_01_BUF_MIA'
SCHEDULE=dict(game_rows=[dict(game_id=GID,season=2026,week=1,game_type='REG',home_team='MIA',away_team='BUF')])


def payload():
    status=dict(state='post',completed=True,name='STATUS_FINAL')
    return dict(season=dict(year=2026,type=2),week=dict(number=1),events=[dict(id='401',status=dict(type=deepcopy(status)),
        competitions=[dict(id='401',date='2026-09-13T17:00:00Z',status=dict(type=deepcopy(status)),competitors=[
            dict(homeAway='home',team=dict(abbreviation='MIA'),score='14'),dict(homeAway='away',team=dict(abbreviation='BUF'),score='21')])])])


def normalize(p=None):return normalize_completed_scores(p or payload(),SCHEDULE,season=2026,week=1,observed_at=OBS,source_ref={'snapshot_id':'source','sha256':'a'*64})


def proof():return {GID:dict(eligible=True,schedule_scores=(14,21),pbp_final_scores=(14,21),pbp_terminal_scores=(14,21),native_terminal_play_id='99',positive_offense_after_terminal=0)}


def build(rows=None,p=None):return build_opponent_team_point_distributions(rows if rows is not None else normalize(),p or proof(),before_period=202606)


def test_completed_native_points_are_opponent_team_scores_not_DST_concessions():
    r=build();profiles={x['team']:x for x in r['team_distributions']}
    assert profiles['MIA']['mean_opponent_real_points']==21
    assert profiles['BUF']['mean_opponent_real_points']==14
    assert r['game_rows'][0]['exact_completed_score']==(14,21)
    assert r['pregame_serving_eligible']is False and r['forecast']is None


@pytest.mark.parametrize('kind',['live','suspended','canceled','missing_completed','outer_disagrees','future_date'])
def test_provider_finalness_is_required_not_numeric_copies(kind):
    p=payload();c=p['events'][0]['competitions'][0];status=c['status']['type']
    if kind=='live':status.update(state='in',completed=False,name='STATUS_IN_PROGRESS')
    elif kind=='suspended':status.update(completed=False,name='STATUS_SUSPENDED')
    elif kind=='canceled':status.update(name='STATUS_CANCELED')
    elif kind=='missing_completed':del status['completed']
    elif kind=='outer_disagrees':p['events'][0]['status']['type']['state']='pre'
    else:c['date']='2026-10-20T17:00:00Z'
    n=normalize(p);assert n[0]['completed_score_eligible']is False
    r=build(n);assert r['game_rows'][0]['exact_completed_score']is None
    assert r['team_distributions'][0]['mean_opponent_real_points']is None


@pytest.mark.parametrize('score',[None,'',True,'-1','3.5','NaN'])
def test_unknown_or_invalid_score_not_shutout_zero(score):
    p=payload();p['events'][0]['competitions'][0]['competitors'][0]['score']=score
    assert normalize(p)[0]['completed_score_eligible']is False


def test_known_zero_score_and_ordinary_overtime_final_are_valid():
    p=payload();p['events'][0]['competitions'][0]['competitors'][0]['score']='0'
    r=normalize(p);pr=proof();pr[GID].update(schedule_scores=(0,21),pbp_final_scores=(0,21),pbp_terminal_scores=(0,21))
    assert build(r,pr)['game_rows'][0]['exact_completed_score']==(0,21)
    p=payload();p['events'][0]['competitions'][0]['status']['type']['detail']='Final/OT'
    assert normalize(p)[0]['completed_score_eligible']is True


@pytest.mark.parametrize('field',['eligible','schedule_scores','pbp_final_scores','pbp_terminal_scores'])
def test_each_independent_final_corroboration_required(field):
    p=proof();p[GID][field]=False if field=='eligible'else (14,20)
    assert build(p=p)['game_rows'][0]['exact_completed_score']is None


def test_source_revisions_conflict_not_resolved_by_latest_or_extra_votes():
    rows=normalize();new=deepcopy(rows[0]);new['provider_reported_home_score']=15
    assert build(rows+[new])['game_rows'][0]['exact_completed_score']is None
    old=build(rows);dup=deepcopy(rows[0]);dup['source_ref']['snapshot_id']='another';dup['source_ref']['captured_at']='later'
    assert build(rows+[dup])['semantic_sha256']==old['semantic_sha256']


def test_missing_source_game_stays_unknown_not_dropped_from_native_universe():
    r=build([],proof())
    assert len(r['game_rows'])==1 and r['game_rows'][0]['exact_completed_score']is None
    assert r['team_distributions'][0]['unknown_games']==1


@pytest.mark.parametrize('kind',['week','native_duplicate','home_away','competition_id'])
def test_native_period_and_identity_conflicts_never_join_by_names(kind):
    p=payload();c=p['events'][0]['competitions'][0]
    if kind=='week':p['week']['number']=2
    elif kind=='native_duplicate':p['events'].append(deepcopy(p['events'][0]))
    elif kind=='home_away':c['competitors'][0]['team']['abbreviation']='GB'
    else:c['id']='other'
    if kind=='competition_id':assert normalize(p)[0]['completed_score_eligible']is False
    else:
        with pytest.raises(ValueError):normalize(p)


def test_capture_preserves_original_http_bytes_with_explicit_new_source_contract():
    raw=json.dumps(payload(),indent=2).encode()
    class Service:
        def capture_file(self,path,**kwargs):return dict(raw=Path(path).read_bytes(),**kwargs)
    result=capture_scoreboard_results(Service(),season=2026,week=1,slate_lock_at=None,fetcher=lambda url:raw)
    assert result['raw']==raw and result['metadata']['contract_id']==SOURCE_VERSION
    assert result['media_type']=='application/json'and result['row_count']==1
    with pytest.raises(ValueError):capture_scoreboard_results(Service(),season=2026,week=2,slate_lock_at=None,fetcher=lambda url:raw)


def test_actual_indexed_reader_hash_clock_and_original_envelope_scope(tmp_path,monkeypatch):
    from backend.app.services import source_capture
    p=tmp_path/'original.json';p.write_bytes(json.dumps(payload()).encode());now=datetime.now(UTC)
    snap=SimpleNamespace(source_system='espn',source_uri='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week=1',
        season=2026,week=1,dataset='completed_game_scoreboard',media_type='application/json',metadata_json=dict(contract_id=SOURCE_VERSION),
        observed_at=now-timedelta(hours=1),captured_at=now-timedelta(hours=1),byte_count=p.stat().st_size,artifact_path=p,row_count=1,snapshot_id='snapshot',content_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def verify(s):assert hashlib.sha256(Path(s.artifact_path).read_bytes()).hexdigest()==s.content_sha256
    monkeypatch.setattr(source_capture,'verify_snapshot_artifact',verify)
    assert read_indexed_scoreboard(snap,actual_read_at=now)['payload']==payload()
    with pytest.raises(ValueError):read_indexed_scoreboard(snap,actual_read_at=now-timedelta(days=1))


@pytest.mark.parametrize('kind',['valid','later_offense','score_conflict','native_week_conflict','duplicate_order'])
def test_native_terminal_corroboration_is_not_end_marker_alone(tmp_path,monkeypatch,kind):
    import csv
    from backend.app.product_services import schedule_context_features
    from backend.app.product_services.scoreboard_result_features import read_score_corroboration
    from backend.app.services import source_capture
    now=datetime.now(UTC);schedule_path=tmp_path/'schedule.csv'
    with schedule_path.open('w',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=['game_id','home_score','away_score']);writer.writeheader();writer.writerow(dict(game_id=GID,home_score=14,away_score=21))
    row=dict(game_id=GID,play_id=1,season=2026,week=1,season_type='REG',home_team='MIA',away_team='BUF',home_score=14,away_score=21,total_home_score=0,total_away_score=0,order_sequence=1,
        play_type_nfl='PASS',desc='play',pass_attempt=1,rush_attempt=0,sack=0,qb_dropback=1,qb_spike=0,qb_kneel=0,qb_scramble=0,two_point_attempt=0)
    end=row|dict(play_id=2,order_sequence=2,play_type_nfl='END_GAME',desc='END GAME',pass_attempt=0,qb_dropback=0,total_home_score=14,total_away_score=21)
    rows=[row,end]
    if kind=='later_offense':rows.append(row|dict(play_id=3,order_sequence=3))
    elif kind=='score_conflict':rows[0]['home_score']=15
    elif kind=='native_week_conflict':rows[1]['week']=2
    elif kind=='duplicate_order':rows.append(row|dict(play_id=3,order_sequence=2))
    raw=tmp_path/'pbp.csv'
    with raw.open('w',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerows(rows)
    common=dict(source_system='nflreadpy',source_uri='nflreadpy://pbp/2026',dataset='play_by_play',media_type='text/csv',
        metadata_json=dict(contract_id='operational_opportunity_source_v1',loader='load_pbp'),season=2026,week=6,observed_at=now-timedelta(hours=1),captured_at=now-timedelta(hours=1),
        byte_count=raw.stat().st_size,artifact_path=raw,snapshot_id='pbp',content_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    pbp=SimpleNamespace(**common);schedule=SimpleNamespace(artifact_path=schedule_path,snapshot_id='schedule',content_sha256=hashlib.sha256(schedule_path.read_bytes()).hexdigest())
    monkeypatch.setattr(schedule_context_features,'load_schedule_context',lambda *a,**k:SCHEDULE)
    monkeypatch.setattr(source_capture,'verify_snapshot_artifact',lambda s:None)
    if kind in {'native_week_conflict','duplicate_order'}:
        with pytest.raises(ValueError):read_score_corroboration(schedule,pbp,before_period=202606,actual_read_at=now)
    else:
        _,proofs,_=read_score_corroboration(schedule,pbp,before_period=202606,actual_read_at=now)
        assert proofs[GID]['eligible']is (kind=='valid')
