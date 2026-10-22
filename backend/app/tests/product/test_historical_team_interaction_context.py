from copy import deepcopy
from datetime import datetime,UTC,timedelta
import hashlib
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from backend.app.product_services.historical_team_interaction_context import load_historical_team_interaction_context,compose_historical_team_interactions
from backend.app.product_services.team_opportunity_matrix import RAW_FIELDS
from backend.app.tests.product.test_defense_context_evidence import play
from backend.app.tests.product.test_team_market_interactions import fixture


def record(number=1,week=1,**changes):
    row={k:None for k in RAW_FIELDS};row.update(play(number,week=week,game_id=f'2026_{week:02d}_WAS_SF',posteam='WAS',defteam='SF'))
    row.update(passer_player_id='00-0000001',receiver_player_id='00-0000002',rusher_player_id=None)
    row.update(changes);return row


def descriptor(tmp_path,rows):
    p=tmp_path/'original.parquet';pq.write_table(pa.Table.from_pylist(rows),p);raw=p.read_bytes()
    return dict(path=str(p),manifest=dict(url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet',
        received_at='2026-10-13T10:00:00Z',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))


def load(d,**kwargs):return load_historical_team_interaction_context(d,before_period=202606,cutoff=datetime.now(UTC),**kwargs)


def test_same_source_receipt_produces_fullteam_environment_and_official_counts(tmp_path):
    rows=[record(1),record(2,play_type='run',pass_attempt=0,rush_attempt=1,qb_kneel=1,qb_dropback=0)]
    r=load(descriptor(tmp_path,rows));e=r['environment'];o=r['official']
    assert e['provenance']['event_receipt_sha256']==o['provenance']['event_receipt_sha256']
    assert e['game_rows'][0]['known_offensive_snaps']==2
    assert o['full_team_denominators'][0]['measurements']['official_carries']['exact_within_log_count']==1
    assert o['actor_game_rows']==[] # No individual canonical/position attachment attempted.
    assert r['pregame_serving_eligible']is False and 'original' in r['provenance']['original_source_descriptor']['path']


def test_regular_prior_scope_and_native_controls_preserved_without_finalness(tmp_path):
    rows=[record(1),record(2,week=6),record(3,week=2,season_type='POST'),
        record(4,week=3,posteam=None,defteam=None,play_type=None,pass_attempt=0,rush_attempt=0,sack=0,qb_dropback=0,qb_spike=0,qb_kneel=0,qb_scramble=0,two_point_attempt=0,quarter_end=1)]
    # Arrow's schema follows the first row; ensure native optional field exists there too.
    rows[0]['quarter_end']=0
    r=load(descriptor(tmp_path,rows));p=r['provenance']
    assert (p['scoped_event_rows'],p['retained_controls'],p['excluded_not_REG_rows'],p['excluded_at_or_after_period'])==(1,1,1,1)
    assert r['environment']['provenance']['source']['full_game_coverage']=='unverified'


@pytest.mark.parametrize('kind',['byte_hash','byte_size','future_received','wrong_uri_year'])
def test_source_bytes_and_actual_receipt_clocks_are_not_markers(tmp_path,kind):
    d=descriptor(tmp_path,[record()])
    if kind=='byte_hash':d['manifest']['sha256']='0'*64
    elif kind=='byte_size':d['manifest']['bytes']+=1
    elif kind=='future_received':d['manifest']['received_at']=(datetime.now(UTC)+timedelta(days=1)).isoformat()
    else:d['manifest']['url']=d['manifest']['url'].replace('2026','2025')
    with pytest.raises(ValueError):load(d)


@pytest.mark.parametrize('kind',['duplicate','wrong_team','bad_native','wrong_season','unscoped_positive'])
def test_native_identity_and_administrative_scope_guards(tmp_path,kind):
    rows=[record()]
    if kind=='duplicate':rows.append(record(1,play_id=1.0))
    elif kind=='wrong_team':rows[0]['posteam']='GB'
    elif kind=='bad_native':rows[0]['passer_player_id']='a display name'
    elif kind=='wrong_season':rows[0]['season']=2025
    else:rows[0].update(posteam=None,play_type=None,quarter_end=1)
    with pytest.raises(ValueError):load(descriptor(tmp_path,rows))


def test_schema_and_bounds_reject_missing_native_fields(tmp_path):
    row=record();del row['sack'];d=descriptor(tmp_path,[row])
    with pytest.raises(ValueError,match='schema'):load(d)
    d=descriptor(tmp_path,[record()])
    with pytest.raises(ValueError,match='bound'):load(d,max_rows=0)


def test_historical_observed_continuous_responses_are_not_lagged_products(tmp_path):
    rows=[record(1,week=w,yards_gained=w) for w in range(1,6)]
    d=descriptor(tmp_path,rows);c=load(d);markets=fixture()[2];markets['before_period']=202606;markets['rows']=markets['rows'][:5]
    r=compose_historical_team_interactions(c,markets,reference_before_period=202604)
    assert r['version']=='historical_team_market_responses_v1'
    assert set(r['rows'][0]['metrics'])=={f'X01-M{i:02}' for i in range(1,9)}
    m=r['rows'][0]['metrics']['X01-M01']['observed_response']
    assert m['mean_response']==1 and m['population_covariance']==0 and m['known_paired_logs']==2
    assert r['pregame_serving_eligible']is False and r['forecast']is None
    assert r['cutpoints']['reference_before_period']==202604


def test_unknown_carry_eligibility_remains_unknown_after_source_derivation(tmp_path):
    c=load(descriptor(tmp_path,[record(1,week=w,rush_attempt=None) for w in range(1,6)]))
    markets=fixture()[2];markets['before_period']=202606;markets['rows']=markets['rows'][:5]
    r=compose_historical_team_interactions(c,markets,reference_before_period=202604)
    assert r['rows'][0]['metrics']['X01-M03']['observed_response']['mean_response']is None


def test_response_artifact_cannot_enter_existing_pregame_component_contract(tmp_path):
    from backend.app.product_services.player_opportunity_components import require_component_use
    c=load(descriptor(tmp_path,[record(1,week=w) for w in range(1,6)]))
    markets=fixture()[2];markets['before_period']=202606;markets['rows']=markets['rows'][:5]
    r=compose_historical_team_interactions(c,markets,reference_before_period=202604)
    with pytest.raises(ValueError,match='Postlock descriptive'):
        require_component_use(r,purpose='pregame')
