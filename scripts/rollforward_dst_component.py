"""Version an accepted fixed DST policy with newly verified prior-game history.

No old artifact is overwritten, no weights are refitted, no config is changed.
The caller must explicitly select the returned manifest after reviewing receipt.
"""
import argparse,hashlib,json
from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
import joblib,pandas as pd
from sqlalchemy import text
from backend.app.db import engine
from backend.app.config import get_settings
from backend.app.product_services.primary_model_source import ensure_source,source_inputs
from backend.app.product_services.dst_deployment import load_selection,score_component
from backend.app.product_services.dst_scoring_reconciliation import score_game
from backend.app.product_services.dst_feature_pipeline import DstFeatureContext

def run(season,week,slate,destination):
    root=Path(destination);root.mkdir(parents=True,exist_ok=False)
    settings=get_settings();old,audit=load_selection(settings.dst_deployment_manifest_path,settings.dst_deployment_manifest_sha256)
    target=season*100+week
    if old['target_period']>=target:raise ValueError('Roll-forward must advance the target period')
    ensure_source(engine,season=season,week=week,slate=slate)
    _,source=source_inputs(engine,season=season,week=week,slate=slate,cutoff=datetime.now(UTC))
    with engine.connect() as connection:
        identities={str(t):str(pid) for t,pid in connection.execute(text("SELECT primary_team,player_master_id FROM player_master WHERE position='DST'"))}
        schedule=connection.execute(text("SELECT DISTINCT ON (game_id) game_id,raw_row_json FROM raw_nfl_schedule WHERE source_system='nflreadpy' AND season=:s AND week<:w ORDER BY game_id,created_at DESC,raw_nfl_schedule_id DESC"),dict(s=season,w=week)).all()
    frame=pd.read_csv(source['artifact_path'],low_memory=False)
    events=[]
    for gid,raw in schedule:
        period=int(gid[:4])*100+int(gid.split('_')[1])
        if not old['target_period']<=period<target:continue
        away,home=gid.split('_')[2:]
        from Database.dst import normalize_team
        away,home=normalize_team(away),normalize_team(home)
        rows=frame.loc[frame.game_id.eq(gid)].to_dict('records')
        result=score_game(rows,expected_game_id=gid,expected_teams={home,away},canonical_player_ids=identities,
            expected_score={home:raw['home_score'],away:raw['away_score']})
        for row in result:
            events.append(dict(season=season,week=period%100,team=row['team'],opponent=row['opponent'],game_id=gid,
                player_master_id=row['player_master_id'],points=row['dk_points'],sacks=row['components']['sacks'],
                takeaways=row['components']['interceptions']+row['components']['fumble_recoveries'],allowed=row['components']['points_allowed']))
    if not events:raise ValueError('No newly verified completed games; cannot extend expiry')
    updated=deepcopy(old);outcomes=pd.concat([old['context'].outcomes,pd.DataFrame(events)],ignore_index=True)
    if outcomes.duplicated(['game_id','player_master_id']).any():raise ValueError('Duplicate refreshed DST history')
    event_sha=hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest()
    updated['context']=DstFeatureContext(outcomes.sort_values(['season','week','game_id','team']),event_sha,old['context'].identities_sha256,
        old['context'].chronology+'; refreshed verified prior outcomes for next-period serving',old['context'].schedule)
    updated.update(target_period=target,source_hashes={**old['source_hashes'],'events':event_sha,'parent_events':old['source_hashes']['events']})
    artifact=root/'component.joblib';joblib.dump(updated,artifact,compress=3)
    manifest=json.loads(Path(settings.dst_deployment_manifest_path).read_text())
    manifest['artifact']=dict(path=str(artifact.resolve()),sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest['acceptance']=dict(status='approved',decision_id=f'user-requested-week-rollforward-{target}',
        standard='User-authorized first-use roll-forward of the accepted fixed policy; verified new prior history, unchanged fitted weights/calibration; ranking advantage remains unproven',
        limitations_acknowledged=True,evidence_sha256={'parent_selection':settings.dst_deployment_manifest_sha256,'refreshed_events':event_sha},
        user_instruction='Keep working through the TODO list until the Week 7 Thursday Night workflow is ready. Make the new models drive lineup selection, resolve the DST expiry, and preserve the old optimizer as the comparison.',
        scope=dict(season=season,week=week,slate=slate),captured_at=datetime.now(UTC).isoformat())
    manifest['limitations']=['Same accepted policy weights and residual calibration; new verified prior history; no ranking-superiority claim','Original historical capture chronology remains incomplete']
    path=root/'selection.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
    sha=hashlib.sha256(path.read_bytes()).hexdigest();load_selection(path,sha)
    receipt=dict(selection_path=str(path.resolve()),selection_sha256=sha,parent_selection=settings.dst_deployment_manifest_path,
        target_period=target,new_team_game_rows=len(events),fits=0,source=source,weights_and_calibration_unchanged=True)
    (root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--season',type=int,required=True);parser.add_argument('--week',type=int,required=True)
    parser.add_argument('--slate',required=True);parser.add_argument('--destination',required=True);args=parser.parse_args()
    run(args.season,args.week,args.slate,args.destination)
