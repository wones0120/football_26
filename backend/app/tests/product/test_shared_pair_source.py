from copy import deepcopy
import pytest
from backend.app.product_services.shared_pair_source import validate_td_revision,prepare_pair_actor_rows,VERSION
from backend.app.product_services.active_workload_distributions import VERSION as ACTIVE_VERSION
N='00-0000001';P='00000000-0000-0000-0000-000000000001';G='2026_01_BUF_MIA';CLOCK='2026-10-20T00:00:00Z'


def source():
    raw=dict(player_id=N,season=2026,week=1,season_type='REG',position='QB',team='BUF',attempts=10,passing_tds=1,targets=0)
    old=dict(source_id='id1',source_player_id=N,season=2026,week=1,team='BUF',position='QB',game_id=G,ingest_run_id='original-ingest',imported_at=CLOCK,raw_row_json=raw)
    new=deepcopy(old);new['raw_row_json']['receiving_tds']=0
    return old,new


def parents():
    old,new=source();alias=dict(alias_id='alias1',source_system='nflreadpy',source_key=N,player_master_id=P,created_at='2020-01-01T00:00:00Z');ref=dict(source_id='id1',ingest_run_id='original-ingest',imported_at=CLOCK,native_alias_evidence=[alias])
    counts=dict(pass_attempts=10,targets=0);proof=dict(native_game_id=G,season=2026,week=1,team='BUF',player_master_id=P,offense_snaps=30)
    log=dict(week=1,native_game_id=G,counts=counts,source_ref=ref,positive_offensive_participation_proven=True,participation_ref=proof)
    active=dict(version=ACTIVE_VERSION,pregame_serving_eligible=False,rows=[dict(season=2026,team='BUF',source_player_id=N,player_master_id=P,source_position='QB',logs=[log])],positive_participants_missing_weekly_rows=[],unresolved_participation_rows=[])
    weekly=dict(rows=[dict(source_player_id=N,season=2026,week=1,team='BUF',player_master_id=P,source_position='QB',QB_scope_source_proven=True,native_game_id=G,source_ref=deepcopy(ref),metrics={'G04-M01':dict(denominator=10),'G09-M01':dict(denominator=0)})])
    extract=dict(actual_alias_evidence_read_at='2026-10-20T00:01:00Z',rows=[old]);revision=validate_td_revision([new],[old],cutoff='2026-10-20T00:02:00Z')
    return active,weekly,extract,revision


def prepare(values=None):
    return prepare_pair_actor_rows(*(values or parents()),before_period=202606,cutoff='2026-10-20T00:03:00Z')


def test_new_explicit_zero_TD_field_is_preserved_with_original_import_separate():
    r=prepare()['actor_rows'][0]
    assert r['official_receiving_TDs']==0 and r['official_passing_TDs']==1
    assert r['participation']is True and r['identity_proven']


@pytest.mark.parametrize('field,value',[('game_id','2026_02_BUF_MIA'),('source_player_id','00-0000002'),('ingest_run_id','changed'),('imported_at','2027-01-01T00:00:00Z')])
def test_exact_source_revision_rejects_changed_scope_or_import(field,value):
    old,new=source();new[field]=value
    with pytest.raises(ValueError):validate_td_revision([new],[old],cutoff='2026-10-20T00:02:00Z')


def test_changed_original_raw_projection_and_missing_source_ids_rejected():
    old,new=source();new['raw_row_json']['attempts']=99
    with pytest.raises(ValueError,match='projection changed'):validate_td_revision([new],[old],cutoff='2026-10-20T00:02:00Z')
    with pytest.raises(ValueError,match='missing'):validate_td_revision([],[old],cutoff='2026-10-20T00:02:00Z')


def test_missing_TD_field_not_zero_even_with_positive_snap_proof():
    p=parents();p[3]['rows'][0]['raw_row_json'].pop('receiving_tds')
    assert prepare(p)['actor_rows'][0]['official_receiving_TDs']is None


def test_conflicting_raw_position_alias_and_unknown_QB_scope_not_proven_role():
    for mutate in ('raw','old'):
        p=parents()
        if mutate=='raw':p[3]['rows'][0]['raw_row_json']['pos']='WR'
        else:p[1]['rows'][0]['QB_scope_source_proven']=False
        assert prepare(p)['actor_rows'][0]['source_position']is None


def test_positive_flag_requires_same_game_native_positive_snap_count():
    p=parents();p[0]['rows'][0]['logs'][0]['participation_ref']['offense_snaps']=0
    with pytest.raises(ValueError,match='participation'):prepare(p)
    p=parents();p[0]['rows'][0]['logs'][0]['participation_ref']['native_game_id']='2026_02_BUF_MIA'
    with pytest.raises(ValueError,match='participation'):prepare(p)


def test_nonpositive_or_missing_participation_kept_unknown_not_DNP_or_inactive():
    p=parents();p[0]['rows'][0]['logs'][0]['positive_offensive_participation_proven']=False
    assert prepare(p)['actor_rows'][0]['participation']is None


def test_source_count_drift_or_future_alias_evidence_never_attaches():
    p=parents();p[0]['rows'][0]['logs'][0]['counts']['targets']=4
    with pytest.raises(ValueError,match='exposure differs'):prepare(p)
    p=parents();p[0]['rows'][0]['logs'][0]['source_ref']['native_alias_evidence'][0]['created_at']='2027-01-01T00:00:00Z';p[1]['rows'][0]['source_ref']=deepcopy(p[0]['rows'][0]['logs'][0]['source_ref'])
    with pytest.raises(ValueError,match='alias evidence'):prepare(p)


def test_field_reader_queries_only_frozen_original_ids_with_bounded_statement():
    from backend.app.product_services.shared_pair_source import read_exact_td_revision
    old,new=source();calls=[]
    class Result:
        def mappings(self):return [new]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):
            calls.append((str(sql),params))
            return Result()
    class Engine:
        def connect(self):return Connection()
    r=read_exact_td_revision(Engine(),[old],cutoff='2026-10-20T00:02:00Z')
    assert calls[1][1]['ids']==['id1']and'receiving_tds'in calls[1][1]['fields']
    assert 'statement_timeout'in calls[0][0]and r['rows'][0]['raw_row_json']['receiving_tds']==0
    assert r['actual_fields_read_started_at']=='2026-10-20T00:02:00+00:00'


def test_frozen_attachment_incident_preserves_existing_resolved_case_identity():
    from backend.app.product_services.shared_pair_source import persist_pair_identity_requests
    from backend.app.product_services.shared_scoring_pair_covariance import VERSION as PAIR_VERSION
    from backend.app.product_services.evaluation_record import digest
    case=dict(identity_quarantine_id='real-prior-case',source_table='player_alias',source_record_key='shared-pair-frozen-identity:nflreadpy:'+N+':'+digest([]),source_player_key=N,status='resolved',first_seen_at='old',updated_at='same')
    features=dict(version=PAIR_VERSION,pregame_serving_eligible=False,identity_review_requests=[dict(source_system='nflreadpy',source_key=N,reason='frozen_pair_attachment_unavailable',evidence=dict(original_alias_evidence=[]),game_id=G,team='BUF')])
    class Result:
        def mappings(self):return [deepcopy(case)]
    class Connection:
        def execute(self,sql,params):
            if str(sql).lstrip().startswith('SELECT'):return Result()
            assert 'DO NOTHING'in str(sql)and'UPDATE'not in str(sql)
    q=persist_pair_identity_requests(Connection(),features,source_refs=[])
    assert q['created_new']==0 and q['existing_unchanged']==1 and q['records'][0]['identity_quarantine_id']=='real-prior-case'


def test_typed_raw_zero_cannot_be_replaced_by_boolean_false_as_equal_projection():
    old,new=source();new['raw_row_json']['targets']=False
    with pytest.raises(ValueError,match='projection changed'):
        validate_td_revision([new],[old],cutoff='2026-10-20T00:02:00Z')


def test_field_revision_keeps_full_5501_row_identity_scope_in_two_bounded_queries():
    from backend.app.product_services.shared_pair_source import read_exact_td_revision
    old,new=source();original=[];rows={}
    for i in range(5501):
        a=deepcopy(old);a['source_id']=str(i);original.append(a)
        b=deepcopy(new);b['source_id']=str(i);rows[str(i)]=b
    calls=[]
    class Result:
        def __init__(self,data):self.data=data
        def mappings(self):return self.data
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):
            if params is None:return Result([])
            calls.append(params['ids']);assert len(params['ids'])<=3000
            return Result([rows[k]for k in params['ids']])
    class Engine:
        def connect(self):return Connection()
    r=read_exact_td_revision(Engine(),original,cutoff='2026-10-20T00:02:00Z')
    assert len(r['rows'])==5501 and list(map(len,calls))==[3000,2501]
    assert {k for batch in calls for k in batch}==set(rows)
    with pytest.raises(ValueError,match='Bounded'):
        read_exact_td_revision(Engine(),original+[dict(original[0],source_id=str(i))for i in range(5501,6001)],cutoff='2026-10-20T00:02:00Z')
