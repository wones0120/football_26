"""Source revision diagnostics in literal rank and presence units."""
from copy import deepcopy
from datetime import datetime,UTC
from .observed_depth_changes import VERSION as DEPTH_VERSION
from .factual_designation import clock
from .evaluation_record import digest

VERSION='observed_depth_revision_diagnostics_v1'


def build_depth_revision_diagnostics(depth,*,cutoff):
    if depth.get('version')!=DEPTH_VERSION or depth.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Reviewed descriptive depth contract required')
    decision=clock(cutoff)
    if decision>datetime.now(UTC) or clock(depth['provenance']['actual_derived_at'])>decision:raise ValueError('Depth input unavailable')
    basis={k:depth[k] for k in ('version','season','week','comparisons','unkeyed_source_roles')}
    if depth['semantic_sha256']!=digest(basis):raise ValueError('Depth semantic binding differs')
    sources={s['snapshot_id']:s for s in depth['provenance']['sources']}
    rows=[]
    for c in depth['comparisons']:
        previous,current=(sources[c[k]] for k in ('prior_snapshot_id','current_snapshot_id'))
        if clock(previous['captured_at'])>=clock(current['captured_at']) or clock(current['captured_at'])>decision:raise ValueError('Source revision chronology differs')
        summaries={}
        for unit in ('all_literal_roles','non_special_teams','special_teams'):
            matched=[r for r in c['matched_roles'] if unit=='all_literal_roles' or r['unit']==unit]
            known=[r['rank_delta'] for r in matched if r['rank_delta'] is not None];unknown=len(matched)-len(known)
            count=sum(d!=0 for d in known);magnitude=sum(abs(d) for d in known)
            summaries[unit]=dict(matched_roles=len(matched),known_delta_roles=len(known),unknown_delta_roles=unknown,
                rank_revision_count=count if not unknown else None,known_rank_revision_count=count,
                rank_revision_frequency=count/len(matched) if matched and not unknown else None,
                known_sample_rank_revision_frequency=count/len(known) if known else None,
                absolute_rank_delta_sum=magnitude if matched and not unknown else None,known_absolute_rank_delta_sum=magnitude if known else None,
                new_source_roles=sum(unit=='all_literal_roles' or r['unit']==unit for r in c['newly_observed_roles']),
                not_observed_source_roles=sum(unit=='all_literal_roles' or r['unit']==unit for r in c['not_observed_roles']))
        rows.append(dict(teams=deepcopy(c['teams']),prior_snapshot_id=c['prior_snapshot_id'],current_snapshot_id=c['current_snapshot_id'],units=summaries))
    basis=dict(version=VERSION,candidate_id='X08-M07',source_domain='provider_literal_depth_roles',rows=rows,
        original_source_refs=[deepcopy(s) for s in depth['provenance']['sources']],unkeyed_source_roles=deepcopy(depth['unkeyed_source_roles']),
        limitations=['Rank and source-presence units remain separate; no numeric sum across them','Unkeyed native roles outside matched-role estimand remain explicit; no exhaustive football revision claim','Not forecast or role-persistence change, no imputation'])
    return basis|dict(semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False)
