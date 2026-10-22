"""Pure independent official-count reconciliation; no player identity guessing."""
from copy import deepcopy
from datetime import date
import re

FIELDS=('official_pass_attempts','official_carries','official_targets','physical_plays')

def _count(value):
    if type(value)is not int or value<0:raise ValueError('Explicit nonnegative integral source count required')
    return value

def reconcile(pbp,official,scope):
    gid=pbp['game_id'];parts=gid.split('_')
    if len(parts)!=4 or official['game_id']!=gid or scope['game_id']!=gid:raise ValueError('Exact native game identity required')
    season,week=int(parts[0]),int(parts[1]);teams=set(pbp['source_sides'])
    if (len(teams)!=2 or len(pbp['source_sides'])!=2 or teams!=set(official['teams'])
            or teams!=set(scope['teams']) or teams!=set(parts[2:])):raise ValueError('Exact native team scope required')
    if official['season']!=season or official['week']!=week or scope['season']!=season or scope['week']!=week:raise ValueError('Native season/week conflict')
    if official['game_date']!=scope['game_date'] or date.fromisoformat(official['game_date']).year!=season:raise ValueError('Document and native schedule date conflict')
    if (not pbp['metrics_admitted'] or not pbp['regulation_score_certified'] or not pbp['independently_completed']
            or pbp['overtime_rows_retained']!=0 or scope['native_quarters']!=[1,2,3,4]
            or scope['unknown_period_rows']!=0 or not scope['all_native_rows_retained']
            or not scope['unique_native_play_keys']):raise ValueError('Regulation-only scope not proven')
    if (official.get('reviewed_final_tables')is not True or not re.fullmatch(r'[a-f0-9]{64}',official.get('pdf_sha256',''))
            or not official.get('team_page') or not official.get('individual_page')):raise ValueError('Reviewed bound final tables required')
    for side,team in enumerate(pbp['source_sides']):
        if official['teams'][team]['final_score']!=pbp['regulation_scores'][side]:raise ValueError('Official final versus certified regulation score conflict')
    labels=[];evidence=[];conflicts=[]
    for side,team in enumerate(pbp['source_sides']):
        observed=official['teams'][team];values={field:_count(observed[field])for field in FIELDS}
        sacks=_count(observed['sacks']);completions=_count(observed['completions'])
        if (values['official_targets']>values['official_pass_attempts'] or completions>values['official_targets']
                or values['official_pass_attempts']+values['official_carries']+sacks!=values['physical_plays']):raise ValueError('Official count conservation conflict')
        targets=observed['receiving_target_rows']
        if not targets or sum(_count(v)for v in targets)!=values['official_targets']:raise ValueError('Complete receiving-table TAR total required')
        out={};proof={}
        for field in FIELDS:
            known=_count(pbp['known_production_sums_by_side'][side][field]);full=pbp['production_by_side'][side][field]
            unknown=pbp['unknown_production_play_ids_by_side'][side][field]
            if len(unknown)!=len(set(unknown)) or any(not isinstance(p,str)or not p.isdigit()for p in unknown):raise ValueError('Unique native unresolved play IDs required')
            if full is not None and (_count(full)!=known or unknown):raise ValueError('PBP full/partial/mask inconsistency')
            if full is None and not unknown:raise ValueError('Unexplained PBP count mask')
            total=values[field]
            conflict=(full is not None and full!=total)or not known<=total<=known+len(unknown)
            out[field]=None if conflict else total
            proof[field]=dict(pbp_full_value=full,pbp_known_partial_sum=known,pbp_unknown_native_play_ids=list(unknown),official_total=total,
                status='SOURCE_CONFLICT'if conflict else'INDEPENDENT_OFFICIAL_TOTAL_WITH_PBP_MASK_RETAINED'if full is None else'AGREEMENT')
            if conflict:conflicts.append(dict(team=team,field=field,**proof[field]))
        labels.append(out);evidence.append(proof)
    return dict(game_id=gid,source_sides=list(pbp['source_sides']),production_by_side=labels,count_source_evidence_by_side=evidence,
        conflicts=conflicts,original_pbp_record=deepcopy(pbp),official_evidence=deepcopy(official),native_scope_evidence=deepcopy(scope),
        label_definition='OFFICIAL_REGULATION_TEAM_P_R_T_PHYSICAL_COUNTS;GAMEBOOK_SOURCE_ALTERNATIVE_V1',
        original_pregame_availability=False,event_level_unknowns_resolved=False,activation=False)
