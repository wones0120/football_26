from copy import deepcopy
import pytest
from backend.app.product_services.provider_pressure_scramble import build_provider_pressure_scrambles
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.product_services.participation_defense_catalog import build_participation_defense_catalog
from backend.app.tests.product.test_offensive_line_participation import source,snap,native,gid


def fixture():
 rows=[snap(1,number=n,passer_player_id=native(6),rusher_player_id=native(6)if n==101 else None,qb_scramble=int(n==101),rush_attempt=int(n==101),pass_attempt=int(n!=101),qb_spike=0,play_type='run'if n==101 else'pass',play_type_nfl='RUSH'if n==101 else'PASS')for n in(100,101)]
 p=normalize_participation_rows([source(1,number=n,was_pressure=True)for n in(100,101)],season=2023)
 b=build_participation_defense_catalog(p,rows,before_period=202319)
 return b,p,rows


def run(x=None):return build_provider_pressure_scrambles(*(x or fixture()))
def qb(x):return x['game_rows'][0]


def test_same_event_provider_pressure_denominator_and_same_QB_scramble():
 x=run();r=qb(x);assert r['known_pressured_dropbacks']==2 and r['known_same_QB_scrambles']==1 and r['scramble_fraction']==.5
 assert r['source_role']=='QB' and x['pregame_serving_eligible']is False


def test_no_scramble_implies_pressure_or_rounded_vendor_fraction():
 b,p,rows=fixture();b['event_basis'][1]['native_pressure']=False
 r=qb(run((b,p,rows)));assert r['known_pressured_dropbacks']==1 and r['scramble_fraction']==0
 b['event_basis'][0]['native_pressure']=False
 r=qb(run((b,p,rows)));assert r['known_pressured_dropbacks']==0 and r['scramble_fraction']is None

@pytest.mark.parametrize('field',['native_pressure','eligible_nonspike_dropback'])
def test_unknown_membership_keeps_lower_count_not_full_ratio(field):
 x=fixture();x[0]['event_basis'][1][field]=None;r=qb(run(x))
 assert r['known_pressured_dropbacks']==1 and r['unknown_pressured_membership']==1 and r['scramble_fraction']is None


def test_scramble_missing_retains_known_pressure_denominator_and_unknown_numerator():
 b,p,rows=fixture();rows[1]['qb_scramble']=None
 r=qb(run((b,p,rows)));assert r['known_pressured_dropbacks']==2 and r['unknown_scramble_outcomes']==1 and r['scramble_fraction']is None


def test_unknown_scramble_different_passer_rusher_not_priority_alias():
 b,p,rows=fixture();rows[1].update(qb_scramble=None,rusher_player_id=native(9))
 x=run((b,p,rows));assert qb(x)['unknown_pressured_membership']==1
 assert x['unassigned_QB_residual'][0]['unknown_other_candidates']is True


def test_scramble_nonrush_contradiction_is_unknown_outcome():
 x=fixture();x[2][1]['rush_attempt']=0
 r=qb(run(x));assert r['unknown_scramble_outcomes']==1 and r['scramble_fraction']is None

@pytest.mark.parametrize('change',['side','role','eleven','phase','missing'])
def test_unproven_QB_event_proof_masks_existing_actor_and_preserves_residual(change):
 b,p,rows=fixture();part=p['rows'][1]
 if change=='side':part['possession_team']='MIA'
 elif change=='role':part['participant_scopes']['offense']['position_by_native_id'][native(6)]='WR'
 elif change=='eleven':part['participant_scopes']['offense']['native_player_ids'].pop()
 elif change=='phase':part['native_phase']='POST'
 else:p['rows'].pop()
 x=run((b,p,rows));assert qb(x)['scramble_fraction']is None
 assert len(x['unassigned_QB_residual'])==1


def test_missing_offense_never_creates_QB_actor_on_both_teams():
 b,p,rows=fixture();rows[1]['posteam']=None;b['event_basis'][1]['offense']=None
 x=run((b,p,rows));assert len(x['game_rows'])==1 and x['game_rows'][0]['team']=='BUF'
 assert qb(x)['unknown_pressured_membership']==1


def test_sack_false_pressure_basis_conflict_remains_unknown_not_OR_repaired():
 b,p,rows=fixture();b['event_basis'][0].update(native_pressure=None,pressure_sack_conflict=True)
 x=run((b,p,rows));assert qb(x)['scramble_fraction']is None and x['event_basis'][0]['source_pressure_sack_conflict']is True


def test_universe_includes_unproven_potential_raw_rusher():
 x=fixture();x[2][1]['rusher_player_id']=native(80);out=run(x)
 assert native(80)in out['native_identity_universe'] and out['unassigned_QB_residual']

@pytest.mark.parametrize('bad',['missingraw','duplicate','side','period','version','name'])
def test_native_source_scope_rejects(bad):
 x=fixture()
 if bad=='missingraw':x[2].pop()
 if bad=='duplicate':x[2].append(deepcopy(x[2][0]))
 if bad=='side':x[2][1]['posteam']='MIA'
 if bad=='period':x[2][1]['week']=2
 if bad=='version':x[0]['version']='other'
 if bad=='name':x[2][1]['rusher_player_id']='A Quarterback'
 with pytest.raises(ValueError):run(x)


def test_reported_passer_rusher_conflict_cannot_certify_same_QB_scramble():
 x=fixture();x[2][1]['passer_player_id']=native(8);out=run(x)
 assert out['event_basis'][1]['reported_QB_identity_conflict']is True
 assert qb(out)['scramble_fraction']is None


def test_missing_opposing_side_masks_pressure_condition():
 x=fixture();x[0]['event_basis'][1]['defense']=None
 r=qb(run(x));assert r['unknown_pressured_membership']==1 and r['scramble_fraction']is None


def test_identity_graph_withholds_all_candidate_edges_and_all_periods():
 from backend.app.product_services.provider_pressure_scramble import attach_pressure_identity
 from backend.app.tests.product.test_offensive_line_participation import aliases,NOW
 from uuid import UUID
 b=run();universe=set(b['native_identity_universe'])|{native(80)};a=aliases([6,80]);a[1]['player_master_id']=str(UUID(int=6))
 # Ambiguous QB A->{6,7}; B->{6} must also be withheld.
 a.append({**a[0],'alias_id':99,'player_master_id':str(UUID(int=7))})
 x=attach_pressure_identity([b],a,cutoff=NOW,identity_universe=universe)[0]
 assert x['identity_receipts'][native(80)]['player_master_id']is None
 assert x['game_rows'][0]['canonical_qualified_scramble_fraction']is None
 assert x['game_rows'][0]['scramble_fraction']==.5 and x['identity_review_requests']


def test_global_identity_universe_must_include_unproven_raw_candidates():
 from backend.app.product_services.provider_pressure_scramble import attach_pressure_identity
 from backend.app.tests.product.test_offensive_line_participation import aliases,NOW
 b=run();needed=set(b['native_identity_universe']);needed.remove(native(6))
 with pytest.raises(ValueError):attach_pressure_identity([b],aliases([]),cutoff=NOW,identity_universe=needed)

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future','serving'])
def test_managed_native_basis_reader_binds_producers_semantics_clocks(tmp_path,monkeypatch,change):
 from pathlib import Path
 import json,hashlib
 from backend.app.product_services.provider_pressure_scramble import load_reviewed_pressure_basis
 from backend.app.product_services import participation_defense_catalog,participation_source_components,fumble_event_components
 monkeypatch.chdir(tmp_path);x=fixture()[0]
 x['provenance'].update(actual_publication_at='2026-10-19T01:00:00Z',**{k:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()for k,m in(('producer_code_sha256',participation_defense_catalog),('source_adapter_sha256',participation_source_components),('eligibility_helper_sha256',fumble_event_components))})
 if change=='semantic':x['event_basis'][0]['native_pressure']=False
 if change=='producer':x['provenance']['producer_code_sha256']='b'*64
 if change=='future':x['provenance']['actual_publication_at']='2026-10-21T01:00:00Z'
 if change=='serving':x['pregame_serving_eligible']=True
 b=json.dumps(x,sort_keys=True).encode();h=hashlib.sha256(b).hexdigest();p=Path('artifacts/participation_defense_catalog')/(h+'.json');p.parent.mkdir(parents=True);p.write_bytes(b);ref=dict(path=str(p.resolve()),sha256=h,bytes=len(b))
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_pressure_basis(ref,cutoff='2026-10-20T10:00:00Z')
 else:assert load_reviewed_pressure_basis(ref,cutoff='2026-10-20T10:00:00Z')['semantic_sha256']==x['semantic_sha256']


def test_frozen_attachment_queue_is_append_only_evidence_specific_not_alias_repair():
 from backend.app.product_services.provider_pressure_scramble import attach_pressure_identity,persist_pressure_identity_requests
 from backend.app.tests.product.test_offensive_line_participation import NOW
 b=run();x=attach_pressure_identity([b],[],cutoff=NOW,identity_universe=set(b['native_identity_universe']))
 class Connection:
  def __init__(self):self.calls=[]
  def execute(self,sql,args):self.calls.append((str(sql),args))
 c=Connection();a=persist_pressure_identity_requests(c,x,source_refs=[{'sha256':'a'*64}]);again=persist_pressure_identity_requests(c,x,source_refs=[{'sha256':'a'*64}])
 assert a==again and a['requests']==1
 assert all('ON CONFLICT' in sql and 'DO NOTHING'in sql and 'UPDATE 'not in sql and 'player_alias'not in sql for sql,args in c.calls)
 assert c.calls[0][1]['native']==native(6) and 'pressure-frozen-attachment'in c.calls[0][1]['key']
