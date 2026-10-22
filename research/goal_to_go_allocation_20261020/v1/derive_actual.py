from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.goal_to_go_allocation import load_goal_to_go_allocation,CHANNELS

def main():
    start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/goal_to_go_allocation_20261020/v1')
    ref=json.loads(Path('research/player_scoring_zone_components_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref'];result=load_goal_to_go_allocation(ref,actual_read_at=actual);result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
    dest=Path('artifacts/goal_to_go_allocation');dest.mkdir(parents=True,exist_ok=True)
    def save(value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<24*1024*1024
        sha=hashlib.sha256(raw).hexdigest();path=(dest/(sha+'.json')).resolve()
        if path.exists():assert path.read_bytes()==raw
        else:
            with path.open('xb') as f:f.write(raw)
        return dict(path=str(path),sha256=sha,bytes=len(raw))
    full=save(result);selected={**result,'windows':[r for r in result['windows'] if r['team'] in {'SF','WAS'}]};selected.pop('semantic_sha256');selected['selected_from_full_ref']=full;sel=save(selected)
    coverage=dict(windows=len(result['windows']),selected_windows=len(selected['windows']),actor_windows=sum(len(w['actors']) for w in result['windows']),known_shares={str(limit):{ch:sum(a['channels'][ch]['share'] is not None for w in result['windows'] if w['window_max_observed_games']==limit for a in w['actors']) for ch in CHANNELS} for limit in (1,3,8)},achieved_window_game_counts={str(limit):sorted({w['observed_games'] for w in result['windows'] if w['window_max_observed_games']==limit}) for limit in (1,3,8)})
    receipt=dict(full_ref=full,selected_ref=sel,input_ref=ref,coverage=coverage,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,source_fetches=0,database_reads=0,database_writes=0,parent_inflations=0,models=0,review_status='pending High')
    (directory/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
