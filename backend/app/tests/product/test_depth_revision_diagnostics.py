from copy import deepcopy
import pytest
from backend.app.product_services.observed_depth_changes import build_observed_depth_changes
from backend.app.product_services.depth_revision_diagnostics import build_depth_revision_diagnostics
from backend.app.product_services.evaluation_record import digest

def source():
 rows=[]
 for day,rank in [(17,'1'),(18,'3')]:rows.append(dict(snapshot_id=str(day),season=2026,week=6,teams=['SF'],observed_at=f'2026-10-{day}T09:00:00Z',captured_at=f'2026-10-{day}T10:00:00Z',rows=[dict(team='SF',gsis_id='00-0031234',pos_abb='KR',pos_slot='5',pos_rank=rank,dt=f'2026-10-{day}T08:00:00Z')]))
 d=build_observed_depth_changes(rows,{},season=2026,week=6,cutoff='2026-10-20T01:00:00Z');d['provenance']['actual_derived_at']='2026-10-20T01:00:00Z';return d

def bind(d):d['semantic_sha256']=digest({k:d[k] for k in ('version','season','week','comparisons','unkeyed_source_roles')})
def build(d):return build_depth_revision_diagnostics(d,cutoff='2026-10-20T02:00:00Z')

def test_separate_units_and_original_sources():
 d=source();r=build(d);u=r['rows'][0]['units'];assert u['special_teams']['absolute_rank_delta_sum']==2 and u['special_teams']['rank_revision_frequency']==1
 assert u['non_special_teams']['rank_revision_frequency'] is None
 assert r['original_source_refs']==d['provenance']['sources'] and r['forecast'] is None

def test_unknown_masks_exact_not_sample():
 d=source();r=deepcopy(d['comparisons'][0]['matched_roles'][0]);r['rank_delta']=None;d['comparisons'][0]['matched_roles'].append(r);bind(d)
 u=build(d)['rows'][0]['units']['all_literal_roles'];assert u['rank_revision_frequency'] is None and u['known_sample_rank_revision_frequency']==1

def test_zero_revision_is_known_zero():
 d=source();d['comparisons'][0]['matched_roles'][0]['rank_delta']=0;bind(d)
 assert build(d)['rows'][0]['units']['all_literal_roles']['absolute_rank_delta_sum']==0

def test_presence_not_rank_change():
 d=source();d['comparisons'][0]['newly_observed_roles']=[dict(unit='non_special_teams')];bind(d)
 u=build(d)['rows'][0]['units'];assert u['non_special_teams']['new_source_roles']==1 and u['non_special_teams']['rank_revision_count']==0

@pytest.mark.parametrize('kind',['hash','clock','order'])
def test_guards(kind):
 d=source()
 if kind=='hash':d['comparisons'][0]['matched_roles'][0]['rank_delta']=7
 if kind=='clock':d['provenance']['actual_derived_at']='2026-10-21T01:00:00Z'
 if kind=='order':d['provenance']['sources'][0]['captured_at']='2026-10-19T01:00:00Z'
 with pytest.raises(ValueError):build(d)
