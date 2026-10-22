import csv
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile
import pytest
from backend.app.product_services import special_contest_results as results
from backend.app.product_services.single_stat import score


def source(tmp_path, lineup, points=3, name='contest-standings-987654.csv'):
    p=tmp_path/name
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['Rank','EntryId','EntryName','Points','Lineup','Player','Roster Position','%Drafted']);w.writeheader();w.writerow(dict(Rank=1,EntryId='fixture-entry-1',EntryName='fixture-learning-user',Points=points,Lineup=lineup))
    return p


def ingest(p,tmp_path,fmt='single_stat',variant='touchdowns',**kwargs):
    return results.import_results(p,season=2020,week=1,slate='SUNDAY_MAIN',contest_id='987654',contest_format=fmt,variant=variant,
        directory=tmp_path/'ledger',source_reference='fixture: explicit verified scope/scoring contract',**kwargs)


def pool(fmt='single_stat'):
    rows=[dict(source_player_id=str(i+1),player_master_id=f'canonical-{i}',team='WAS' if i%2 else 'SF',game_id=f'game-{i%2}',tier=f'T{i+1}')for i in range(6)]
    return dict(kind='pool',season=2020,week=1,slate='SUNDAY_MAIN',source=dict(season=2020,week=1),variant='touchdowns',tier_labels=[f'T{i}'for i in range(1,7)],players=rows,native_draft_group_id=123)


@pytest.mark.parametrize('variant,points,units',[('touchdowns',3,'touchdowns'),('total_yards',231,'yards'),('passing_yards',490,'yards')])
def test_observed_single_stat_units_are_preserved_without_components(tmp_path,variant,points,units):
    p=source(tmp_path,'FLEX Fixture A FLEX Fixture B FLEX Fixture C',points)
    r,duplicate=ingest(p,tmp_path,variant=variant)
    assert not duplicate and r['units']==units and r['best_observed_score']==points
    e=results.entries(r,'fixture-learning-user',directory=tmp_path/'ledger')[0]
    assert e['observed_score']==points and e['identity_status']=='unverified'
    assert e['forecast_comparison']['status']=='unmatched' and e['roi'] is None
    assert r['reconciliation_status']=='unverified_components'
    assert (tmp_path/'ledger'/r['record_id']/'source.bin').read_bytes()==p.read_bytes()


def test_tiers_native_ids_roles_and_duplicate_import_are_immutable(tmp_path,monkeypatch):
    p=source(tmp_path,' '.join(f'T{i} Fixture {i} ({i})'for i in range(1,7)),147.22)
    native=pool('tiers');monkeypatch.setattr(results,'forecast_comparison',lambda *a:dict(status='unmatched'))
    r,duplicate=ingest(p,tmp_path,'tiers',None,pool_sha256='nativepool',pool_loader=lambda *a:native)
    assert r['units']=='dk_fantasy_points' and not duplicate
    assert ingest(p,tmp_path,'tiers',None,pool_sha256='nativepool',pool_loader=lambda *a:native)[1]
    e=results.entries(r,'fixture-learning-user',directory=tmp_path/'ledger',pool_loader=lambda *a:native)[0]
    assert e['identity_status']=='resolved' and len(e['players'])==6


@pytest.mark.parametrize('lineup,fmt,variant',[
 ('FLEX A FLEX B FLEX C','single_stat',None),
 ('FLEX A FLEX B FLEX C','single_stat','fantasy_points'),
 ('T1 A T2 B T3 C T4 D T5 E','tiers',None),
 ('T1 A T2 B T3 C T4 D T5 E T5 F','tiers',None),
 ('FLEX A FLEX A FLEX C','single_stat','touchdowns'),
 ('FLEX A FLEX B FLEX C','tiers',None),
])
def test_invalid_ambiguous_or_wrong_format_never_commits(tmp_path,lineup,fmt,variant):
    p=source(tmp_path,lineup)
    with pytest.raises(ValueError):ingest(p,tmp_path,fmt,variant)
    assert not list((tmp_path/'ledger').glob('*/record.json')) and p.exists()


def test_wrong_single_stat_units_rejected(tmp_path):
    with pytest.raises(ValueError,match='units'):ingest(source(tmp_path,'FLEX A FLEX B FLEX C',3.25),tmp_path)


def test_native_scope_tier_and_canonical_duplicates_fail_closed(tmp_path):
    p=source(tmp_path,' '.join(f'T{i} Fixture {i} ({i})'for i in range(1,7)))
    for change in ['week','tier','identity','games']:
        native=pool('tiers')
        if change=='week':native['week']=2
        if change=='tier':native['players'][0]['tier']='T2'
        if change=='identity':native['players'][0]['player_master_id']=native['players'][1]['player_master_id']
        if change=='games':
            for x in native['players']:x['game_id']='same-game'
        with pytest.raises(ValueError):ingest(p,tmp_path,'tiers',None,pool_sha256='pool',pool_loader=lambda *a:native)


def test_zip_raw_roundtrip_and_correction_lineage(tmp_path):
    p=source(tmp_path,'FLEX A FLEX B FLEX C')
    z=tmp_path/'contest-standings-987654.zip'
    with ZipFile(z,'w')as f:f.write(p,p.name)
    a,_=ingest(z,tmp_path)
    source(tmp_path,'FLEX A FLEX B FLEX C',4)
    with pytest.raises(ValueError,match='correction'):ingest(p,tmp_path)
    b,_=ingest(p,tmp_path,correction_of=a['record_id'])
    assert b['record_id']!=a['record_id'] and results.load(a['record_id'],tmp_path/'ledger')['best_observed_score']==3
    groups=results.learning_groups(season=2020,week=1,entry_user='fixture-learning-user',directory=tmp_path/'ledger')
    assert len(groups)==1 and groups[0]['record_id']==b['record_id']


def test_single_stat_contract_does_not_invent_rare_touchdowns_or_use_ppr():
    assert score('touchdowns',dict(rushing_tds=1,receiving_tds=2,passing_tds=9))['value'] is None
    components=dict(rushing_tds=1,receiving_tds=2,kick_return_tds=0,missed_fg_return_tds=0,punt_return_tds=0,offensive_fumble_recovery_tds=0,defensive_tds=0,passing_tds=9)
    assert score('touchdowns',components)['value']==3
    assert score('total_yards',dict(rushing_yards=41,receiving_yards=62,passing_yards=400,receptions=9))['value']==103
    assert score('passing_yards',dict(passing_yards=400,rushing_yards=41))['value']==400


def test_typed_weekly_report_keeps_financial_scope_and_versions_evidence():
    from backend.app.product_services.slate_learning import build_weekly_learning_report
    group=dict(record_id='one',contest_format='single_stat',variant='touchdowns',contest_id='987654',entries=[dict(observed_score=3)])
    a=build_weekly_learning_report(season=2020,week=1,entry_user='fixture',slate_reports=[],format_results=[group])
    assert a['summary']['entries']==0 and a['summary']['typed_contest_entries']==1
    assert a['format_results'][0]['entries'][0]['observed_score']==3
    b=build_weekly_learning_report(season=2020,week=1,entry_user='fixture',slate_reports=[],format_results=[{**group,'entries':[dict(observed_score=4)]}])
    assert a['evidence_hash']!=b['evidence_hash']


def test_classic_showdown_detection_preserved_and_typed_never_misattributed():
    import pandas as pd
    from backend.app.product_services.ownership import OwnershipService
    resolve=OwnershipService._resolve_contest_format
    assert resolve(None,slate='SUNDAY_MAIN',roster_positions=pd.Series(['QB','RB','WR','TE','DST']))=='classic'
    assert resolve(None,slate='MONDAY_NIGHT',roster_positions=pd.Series(['CPT','FLEX']))=='showdown'
    for roles in [['T1','T2'],['FLEX']]:
        with pytest.raises(ValueError):resolve(None,slate='SUNDAY_MAIN',roster_positions=pd.Series(roles))


def test_unique_and_ambiguous_forecast_correspondence_never_proves_origin(monkeypatch):
    from backend.app.product_services import single_stat
    record=dict(pool_sha256='pool',contest_format='single_stat',variant='total_yards',units='yards')
    players=[dict(role='FLEX',player_id=str(i))for i in range(3)]
    report=dict(kind='report',sha256='report1',pool_sha256='pool',variant='total_yards',units='yards',objective='highest_expected_total_yards',expected_metric=200,created_at='2020-09-01T00:00:00+00:00',players=[dict(player_master_id=str(i))for i in range(3)])
    monkeypatch.setattr(single_stat,'catalog',lambda:[dict(kind='report',sha256='report1')])
    monkeypatch.setattr(single_stat,'load',lambda _:report)
    result=results.forecast_comparison(record,players)
    assert result['status']=='unique_roster_correspondence' and result['origin_proven']is False
    monkeypatch.setattr(single_stat,'catalog',lambda:[dict(kind='report',sha256='report1'),dict(kind='report',sha256='report2')])
    assert results.forecast_comparison(record,players)['status']=='ambiguous_roster_correspondence'
    report['units']='dk_fantasy_points'
    assert results.forecast_comparison(record,players)['status']=='unmatched'


def test_api_reopens_exact_saved_results_and_rejects_traversal(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.product_routes import router
    monkeypatch.setattr(results,'LEDGER',tmp_path/'ledger')
    record,_=ingest(source(tmp_path,'FLEX A FLEX B FLEX C'),tmp_path)
    app=FastAPI();app.include_router(router);client=TestClient(app)
    assert client.get('/api/learning/typed-results').json()['records'][0]['record_id']==record['record_id']
    opened=client.get('/api/learning/typed-results/'+record['record_id'],params={'entry_user':'fixture-learning-user'})
    assert opened.status_code==200 and opened.json()['entries'][0]['observed_score']==3
    assert client.get('/api/learning/typed-results/invalid').status_code==422


def test_folder_typed_dispatch_archives_only_successful_validated_import(tmp_path,monkeypatch):
    from unittest.mock import MagicMock
    from backend.app.product_services.batch_import import DraftKingsBatchImportService,SelectedWeeklyContestFile
    p=source(tmp_path,'FLEX A FLEX B FLEX C')
    monkeypatch.setattr(results,'LEDGER',tmp_path/'ledger')
    service=object.__new__(DraftKingsBatchImportService);service.engine=MagicMock();service.ownership=MagicMock()
    service._ensure_schema=MagicMock();service.get_batch_result=MagicMock(return_value=None)
    service.ownership._source_file_info.return_value={'source_file_id':'immutable_source'}
    preview=service.import_directory(str(tmp_path),season=2020,week=1,slate='UNRESOLVED',recursive=False,dry_run=True,weekly_contests_only=True)
    assert preview.files[0].contest_format=='single_stat' and preview.files[0].status=='would_stage'
    selected=SelectedWeeklyContestFile(str(p),'immutable_source',2020,1,'SUNDAY_MAIN',contest_format='single_stat',scoring_variant='touchdowns',source_reference='fixture: verified scope')
    result=service.import_directory(str(tmp_path),season=2020,week=1,slate='UNRESOLVED',recursive=False,dry_run=False,weekly_contests_only=True,selected_files=[selected])
    assert result.files[0].status=='imported' and not p.exists() and list((tmp_path/'Processed').glob('**/*.csv'))
    bad=source(tmp_path,'FLEX A FLEX A FLEX C',name='contest-standings-987655.csv')
    selected=SelectedWeeklyContestFile(str(bad),'immutable_source',2020,1,'SUNDAY_MAIN',contest_format='single_stat',scoring_variant='touchdowns',source_reference='fixture: invalid duplicate')
    failed=service.import_directory(str(tmp_path),season=2020,week=1,slate='UNRESOLVED',recursive=False,dry_run=False,weekly_contests_only=True,selected_files=[selected])
    assert failed.files[0].status=='failed' and bad.exists()


def test_blank_field_participant_preserves_observed_score_without_a_roster(tmp_path):
    p=source(tmp_path,'T1 A T2 B T3 C T4 D T5 E T6 F',120)
    with p.open('a')as f:f.write('2,empty-entry,fixture-learning-user,0,,,,,\n')
    record,_=ingest(p,tmp_path,'tiers',None)
    assert record['entry_count']==2 and record['unavailable_lineups']==1
    e=results.entries(record,'fixture-learning-user',directory=tmp_path/'ledger')[1]
    assert e['identity_status']=='roster_unavailable' and e['observed_score']==0 and e['forecast_comparison']['status']=='unmatched'


def test_correction_cannot_branch_or_replace_real_evidence_with_fixture(tmp_path):
    p=source(tmp_path,'FLEX A FLEX B FLEX C')
    a,_=ingest(p,tmp_path)
    source(tmp_path,'FLEX A FLEX B FLEX C',4)
    b,_=ingest(p,tmp_path,correction_of=a['record_id'])
    source(tmp_path,'FLEX A FLEX B FLEX C',5)
    with pytest.raises(ValueError,match='branch'):ingest(p,tmp_path,correction_of=a['record_id'])
    c,_=ingest(p,tmp_path,correction_of=b['record_id'])
    assert c['correction_of']==b['record_id']
