from copy import deepcopy
from pathlib import Path
import hashlib,json
import pytest
from backend.app.product_services.qb_teammate_rushing_td_source import prepare_rushing_actor_rows,read_managed_parent,PAIR_VERSION,ACTIVE_VERSION


def inputs():
    ref=dict(source_id='original',ingest_run_id='run',imported_at='2026-10-20T00:00:00Z');gid='2026_01_BUF_MIA';native='00-0000001';pid='00000000-0000-0000-0000-000000000001'
    row=dict(game_id=gid,team='BUF',native_GSIS=native,player_master_id=pid,source_position='QB',source_role_proven=True,source_ref=ref,participation=True)
    pair=dict(version=PAIR_VERSION,pregame_serving_eligible=False,provenance=dict(source_actor_rows=[row]))
    active=dict(version=ACTIVE_VERSION,pregame_serving_eligible=False,rows=[dict(source_player_id=native,player_master_id=pid,team='BUF',logs=[dict(source_ref=deepcopy(ref),native_game_id=gid,positive_offensive_participation_proven=True,counts=dict(rush_attempts=0))])])
    return pair,active


def test_original_carry_zero_distinct_from_missing_and_source_role_bound():
    p,a=inputs();assert prepare_rushing_actor_rows(p,a)[0]['official_rush_attempts']==0
    a['rows'][0]['logs'][0]['counts']['rush_attempts']=None
    assert prepare_rushing_actor_rows(p,a)[0]['official_rush_attempts']is None


@pytest.mark.parametrize('field',['native_game_id','source_ref','positive_offensive_participation_proven'])
def test_changed_original_scope_receipt_participation_rejected(field):
    p,a=inputs();a['rows'][0]['logs'][0][field]={'source_id':'changed'}if field=='source_ref'else False if field=='positive_offensive_participation_proven'else'2026_02_BUF_MIA'
    with pytest.raises((ValueError,KeyError)):prepare_rushing_actor_rows(p,a)


def test_QB_role_not_inferred_from_attempts():
    p,a=inputs();p['provenance']['source_actor_rows'][0]['source_role_proven']=False
    with pytest.raises(ValueError,match='QB role'):prepare_rushing_actor_rows(p,a)


def test_managed_parent_hash_producer_and_clock(tmp_path):
    producer=tmp_path/'producer.py';producer.write_text('# frozen');v=dict(version='test',pregame_serving_eligible=False,provenance=dict(actual_publication_at='2026-10-20T00:00:00Z',producer_code_hashes={str(producer):hashlib.sha256(producer.read_bytes()).hexdigest()}));raw=json.dumps(v).encode();sha=hashlib.sha256(raw).hexdigest();p=tmp_path/(sha+'.json');p.write_bytes(raw);ref=dict(path=str(p),sha256=sha,bytes=len(raw))
    assert read_managed_parent(ref,tmp_path,cutoff='2026-10-20T00:01:00Z')['version']=='test'
    with pytest.raises(ValueError,match='Published'):read_managed_parent(ref,tmp_path,cutoff='2026-10-19T00:01:00Z')
    producer.write_text('# drift')
    with pytest.raises(ValueError,match='producer changed'):read_managed_parent(ref,tmp_path,cutoff='2026-10-20T00:01:00Z')
    p.write_text('{}')
    with pytest.raises(ValueError,match='managed source'):read_managed_parent(ref,tmp_path,cutoff='2026-10-20T00:01:00Z')
