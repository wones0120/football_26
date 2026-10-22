from copy import deepcopy
from backend.app.product_services.pfr_pressure_cohort import VERSION as SOURCE_VERSION
from backend.app.product_services.pfr_pressure_catalog import build_pressure_catalog,persist_pressure_identity_requests


def source():
    gs=[dict(game_id='2023_01_BUF_MIA',season=2023,week=1,offense='BUF',defense='MIA',known_dropbacks=10,known_pressure_lower_bound=2,pressure_rate=.2,full_observed_cohort_proven=True),dict(game_id='2023_02_BUF_NYJ',season=2023,week=2,offense='BUF',defense='NYJ',known_dropbacks=30,known_pressure_lower_bound=12,pressure_rate=.4,full_observed_cohort_proven=True)]
    return dict(version=SOURCE_VERSION,pregame_serving_eligible=False,game_rows=gs,native_GSIS_identity_proofs={},native_PFR_identity_proofs={},provenance=dict(official_dropback_cohort=dict(event_basis=[]),PFR_raw_actor_rows=[]))


def test_opposite_native_perspectives_share_one_pressure_count_not_extra_volume():
    r=build_pressure_catalog(source());g=r['game_rows'][0]
    assert g['metrics']['G13-M03']['value']==g['metrics']['G14-M01']['value']==.2
    assert g['offense']=='BUF'and g['defense']=='MIA'
    p=next(p for p in r['profiles']if p['team']=='BUF'and p['catalog_id']=='G13-M03')
    assert p['value']==14/40 and p['value']!=(.2+.4)/2


def test_unknown_game_masks_full_pool_known_complete_sample_retained():
    s=source();s['game_rows'][1].update(full_observed_cohort_proven=False,pressure_rate=None)
    r=build_pressure_catalog(s);p=next(p for p in r['profiles']if p['team']=='BUF'and p['catalog_id']=='G13-M03')
    assert p['value']is None and p['known_complete_sample_rate']==.2 and p['unknown_games']==1
    assert r['game_rows'][1]['metrics']['G13-M03']['exact_pressure_count']is None


def test_zero_dropbacks_undefined_rate_and_no_hidden_imputation():
    s=source();s['game_rows']=s['game_rows'][:1];s['game_rows'][0].update(known_dropbacks=0,known_pressure_lower_bound=0,pressure_rate=None)
    r=build_pressure_catalog(s)
    assert all(p['value']is None for p in r['profiles'])
    assert not r['pregame_serving_eligible']and r['forecast']is None


def test_existing_resolved_native_case_preserved_id_and_clocks():
    s=source();s['native_PFR_identity_proofs']={'Missing00':dict(player_master_id=None,status='unresolved_native_key',original_alias_evidence=[])};s['provenance']['PFR_raw_actor_rows']=[dict(pfr_player_id='Missing00',game_id='2023_01_BUF_MIA',team='BUF')]
    r=build_pressure_catalog(s)
    old=dict(identity_quarantine_id='real-old-id',source_table='source_snapshot',source_record_key='pfr-player:Missing00',source_player_key='Missing00',status='resolved',first_seen_at='first',updated_at='unchanged')
    class Result:
        def mappings(self):return [deepcopy(old)]
    class Connection:
        def execute(self,sql,params):
            if str(sql).lstrip().startswith('SELECT'):return Result()
            assert 'DO NOTHING'in str(sql)and'UPDATE'not in str(sql)
    q=persist_pressure_identity_requests(Connection(),r,source_refs=[])
    assert q['created_new']==0 and q['existing_unchanged']==1 and q['records'][0]['identity_quarantine_id']=='real-old-id'
