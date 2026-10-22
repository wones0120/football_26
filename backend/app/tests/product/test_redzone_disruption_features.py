from copy import deepcopy
import pytest
from backend.app.product_services.redzone_disruption_features import build_redzone_disruption_features,DEF_VERSION,OFF_VERSION,FUMBLE_VERSION
S=dict(snapshot_id='snapshot',content_sha256='a'*64)

def inputs():
 event=dict(game_id='2025_08_SF_WAS',play_id='1',offense='SF',status='counted',dropback=True,official_pass=True,sack=False,interception=False)
 defense=dict(version=DEF_VERSION,before_period=202509,evidence_use='postlock_descriptive_not_pregame_or_serving',provenance=dict(event_receipt_sha256='events',source=S),event_basis=[event])
 offense=dict(version=OFF_VERSION,before_period=202509,evidence_use='postlock_descriptive_not_pregame_or_serving',source_event_sha256='events',source=S,game_rows=[dict(game_id=event['game_id'],events=[dict(play_id='1',channels=[dict(channel='pass',official_eligibility=True),dict(channel='rush',official_eligibility=False)])])])
 fumbles=dict(version=FUMBLE_VERSION,before_period=202509,evidence_use='postlock_descriptive_not_pregame_or_serving',provenance=dict(source=S),event_basis=[dict(game_id=event['game_id'],play_id='1',eligible=True,fumble_play=False)],fumble_ledger=[])
 raw=[dict(game_id=event['game_id'],play_id='1',posteam='SF',season='2025',week='8',season_type='REG',yardline_100='20')]
 return defense,offense,fumbles,raw

def run(d=None,o=None,f=None,r=None):
 a,b,c,z=inputs();return build_redzone_disruption_features(d or a,o or b,f or c,r or z,before_period=202509,raw_source=S)['game_rows'][0]

def proof(owner='SF',lost=True):return dict(game_id='2025_08_SF_WAS',play_id='1',source_conflict=False,reported_fumblers=[dict(team=owner)],lost_from_fumbler_team=lost)

def test_separate_rz_rates_and_boundary():
 d,o,f,r=inputs();d['event_basis'][0]['sack']=True
 m=run(d,o,f,r)['metrics'];assert m['sack_per_dropback']['value']==1 and m['interception_per_pass']['value']==0

def test_unknown_yardline_masks_no_completecase():
 d,o,f,r=inputs();r[0]['yardline_100']=None
 assert run(d,o,f,r)['metrics']['sack_per_dropback']['unknown_exposures']==1

def test_known_outside_zone_excluded_not_missing():
 d,o,f,r=inputs();r[0]['yardline_100']='21'
 m=run(d,o,f,r)['metrics']['sack_per_dropback'];assert m['known_exposures']==0 and m['value'] is None

def test_opponent_return_fumbler_not_original_offense_loss():
 d,o,f,r=inputs();d['event_basis'][0]['interception']=True;f['event_basis'][0]['fumble_play']=True;f['fumble_ledger']=[proof('WAS')]
 m=run(d,o,f,r)['metrics'];assert m['offense_fumble_loss_per_snap']['value']==0 and m['turnover_event_per_snap']['value']==1

def test_original_fumbler_loss_and_int_or_once():
 d,o,f,r=inputs();d['event_basis'][0]['interception']=True;f['event_basis'][0]['fumble_play']=True;f['fumble_ledger']=[proof()]
 m=run(d,o,f,r)['metrics'];assert m['offense_fumble_loss_per_snap']['value']==1 and m['turnover_event_per_snap']['known_events']==1

def test_multi_fumbler_recovery_never_zipped():
 d,o,f,r=inputs();f['event_basis'][0]['fumble_play']=True;q=proof();q['reported_fumblers'].append(dict(team='WAS'));f['fumble_ledger']=[q]
 assert run(d,o,f,r)['metrics']['offense_fumble_loss_per_snap']['value'] is None

def test_missing_recovery_not_zero():
 d,o,f,r=inputs();f['event_basis'][0]['fumble_play']=True;f['fumble_ledger']=[proof(lost=None)]
 assert run(d,o,f,r)['metrics']['turnover_event_per_snap']['value'] is None

def test_nonphysical_return_event_not_offensive_snap():
 d,o,f,r=inputs();d['event_basis'][0].update(dropback=False,official_pass=False,status='not_applicable');o['game_rows'][0]['events']=[];f['event_basis'][0]['fumble_play']=True;f['fumble_ledger']=[proof()]
 assert run(d,o,f,r)['metrics']['offense_fumble_loss_per_snap']['known_exposures']==0

@pytest.mark.parametrize('kind',['snapshot','event','native','future'])
def test_binding_guards(kind):
 d,o,f,r=deepcopy(inputs())
 if kind=='snapshot':f['provenance']['source']['content_sha256']='b'*64
 if kind=='event':o['source_event_sha256']='different'
 if kind=='native':r[0]['posteam']='WAS'
 if kind=='future':r[0]['week']='9'
 with pytest.raises(ValueError):run(d,o,f,r)

def test_component_publication_clock_not_backdated():
 from backend.app.product_services.redzone_disruption_features import _available_at
 with pytest.raises(ValueError):_available_at({},'2026-10-20T00:00:00Z')
 with pytest.raises(ValueError):_available_at(dict(actual_publication_at='2026-10-21T00:00:00Z'),'2026-10-20T00:00:00Z')
 _available_at(dict(actual_publication_at='2026-10-19T00:00:00Z'),'2026-10-20T00:00:00Z')

def test_descriptive_use_guard():
 from backend.app.product_services.redzone_disruption_features import require_feature_use
 d,o,f,r=inputs();value=build_redzone_disruption_features(d,o,f,r,before_period=202509,raw_source=S)
 assert require_feature_use(value,purpose='offline_descriptive') is value
 with pytest.raises(ValueError):require_feature_use(value,purpose='forecast')
