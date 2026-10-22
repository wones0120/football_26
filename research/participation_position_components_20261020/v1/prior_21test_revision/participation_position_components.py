"""Minimal shared native position evidence from immutable FTN participation bytes.

No canonical attachment, eligibility, routes or assigned coverage are inferred.
"""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import hashlib,json
from .participation_source_components import _int,_tokens,_measurement,URL
from .market_snapshots import canonical_team
from .factual_designation import clock
from .evaluation_record import digest

VERSION='participation_position_components_v1'
COLUMNS=('nflverse_game_id','play_id','season','week','season_type','possession_team','offense_players','offense_positions','defense_players','defense_positions','n_offense','n_defense','defense_man_zone_type','defense_coverage_type')
UNKNOWN_POSITIONS={'UNKNOWN','UNK','UNSPECIFIED','NA','N/A','?'}


def project_participation_positions(records,*,season,max_rows=60000):
    if type(season)is not int or not 2023<=season<=2025:raise ValueError('Declared historical2023–25 FTN source only; no current2026fallback')
    rows=[];seen=set();coverage=Counter()
    for ordinal,r in enumerate(records):
        if ordinal>=max_rows:raise ValueError('Native position projection row bound exceeded')
        gid=r.get('nflverse_game_id');parts=gid.split('_')if isinstance(gid,str)else[]
        if len(parts)!=4 or parts[0]!=str(season)or not parts[1].isdigit()or not 1<=int(parts[1])<=22 or canonical_team(parts[2])==canonical_team(parts[3]):raise ValueError('Native game/season identity required')
        play=_int(r.get('play_id'));key=(gid,str(play))
        if play<0 or key in seen:raise ValueError('Unique nonnegative native game/play key required')
        seen.add(key)
        if r.get('season')is not None and _int(r['season'])!=season or r.get('week')is not None and _int(r['week'])!=int(parts[1]):raise ValueError('Native supplied period contradicts game')
        offense=canonical_team(r['possession_team'])if r.get('possession_team')else None
        if offense is not None and offense not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Native possession team contradicts game')
        scopes={};issues=[]
        for side in ('offense','defense'):
            ids=_tokens(r.get(side+'_players'),ids=True);pos=_tokens(r.get(side+'_positions'),ids=False);count,error=_measurement(r.get('n_'+side),'n_'+side)
            aligned=ids is not None and pos is not None and len(ids)==len(pos)and(count is None or count==len(ids))and error is None
            valid_ids=ids is not None and(count is None or count==len(ids))and error is None
            known_labels=pos is not None and all(p not in UNKNOWN_POSITIONS for p in pos)
            status='aligned_native_position_list'if aligned else'unknown_or_mismatched_native_positions'
            scopes[side]=dict(status=status,native_player_ids=ids if valid_ids else None,position_by_native_id=dict(zip(ids,pos))if aligned else None,reported_native_player_ids=ids,reported_native_positions=pos,reported_native_count=count,native_count_issue=error,exact_eleven_native_proven=bool(valid_ids and len(ids)==11),exact_eleven_positions_proven=bool(aligned and len(ids)==11 and known_labels),position_labels_complete=known_labels)
            if not aligned:issues.append(side+':'+status)
        left=scopes['offense']['native_player_ids'];right=scopes['defense']['native_player_ids']
        if left is not None and right is not None and set(left)&set(right):
            for side in ('offense','defense'):
                scopes[side].update(status='conflicting_cross_side_native_identity',position_by_native_id=None,exact_eleven_native_proven=False,exact_eleven_positions_proven=False)
                issues.append(side+':conflicting_cross_side_native_identity')
        measurements={}
        for name in('defense_man_zone_type','defense_coverage_type'):
            value=r.get(name)
            if value in(None,''):measurements[name]=None
            elif isinstance(value,str):measurements[name]=value
            else:measurements[name]=None;issues.append(name+':invalid_native_label_type')
        row=dict(game_id=gid,play_id=str(play),season=season,week=int(parts[1]),native_phase=r.get('season_type'),possession_team=offense,original_possession_team=r.get('possession_team'),participant_scopes=scopes,measurements=measurements,source_row_ordinal=ordinal,issues=issues)
        rows.append(row)
        for side in('offense','defense'):
            coverage[side+'_exact11_positions']+=int(scopes[side]['exact_eleven_positions_proven'])
        coverage['rows_with_issues']+=int(bool(issues))
    rows.sort(key=lambda r:(r['game_id'],int(r['play_id'])))
    core=dict(version=VERSION,season=season,rows=rows,row_count=len(rows),coverage=dict(coverage),field_scope=list(COLUMNS),evidence_use='Historical postseason FTN native positions/coverage labels only, not eligible snaps/routes/assigned defender',pregame_serving_eligible=False)
    return dict(**core,semantic_sha256=digest(core))


def load_position_component(ref,*,cutoff,directory=None,max_bytes=96*1024*1024):
    boundary=clock(cutoff)
    if boundary is None or boundary>datetime.now(UTC):raise ValueError('Actual nonfuture read cutoff required')
    p=Path(ref['path']);raw=p.read_bytes();folder=Path(directory or'artifacts/participation_position_components').resolve()
    if p.resolve().parent!=folder or p.stem!=ref['sha256']or len(raw)!=ref['bytes']or len(raw)>max_bytes or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Exact immutable managed position component required')
    v=json.loads(raw)
    if v.get('version')!=VERSION or v.get('pregame_serving_eligible')is not False or v['season']not in(2023,2024,2025):raise ValueError('Historical native position component contract required')
    prov=v['provenance'];source=prov['source_ref']
    if source['source_uri']!=URL.format(season=v['season'])or clock(source['captured_at'])is None or not clock(source['captured_at'])<=clock(prov['actual_read_at'])<=clock(prov['actual_publication_at'])<=boundary:raise ValueError('Original source/component clock lineage required')
    if not prov.get('producer_code_hashes'):raise ValueError('Frozen producer bindings required')
    for filename,sha in prov['producer_code_hashes'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen position producer/helper changed')
    semantic={k:value for k,value in v.items()if k not in('semantic_sha256','provenance')}
    if digest(semantic)!=v['semantic_sha256']or v['row_count']!=len(v['rows']):raise ValueError('Position semantic/cardinality proof differs')
    return v
