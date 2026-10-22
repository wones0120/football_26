"""Read-only new rushing-TD allocation bindings from reviewed managed parents."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,UTC
import hashlib,json
from .factual_designation import clock
from .shared_scoring_pair_covariance import VERSION as PAIR_VERSION,_count
from .active_workload_distributions import VERSION as ACTIVE_VERSION


def prepare_rushing_actor_rows(pair,active):
    if pair.get('version')!=PAIR_VERSION or pair.get('pregame_serving_eligible')is not False or active.get('version')!=ACTIVE_VERSION or active.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving source parents required')
    logs={}
    for a in active['rows']:
        for log in a['logs']:
            key=str(log['source_ref']['source_id'])
            if key in logs:raise ValueError('Unique original source actor row required')
            logs[key]=(a,log)
    rows=[]
    for row in pair['provenance']['source_actor_rows']:
        key=str(row['source_ref']['source_id']);actor,log=logs[key]
        if log['source_ref']!=row['source_ref']or(actor['source_player_id'],actor['team'],actor['player_master_id'],log['native_game_id'])!=(row['native_GSIS'],row['team'],row['player_master_id'],row['game_id']):raise ValueError('Same original native game/identity/source receipt required')
        if row['source_position']=='QB'and row.get('source_role_proven')is not True:raise ValueError('Source-proven QB role required')
        if row['participation']is True and log['positive_offensive_participation_proven']is not True:raise ValueError('Original positive participation proof differs')
        rows.append({**deepcopy(row),'official_rush_attempts':_count(log['counts']['rush_attempts'])})
    return rows


def read_managed_parent(ref,folder,*,cutoff,max_bytes=16*1024*1024):
    boundary=clock(cutoff)
    if boundary is None or boundary>datetime.now(UTC):raise ValueError('Actual nonfuture cutoff required')
    p=Path(ref['path']);raw=p.read_bytes()
    if p.resolve().parent!=Path(folder).resolve()or p.stem!=ref['sha256']or len(raw)!=ref['bytes']or len(raw)>max_bytes or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Exact managed source bytes required')
    v=json.loads(raw);prov=v['provenance']
    if v.get('pregame_serving_eligible')is not False or clock(prov['actual_publication_at'])is None or clock(prov['actual_publication_at'])>boundary:raise ValueError('Published nonserving parent required')
    producers=prov.get('producer_code_hashes')
    if producers is None:producers=prov.get('producer_code_hashes',{})
    if prov.get('producer_code_sha256'):producers={**producers,'backend/app/product_services/'+('active_workload_distributions'if v['version']==ACTIVE_VERSION else'scoring_share_components')+'.py':prov['producer_code_sha256']}
    if not producers:raise ValueError('Reviewed producer bindings required')
    for name,sha in producers.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:raise ValueError('Reviewed producer changed')
    return v
