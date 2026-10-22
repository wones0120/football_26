from copy import deepcopy
import pytest
from backend.app.product_services.target_zone_allocation import build_target_zone_allocation,ZONE_VERSION,END_VERSION,USE


def source():
    common=dict(game_id='2025_01_SF_WAS',team='SF')
    metric=dict(counted_lower_bound=2,exact_within_log_count=2)
    zones=dict(version=ZONE_VERSION,before_period=202502,evidence_use=USE,pregame_serving_eligible=False,
        provenance=dict(source=dict(snapshot_id='snapshot',content_sha256='sha'),event_receipt_sha256='events'),
        full_team_denominators=[dict(common,channels=dict(targets=dict(inside5=metric)))],
        actor_game_rows=[dict(common,source_player_id='native',player_master_id='uuid',metrics={'G11-M06':metric})])
    end=dict(version=END_VERSION,before_period=202502,evidence_use=USE,pregame_serving_eligible=False,
        source=dict(snapshot_id='snapshot',content_sha256='sha'),source_event_sha256='events',
        team_game_rows=[dict(common,known_endzone_targets=1,value=1)],
        actor_game_rows=[dict(common,source_player_id='native',player_master_id='uuid',known_endzone_targets=1,value=1)])
    return deepcopy(zones),deepcopy(end)


def run(z=None,e=None):
    a,b=source();return build_target_zone_allocation(z or a,e or b,before_period=202502)


def test_overlapping_budgets_and_share_difference():
    r=run();assert r['actor_game_rows'][0]['endzone_minus_inside5_share']==0
    assert r['team_game_rows'][0]['channels']['inside5']['known_full_team_count']==2


def test_known_zero_actor_with_positive_team_denominator():
    z,e=source();z['actor_game_rows'][0]['metrics']['G11-M06']=dict(counted_lower_bound=0,exact_within_log_count=0)
    r=run(z,e)['actor_game_rows'][0];assert r['channels']['inside5']['share']==0 and r['endzone_minus_inside5_share']==1


def test_empty_denominator_undefined_not_zero_share():
    z,e=source();e['team_game_rows'][0].update(known_endzone_targets=0,value=0);e['actor_game_rows'][0].update(known_endzone_targets=0,value=0)
    assert run(z,e)['actor_game_rows'][0]['endzone_minus_inside5_share'] is None


def test_unknown_channel_budget_masks_comparison_keeps_lower_counts():
    z,e=source();e['team_game_rows'][0]['value']=None
    r=run(z,e)['actor_game_rows'][0];assert r['channels']['endzone']['known_actor_count']==1 and r['endzone_minus_inside5_share'] is None


def test_unattributed_residual_not_donated():
    z,e=source();z['actor_game_rows'][0]['metrics']['G11-M06']=dict(counted_lower_bound=1,exact_within_log_count=None)
    r=run(z,e);assert r['actor_game_rows'][0]['channels']['inside5']['share'] is None
    assert r['team_game_rows'][0]['channels']['inside5']['unattributed_known_count']==1


@pytest.mark.parametrize('kind',['event','source','period','use','duplicate','identity','budget'])
def test_scope_identity_budget_rejections(kind):
    z,e=source()
    if kind=='event':e['source_event_sha256']='other'
    if kind=='source':e['source']['snapshot_id']='other'
    if kind=='period':e['before_period']=202503
    if kind=='use':e['pregame_serving_eligible']=True
    if kind=='population':e['actor_game_rows']=[]
    if kind=='duplicate':e['actor_game_rows']*=2
    if kind=='identity':e['actor_game_rows'][0]['player_master_id']='other'
    if kind=='budget':e['actor_game_rows'][0].update(known_endzone_targets=2,value=2)
    with pytest.raises(ValueError):run(z,e)


def test_reader_checks_reviewed_producer_publication_and_bytes(tmp_path,monkeypatch):
    import json,hashlib
    from pathlib import Path
    from backend.app.product_services import player_scoring_zone_components as zmod,endzone_target_components as emod
    from backend.app.product_services.target_zone_allocation import load_target_zone_allocation,require_feature_use
    z,e=source();monkeypatch.chdir(tmp_path)
    raw=tmp_path/'raw.csv';raw.write_text('source\n');sha=hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(dict(snapshot_id='snapshot',content_sha256=sha)))
    s=dict(snapshot_id='snapshot',content_sha256=sha,artifact_path=str(raw),manifest_path=str(manifest),**{k:'2000-01-01T00:00:00+00:00' for k in ('observed_at','captured_at','effective_at','received_at')})
    z['provenance']['source']=s;e['source']=s
    refs={}
    for name,value,module,folder in [('zones',z,zmod,'player_scoring_zone_components'),('endzone',e,emod,'endzone_target_components')]:
        value.setdefault('provenance',{}).update(actual_publication_at='2000-01-02T00:00:00+00:00',producer_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
        directory=tmp_path/'artifacts'/folder;directory.mkdir(parents=True);data=json.dumps(value).encode();h=hashlib.sha256(data).hexdigest();path=directory/(h+'.json');path.write_bytes(data);refs[name]=dict(path=str(path),sha256=h,bytes=len(data))
    result=load_target_zone_allocation(refs,actual_read_at='2000-01-03T00:00:00+00:00');assert result['actor_game_rows'][0]['endzone_minus_inside5_share']==0
    with pytest.raises(ValueError):require_feature_use(result,purpose='forecast')
    with pytest.raises(ValueError):load_target_zone_allocation(refs,actual_read_at='2000-01-01T00:00:00+00:00')
    Path(refs['zones']['path']).write_text('changed')
    with pytest.raises(ValueError):load_target_zone_allocation(refs,actual_read_at='2000-01-03T00:00:00+00:00')


def test_missing_actor_channel_keeps_union_and_unknown_not_zero():
    z,e=source();e['actor_game_rows']=[]
    r=run(z,e);assert len(r['actor_game_rows'])==1
    assert r['actor_game_rows'][0]['channels']['endzone']['known_actor_count'] is None
    assert r['actor_game_rows'][0]['endzone_minus_inside5_share'] is None
    assert r['team_game_rows'][0]['channels']['endzone']['unattributed_known_count'] is None


def test_unmapped_native_mass_is_not_unattributed_target_mass():
    z,e=source();z['actor_game_rows'][0]['player_master_id']=None;e['actor_game_rows'][0]['player_master_id']=None
    c=run(z,e)['team_game_rows'][0]['channels']['endzone']
    assert c['known_native_without_canonical_count']==1 and c['unattributed_known_count']==0
