"""Post-convergence saved-output stratification; never fits or selects a recipe."""
from collections import defaultdict
from pathlib import Path
from io import BytesIO
import argparse,hashlib,json
import numpy as np
from backend.app.product_services.market_snapshots import canonical_team


def metric(pairs):
    if not pairs:return dict(n=0,mae=None,rmse=None,bias=None)
    y,p=np.asarray(pairs,dtype=float).T;e=p-y
    return dict(n=len(y),mae=float(abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),bias=float(e.mean()))


def opponent(game_id,team):
    season,week,away,home=game_id.split('_');away,home=canonical_team(away),canonical_team(home)
    if team not in{away,home}:raise ValueError('Canonical native game/team mismatch')
    return home if team==away else away


def tags(row,role=None,exposure=None):
    result=['all','zero'if row['label']==0 else'positive']
    if row['kind']=='candidate':
        result+=['prior_role:'+str(role),'prior3_exposure_known'if exposure is not None else'prior3_exposure_unknown']
        if exposure==0:result+=['prior3_exposure_known_zero']
    return result


def matched_report(rows):
    """Rows already have identical keys/labels; missing old rows never enter."""
    buckets=defaultdict(lambda:dict(new=[],saved=[]));weeks=defaultdict(lambda:dict(new=[],saved=[]));matchups=defaultdict(lambda:dict(new=[],saved=[]))
    week_strata=defaultdict(lambda:dict(new=[],saved=[]));matchup_strata=defaultdict(lambda:dict(new=[],saved=[]))
    for row in rows:
        for tag in row['tags']:
            name=str(row['year'])+'|'+tag
            buckets[name]['new'].append((row['label'],row['new']));buckets[name]['saved'].append((row['label'],row['saved']))
        week=str(row['year'])+'_'+str(row['week']).zfill(2)
        matchup=row['game_id']+'|'+row['team']+'|vs_'+row['opponent']
        for d,key in((weeks,week),(matchups,matchup)):
            d[key]['new'].append((row['label'],row['new']));d[key]['saved'].append((row['label'],row['saved']))
        for tag in row['tags']:
            for d,key in((week_strata,week+'|'+tag),(matchup_strata,matchup+'|'+tag)):
                d[key]['new'].append((row['label'],row['new']));d[key]['saved'].append((row['label'],row['saved']))
    convert=lambda d:{k:{side:metric(pairs)for side,pairs in v.items()}for k,v in sorted(d.items())}
    wk,mp=convert(weeks),convert(matchups);macro={}
    for year in sorted({r['year']for r in rows}):
        matched=[v for k,v in wk.items()if k.startswith(str(year)+'_')]
        native_matched=[v for k,v in mp.items()if k.startswith(str(year)+'_')]
        deltas=[v['new']['mae']-v['saved']['mae']for v in matched]
        macro[str(year)]=dict(weeks=len(matched),improved_weeks=sum(x< -1e-12 for x in deltas),worsened_weeks=sum(x>1e-12 for x in deltas),tied_weeks=sum(abs(x)<=1e-12 for x in deltas),
                             macro_week_new_mae=float(np.mean([v['new']['mae']for v in matched]))if matched else None,
                             macro_week_saved_mae=float(np.mean([v['saved']['mae']for v in matched]))if matched else None,
                             native_team_opponent_groups=len(native_matched),
                             macro_matchup_new_mae=float(np.mean([v['new']['mae']for v in native_matched]))if native_matched else None,
                             macro_matchup_saved_mae=float(np.mean([v['saved']['mae']for v in native_matched]))if native_matched else None)
    return dict(pooled_by_stratum=convert(buckets),paired_by_week=wk,paired_by_native_team_opponent=mp,
                paired_by_week_and_stratum=convert(week_strata),paired_by_matchup_and_stratum=convert(matchup_strata),macro_week=macro)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',choices=['v3'],default='v3');parser.add_argument('--channel',choices=['rush','target'],required=True);args=parser.parse_args()
    R=Path(__file__).resolve().parent/args.version;job=json.loads((R/(args.channel+'.json')).read_text())
    if job['status']!='completed':raise ValueError('Failed models have no prediction/evaluation permission')
    def read(ref):
        b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b
    manifest=json.loads(Path(job['manifest_path']).read_text());records=json.loads(read(job['prediction_ref']));tensor=np.load(BytesIO(read(manifest['tensor_ref'])),allow_pickle=False)
    columns=manifest['feature_columns'];offsets=tensor['offsets'];raw=tensor['raw_inputs'];by_index={r['group_index']:r for r in records}
    roles={};exposures={};all_buckets=defaultdict(list)
    for r in records:
        year=r['period']//100;week=r['period']%100;opp=opponent(r['game_id'],r['team']);i=r['group_index']
        for j,c in enumerate(r['cells']):
            role=None;exposure=None
            if c['kind']=='candidate':
                names=[role for role in('QB','RB','WR','TE','FB','other')if raw[offsets[i]+j,columns.index('latest_prior_role_'+role)]==1]
                role=names[0]if names else'UNKNOWN'
                value=raw[offsets[i]+j,columns.index('scheduled3_carries_exposure'if args.channel=='rush'else'scheduled3_targets_exposure')]
                exposure=float(value)if np.isfinite(value)else None
            roles[i,j]=role;exposures[i,j]=exposure
            for tag in tags(c,role,exposure):
                all_buckets[f'{year}|week{week:02}|{c["kind"]}|{tag}'].append((c['label'],c['prediction']))
                all_buckets[f'{r["game_id"]}|{r["team"]}|vs_{opp}|{c["kind"]}|{tag}'].append((c['label'],c['prediction']))
        budgets=[('budget_label','budget_mean')]if args.channel=='rush'else[('target_budget_label','target_mean'),('pass_budget_label','pass_mean')]
        for label_key,pred_key in budgets:
            pair=r['budget_labels'][label_key],r['predicted'][pred_key]
            all_buckets[f'{year}|week{week:02}|{pred_key}'].append(pair)
            all_buckets[f'{r["game_id"]}|{r["team"]}|vs_{opp}|{pred_key}'].append(pair)
    saved=json.loads(read(manifest['saved_baseline_matches_ref']));paired={}
    for name,matches in saved.items():
        rows=[]
        for match in matches:
            i,j=match['group_index'],match['cell_index'];r=by_index[i];c=r['cells'][j];assert c['label']==match['actual']
            rows.append(dict(year=r['period']//100,week=r['period']%100,game_id=r['game_id'],team=r['team'],opponent=opponent(r['game_id'],r['team']),label=c['label'],new=c['prediction'],saved=match['saved_prediction'],tags=tags(c,roles[i,j],exposures[i,j])))
        paired[name]=matched_report(rows)
    team_pair={}
    # Team budget baselines are independently saved observations, NOT summed
    # incomplete old player predictions. Only exact matching labels enter.
    for exp in('pressure_count_model_fits_20261020','workload_direct_count_fits_20261020'):
        for family in('tree','neural'):
            rec=json.loads(Path('research',exp,'v1','team_'+family+'.json').read_text());old=json.loads(read(rec['prediction_ref']));lookup={(r['game_id'],r['team']):r for r in old};rows=[];excluded=0
            for r in records:
                previous=lookup.get((r['game_id'],r['team']));head='rush_attempts'if args.channel=='rush'else'pass_attempts';lk='budget_label'if args.channel=='rush'else'pass_budget_label';pk='budget_mean'if args.channel=='rush'else'pass_mean';label=r['budget_labels'][lk]
                if previous is None or previous['actual'][head]!=label:excluded+=1;continue
                rows.append(dict(year=r['period']//100,week=r['period']%100,game_id=r['game_id'],team=r['team'],opponent=opponent(r['game_id'],r['team']),label=label,new=r['predicted'][pk],saved=previous['predicted'][head],tags=['all']))
            team_pair[exp+'_'+family]=dict(excluded_missing_or_changed_labels=excluded,**matched_report(rows))
    result=dict(status='POSTCONVERGENCE_SAVED_OUTPUT_EVALUATION',channel=args.channel,
                complete_new_population={k:metric(v)for k,v in sorted(all_buckets.items())},matched_saved_candidate_population=paired,matched_saved_team_budget_population=team_pair,
                injury_replacement_stratum='UNKNOWN:0qualifieddatedpregamecases;notfalse/notinferredfromusage',
                scope='Previouslyinspected2025retrospective selectedSOURCE_OBSERVED groups; fullnewcandidate/rest populationdistinctfromincomplete matchedold. No2026/fullNFLcensus/originalpregameorliveclaim.',fits=0)
    out=R/(args.channel+'_WEEK_MATCHUP.json');encoded=(json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    if out.exists():assert out.read_bytes()==encoded
    else:out.write_bytes(encoded)
    print(json.dumps(dict(path=str(out),bytes=len(encoded),candidate_macro={k:v['macro_week']for k,v in paired.items()}),indent=2))


if __name__=='__main__':main()
