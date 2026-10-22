from copy import deepcopy
import pytest
from backend.app.product_services.offensive_scoring_drive_catalog import build_offensive_scoring_drive_catalog
from backend.app.product_services.drive_volume_catalog import build_drive_volume_catalog
from backend.app.product_services.offensive_redzone_stalls import build_offensive_redzone_stalls
from backend.app.tests.product.test_drive_volume_catalog import source as drive_source
from backend.app.tests.product.test_redzone_drive_catalog import source as rz_source


def sources():
    lineage=dict(source=dict(snapshot_id='snapshot',content_sha256='raw-sha'),event_receipt_sha256='same-native-events')
    scoring=dict(version='scoring_share_components_v1',before_period=202606,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,semantic_sha256='scoring',provenance=deepcopy(lineage),team_game_rows=[dict(game_id='2026_01_WAS_SF',team='WAS',counts={'rushing_TD':dict(known_count=1,unknown_events=0),'passing_TD':dict(known_count=1,unknown_events=0)})])
    drives=build_drive_volume_catalog(drive_source(native_drive_ids=['1','2','3']),before_period=202606);drives['provenance']=dict(original_context_provenance=deepcopy(lineage))
    raw=rz_source();raw['provenance']=deepcopy(lineage);redzone=build_offensive_redzone_stalls(raw,before_period=202606)
    return scoring,drives,redzone

def build(s=None):return build_offensive_scoring_drive_catalog(*(s or sources()),before_period=202606)

def test_physical_passing_and_receivingTD_once_and_redzone_conversion():
    r=build();m=r['game_rows'][0]['metrics']
    assert m['G12-M01']['value']==2/3 and m['G12-M01']['numerator']['known_physical_TDs']==2
    assert m['G12-M06']['value']==.5 and m['G12-M06']['known_touchdown_drives']==1
    assert r['forecast'] is None and r['pregame_serving_eligible'] is False

@pytest.mark.parametrize('kind',['TD','drive','missing_TD','missing_drive','missing_RZ'])
def test_unknown_or_missing_source_not_zero_or_dropped(kind):
    a,b,c=sources()
    if kind=='TD':a['team_game_rows'][0]['counts']['passing_TD']['unknown_events']=1
    elif kind=='drive':b['game_rows'][0]['metrics']['G01-M02']['unknown_snap_eligibility']=1
    elif kind=='missing_TD':a['team_game_rows']=[]
    elif kind=='missing_drive':b['game_rows']=[]
    else:c['game_rows']=[]
    r=build((a,b,c));assert len(r['game_rows'])==1
    assert r['game_rows'][0]['metrics']['G12-M06' if kind=='missing_RZ' else 'G12-M01']['value'] is None


def test_zeroTD_measured_and_zero_drive_ratio_undefined():
    a,b,c=sources()
    for v in a['team_game_rows'][0]['counts'].values():v['known_count']=0
    g=c['game_rows'][0];g['metrics']['G23-M06'].update(value=1.,known_stall_drives=2,known_touchdown_drives=0)
    g['drive_outcomes'][0]['completion_basis']='provider_field_goal_terminal'
    assert build((a,b,c))['game_rows'][0]['metrics']['G12-M01']['value']==0
    d=b['game_rows'][0]['metrics']['G01-M02'];d.update(observed_native_drives=0,known_attached_snaps=0,known_physical_snaps=0);b['game_rows'][0]['native_drive_ids']=[];c['game_rows']=[]
    assert build((a,b,c))['game_rows'][0]['metrics']['G12-M01']['value'] is None

@pytest.mark.parametrize('kind',['lineage','future','duplicate','too_manyTD','terminal','TD_partition','subset_TD','drive_keys'])
def test_native_physical_and_source_guards(kind):
    a,b,c=sources()
    if kind=='lineage':c['provenance']['event_receipt_sha256']='different-events'
    elif kind=='future':a['team_game_rows'][0]['game_id']='2026_06_WAS_SF'
    elif kind=='duplicate':a['team_game_rows'].append(deepcopy(a['team_game_rows'][0]))
    elif kind=='too_manyTD':a['team_game_rows'][0]['counts']['passing_TD']['known_count']=3
    elif kind=='subset_TD':
        for v in a['team_game_rows'][0]['counts'].values():v['known_count']=0
    elif kind=='drive_keys':b['game_rows'][0]['native_drive_ids']=[1,8,9]
    elif kind=='terminal':c['game_rows'][0]['drive_outcomes'][0]['native_order_verified']=False
    else:c['game_rows'][0]['metrics']['G23-M06']['known_touchdown_drives']=2
    with pytest.raises(ValueError):build((a,b,c))


def test_unknown_RZ_terminal_masks_rate_not_known_sample_success():
    a,b,c=sources();g=c['game_rows'][0];m=g['metrics']['G23-M06'];m.update(value=None,known_stall_drives=0,known_terminal_outcomes=1,unknown_terminal_outcomes=1)
    g['drive_outcomes'][1].update(outcome_known=False,completion_basis='unknown_no_terminal_evidence')
    m=build((a,b,c))['game_rows'][0]['metrics']['G12-M06']
    assert m['value'] is None and m['known_terminal_sample_conversion']==1

@pytest.mark.parametrize('gid',['2026_01_SF_SF','2026_1_WAS_SF'])
def test_native_game_pair_and_period_spelling_are_unambiguous(gid):
    a,b,c=sources();a['team_game_rows'][0]['game_id']=gid
    with pytest.raises(ValueError):build((a,b,c))


def test_physical_rush_and_passTD_shares_complement_not_attempt_rates():
    m=build()['game_rows'][0]['metrics']
    assert m['G12-M02']['value']==.5 and m['G12-M03']['value']==.5
    assert m['G12-M02']['value']+m['G12-M03']['value']==1
    assert m['G12-M03']['exact_physical_offensive_TD_denominator']==2


def test_unknown_or_zero_physicalTD_denominator_has_no_donated_share():
    a,b,c=sources();a['team_game_rows'][0]['counts']['passing_TD']['unknown_events']=1
    m=build((a,b,c))['game_rows'][0]['metrics']
    assert m['G12-M02']['value'] is None and m['G12-M03']['value'] is None
    for v in a['team_game_rows'][0]['counts'].values():v.update(known_count=0,unknown_events=0)
    c['game_rows']=[]
    m=build((a,b,c))['game_rows'][0]['metrics']
    assert m['G12-M02']['value'] is None and m['G12-M03']['value'] is None
