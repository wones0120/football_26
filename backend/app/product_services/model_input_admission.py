"""Explicit reconstructed-history model view; raw evidence and baseline remain immutable."""
from uuid import UUID
import math
from .team_opportunity_matrix import FEATURES as TEAM_COLUMNS,VERSION as TEAM_VERSION
from .offensive_volume_features import FEATURES as PLAYER_COLUMNS,VERSION as PLAYER_VERSION,digest
from .market_snapshots import canonical_team
VERSION='reconstructed_count_input_admission_v1'
VINTAGE_PREFIXES=('opponent_dropback_epa','opponent_dropback_success','opponent_rush_epa','opponent_rush_success')
MASKED_TEAM_COLUMNS=('game_total_line','team_spread_line',*(p+s for p in VINTAGE_PREFIXES for s in('_mean','_known_exposure','_unknown_eligibility','_unknown_outcomes')))


def fold(period):
    if type(period)is not int:raise ValueError('Integer native period required')
    return 'train'if period<202401 else 'validation'if period<202501 else 'retrospective_test'if period<202601 else 'inspected_later_diagnostic'if period<202606 else 'forward_only'


def admit_matrix(matrix,*,grain,parent_ref):
    if grain not in {'team','player'}:raise ValueError('Explicit matrix grain required')
    basis={k:v for k,v in matrix.items()if k not in {'matrix_sha256','provenance'}}
    if digest(basis)!=matrix.get('matrix_sha256'):raise ValueError('Raw parent semantic checksum mismatch')
    expected=list(TEAM_COLUMNS)if grain=='team'else [*PLAYER_COLUMNS,*(f'team_{k}'for k in TEAM_COLUMNS)]
    if matrix.get('version')!=(TEAM_VERSION if grain=='team'else PLAYER_VERSION)or matrix.get('feature_columns')!=expected:raise ValueError('Exact fixed ordered matrix schema required')
    masks=list(MASKED_TEAM_COLUMNS)if grain=='team'else ['team_'+k for k in MASKED_TEAM_COLUMNS]
    assert len(masks)==18 and set(masks)<=set(expected)
    out=[];games={};seen=set();changes={k:0 for k in masks}
    for row in matrix['rows']:
        p=row['period'];f=fold(p);gid=row.get('game_id');parts=str(gid).split('_')
        if len(parts)!=4 or f'{p//100:04d}_{p%100:02d}'!='_'.join(parts[:2])or not 1<=p%100<=18 or canonical_team(row['team'])not in {canonical_team(v)for v in parts[2:]}:raise ValueError('Native game/team/period binding required')
        if gid in games and games[gid]!=f:raise ValueError('One native game cannot cross folds')
        games[gid]=f
        if any(type(v)is not int or v>=p for field in('history_periods','context_periods','legacy_periods')for v in row.get(field,[])):raise ValueError('Target or future contributing period')
        subject=row['team']if grain=='team'else str(UUID(str(row['player_master_id'])))
        key=(subject,row['team'],p)
        if key in seen:raise ValueError('Duplicate model subject/team/period')
        seen.add(key)
        if set(row['features'])!=set(expected):raise ValueError('Unknown or missing model input column')
        values=dict(row['features'])
        for field in masks:
            changes[field]+=values[field]is not None;values[field]=None
        out.append(dict(row,features=values))
    policy=dict(version=VERSION,grain=grain,parent_ref=parent_ref,masked_columns=masks,reason='Original quote clocks or retained provider expected-points model/training vintage unproven',availability='Revised-history reconstruction only; NOT original-pregame backtest proof',new_catalog_adapters=False)
    result=dict(matrix,rows=out,admission_policy=policy);result.pop('matrix_sha256');result['matrix_sha256']=digest({k:v for k,v in result.items()if k!='provenance'})
    return result,dict(rows=len(out),games=len(games),masked_previously_present=changes,fold_game_counts={name:sum(v==name for v in games.values())for name in ('train','validation','retrospective_test','inspected_later_diagnostic','forward_only')})


def cohort_manifest(prepared,*,grain):
    targets=prepared['target_columns'];result={}
    for split,part in prepared['splits'].items():
        keys=part['keys'];n=len(keys)
        if len(part['x'])!=n:raise ValueError('Prepared row alignment mismatch')
        expected=split
        if any(fold(k['period'])!=expected for k in keys):raise ValueError('Prepared split has wrong game fold')
        target_rows=part['labels']if grain=='player'else [dict(zip(targets,row))for row in part['y']]
        if len(target_rows)!=n:raise ValueError('Prepared label alignment mismatch')
        heads={}
        for target in targets:
            ids=[i for i,r in enumerate(target_rows)if r[target]is not None];ys=[target_rows[i][target]for i in ids]
            if any(isinstance(v,bool)or not math.isfinite(v)or v<0 for v in ys):raise ValueError('Only known nonnegative official count labels')
            heads[target]=dict(known_rows=len(ids),unknown_excluded=n-len(ids),known_zero_rows=sum(v==0 for v in ys),label_sum=sum(ys),keys_sha256=digest([keys[i]for i in ids]),labels_sha256=digest(ys))
        result[split]=dict(rows=n,game_ids_sha256=digest(sorted({k['game_id']for k in keys})),head_cohorts=heads)
    return result
