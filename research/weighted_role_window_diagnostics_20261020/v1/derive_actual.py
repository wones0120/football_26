from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.weighted_role_window_diagnostics import load_weighted_role_window_diagnostics

def main():
    started=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/weighted_role_window_diagnostics_20261020/v1')
    ref=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text())['full_ref']
    result=load_weighted_role_window_diagnostics(ref,actual_read_at=actual);result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
    dest=Path('artifacts/weighted_role_window_diagnostics');dest.mkdir(parents=True,exist_ok=True)
    def save(value):
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<24*1024*1024
        sha=hashlib.sha256(raw).hexdigest();path=(dest/(sha+'.json')).resolve()
        if path.exists():assert path.read_bytes()==raw
        else:
            with path.open('xb') as f:f.write(raw)
        return dict(path=str(path),sha256=sha,bytes=len(raw))
    full=save(result);selected={**result,'rows':[r for r in result['rows'] if r['team'] in {'SF','WAS'}]};selected.pop('semantic_sha256');selected['selected_from_full_ref']=full;selected_ref=save(selected)
    coverage=dict(rows=len(result['rows']),canonical_rows=sum(r['player_master_id'] is not None for r in result['rows']),selected_rows=len(selected['rows']),known_game_ess=sum(r['game_effective_sample_size'] is not None for r in result['rows']),known_weighted_exposure={c:sum(r['metrics'][c]['weighted_exposure'] is not None for r in result['rows']) for c in ('pass_attempts','rush_attempts','targets')},known_concentration_ess={c:sum(r['metrics'][c]['exposure_concentration_effective_games'] is not None for r in result['rows']) for c in ('pass_attempts','rush_attempts','targets')})
    receipt=dict(full_ref=full,selected_ref=selected_ref,input_ref=ref,coverage=coverage,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-started,source_fetches=0,parent_inflations=0,database_writes=0,models=0,review_status='pending High')
    (directory/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
