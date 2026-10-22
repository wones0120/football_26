"""Authenticate two reviewed compact blocks; no DB, fetch or parent inflation."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.target_zone_allocation import load_target_zone_allocation

def main():
    start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/target_zone_allocation_20261020/v1')
    refs={name:json.loads(Path(path).read_text())['full_ref'] for name,path in [('zones','research/player_scoring_zone_components_20261020/v1/actual_derivation_receipt.json'),('endzone','research/endzone_target_components_20261020/v1/actual_receipt.json')]}
    result=load_target_zone_allocation(refs,actual_read_at=actual);result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
    dest=Path('artifacts/target_zone_allocation');dest.mkdir(parents=True,exist_ok=True)
    def save(v):
        raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<16*1024*1024
        sha=hashlib.sha256(raw).hexdigest();path=(dest/(sha+'.json')).resolve()
        if path.exists():assert path.read_bytes()==raw
        else:
            with path.open('xb') as f:f.write(raw)
        return dict(path=str(path),sha256=sha,bytes=len(raw))
    full=save(result);selected={**result,'actor_game_rows':[r for r in result['actor_game_rows'] if r['team'] in {'SF','WAS'}],'team_game_rows':[r for r in result['team_game_rows'] if r['team'] in {'SF','WAS'}]};selected['selected_from_full_ref']=full;selected.pop('semantic_sha256');selected_ref=save(selected)
    coverage=dict(actor_rows=len(result['actor_game_rows']),team_rows=len(result['team_game_rows']),selected_actors=len(selected['actor_game_rows']),selected_teams=len(selected['team_game_rows']),known_comparisons=sum(r['endzone_minus_inside5_share'] is not None for r in result['actor_game_rows']),known_shares={c:sum(r['channels'][c]['share'] is not None for r in result['actor_game_rows']) for c in ('inside5','endzone')})
    receipt=dict(full_ref=full,selected_ref=selected_ref,input_refs=refs,coverage=coverage,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,source_fetches=0,parent_inflations=0,database_writes=0,models=0,review_status='pending High actual review')
    (directory/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
