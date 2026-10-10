"""Frozen pre/post reporting-enhancement comparison. No source collection or DB I/O."""
from copy import deepcopy
from hashlib import sha256
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.product_services.single_lineup import select_single_lineup, CLASSIC_SINGLE_LINEUP_STRATEGY_ID
from backend.app.product_services.classic_game_environment import build_review


def main():
    out=ROOT/'artifacts/classic_game_environment_review'
    control=json.loads((out/'task_start/frozen_control.json').read_text())
    source=control['source'];assert sha256((ROOT/source['path']).read_bytes()).hexdigest()==source['sha256']
    params=deepcopy(control['candidates']);selected,report=select_single_lineup(params,strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID)
    assert selected==control['selected'] and report==control['report'] and len(selected)==1
    before=deepcopy(selected)
    build_review(selected[0],None,run_id='archived',season=2026,week=3,slate='SUNDAY_MAIN',cutoff='2026-09-27T12:00:00Z')
    assert selected==before and params==control['candidates']
    annotated=deepcopy(params)
    for candidate in annotated:
        for player in candidate:player['research_metadata']={'bonus':1e9,'minimum_high_total':8,'actual_cash':True}
    chosen,after=select_single_lineup(annotated,strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID)
    assert [p['player_id'] for p in chosen[0]]==[p['player_id'] for p in selected[0]]
    assert after['recommended']['selection_score']==report['recommended']['selection_score']
    hashes=json.loads((out/'task_start/hashes.json').read_text())
    production=['backend/app/product_services/optimizer.py','backend/app/product_services/single_lineup.py']
    unchanged={p:sha256((ROOT/p).read_bytes()).hexdigest()==hashes[p] for p in production}
    assert all(unchanged.values())
    result={'passed':True,'source':source,'candidate_count':report['candidate_count'],'selected_count':len(selected),
        'selected_ids':[p['player_id'] for p in selected[0]],'before_score':control['report']['recommended']['selection_score'],
        'after_score':report['recommended']['selection_score'],'selected_roster_exactly_identical':True,
        'candidate_report_exactly_identical':True,'research_metadata_cannot_change_selection':True,
        'report_does_not_mutate_inputs':True,'production_source_unchanged':unchanged,'live_solves':0,
        'limitations':['Offline replay on the unchanged archived 120-candidate pool; not a new live-readiness certificate.']}
    (out/'production_preservation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: exact frozen roster/report/score; research metadata inert; optimizer source unchanged.')

if __name__=='__main__':main()
