"""One <=60s cached fixed-five actual-count reconciliation. No simulation."""
from collections import Counter
from datetime import datetime,UTC
from pathlib import Path
import csv,hashlib,json,signal,time
from research.game_progression_pilot_20261020.scenario_03.count_labels import reconcile,FIELDS
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,ROOT
from backend.app.product_services.game_state_reconstruction import integer

D=Path(__file__).resolve().parent

def main():
    destination=D/'RECONCILIATION.json'
    if destination.exists():raise ValueError('No overwrite or unchanged rerun')
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    def cap(*_):raise TimeoutError('60-second cached count-label reconciliation cap')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        v3=D.parent/'v3';manifest_path=v3/'MANIFEST.json';m=json.loads(manifest_path.read_text())
        preserved=[ref(p)for p in (manifest_path,v3/'CHECKPOINT.json',v3/'RESULTS.json',v3/'smoke_attempt_3/SUMMARY.json',v3/'smoke_attempt_3/paths.jsonl')]
        truth=load(m['evaluation_only_labels_ref']);prior_by={g['game_id']:g for g in truth['games']}
        books=json.loads((D/'GAMEBOOK_EVIDENCE.json').read_text())['games'];assert len(books)==3
        schedule_path=ROOT/'artifacts/source_snapshots/nflreadpy/schedules/season=2026/8f5478ad-6fd6-54bd-8013-9af383134dce/nflreadpy_schedules_2026.csv'
        schedule_manifest=json.loads((schedule_path.parent/'manifest.json').read_text());schedule_ref=ref(schedule_path)
        assert schedule_ref['sha256']==schedule_manifest['content_sha256']and schedule_ref['bytes']==schedule_manifest['byte_count']
        with schedule_path.open()as sink:schedules=list(csv.DictReader(sink))
        projection=load(m['source_projection_refs'][1]);columns=projection['columns'];selected={b['game_id']for b in books};native={g:[]for g in selected}
        for values in projection['rows']:
            raw=dict(zip(columns,values))
            if raw['game_id']in selected:native[raw['game_id']].append(raw)
        reconciled=[];source_refs=[]
        for book in books:
            gid=book['game_id'];capture_path=Path(book['capture_receipt_path']);capture=json.loads(capture_path.read_text());pdf_ref=ref(book['pdf_path'])
            assert capture['status']=='captured'and capture['game_id']==gid
            assert pdf_ref['sha256']==capture['pdf_sha256']==book['pdf_sha256']
            assert book['pdf_source_uri']==capture['pdf_uri']and book['page_source_uri']==capture['page_uri']
            assert f"-{book['season']}-reg-{book['week']}?tab=recap"in capture['page_uri']
            page_path=Path(book['extracted_pages_path']);pages=json.loads(page_path.read_text());text='\n'.join(p['text']for p in pages)
            y,mo,day=map(int,book['game_date'].split('-'));assert f'{mo}/{day}/{y}'in text
            assert 'Final Team Statistics'in pages[book['team_page']-1]['text']
            assert 'Final Individual Statistics'in pages[book['individual_page']-1]['text']
            assert 'PASS RECEIVING'in pages[book['individual_page']-1]['text']and 'TAR'in pages[book['individual_page']-1]['text']
            matches=[s for s in schedules if s['game_id']==gid];assert len(matches)==1
            schedule=matches[0]
            assert schedule['away_team']==book['away_team']and schedule['home_team']==book['home_team']
            rows=native[gid];assert rows and all(r['season_type']=='REG'for r in rows)
            quarters=[integer(r.get('qtr'))for r in rows]
            play_keys=[integer(r['play_id'])for r in rows]
            scope=dict(game_id=gid,season=int(schedule['season']),week=int(schedule['week']),teams=[schedule['away_team'],schedule['home_team']],game_date=schedule['gameday'],
                native_quarters=sorted(set(q for q in quarters if q is not None)),unknown_period_rows=quarters.count(None),
                all_native_rows_retained=projection['source_lineage']['all_source_rows_retained']is True,
                unique_native_play_keys=None not in play_keys and len(play_keys)==len(set(play_keys)),native_rows=len(rows),
                source_projection_ref=m['source_projection_refs'][1],source_schedule_ref=schedule_ref,old_game_id=schedule['old_game_id'])
            out=reconcile(prior_by[gid],book,scope);reconciled.append(out)
            source_refs.append(dict(game_id=gid,pdf=pdf_ref,capture=ref(capture_path),extracted_pages=ref(page_path),pdf_observed_at=capture['pdf_observed_at']))
        by={g['game_id']:g for g in reconciled};assert all(not g['conflicts']for g in reconciled)
        games=[]
        for original in truth['games']:
            gid=original['game_id'];result=by.get(gid);counts=result['production_by_side']if result else[{f:s[f]for f in FIELDS}for s in original['production_by_side']]
            games.append(dict(game_id=gid,source_sides=original['source_sides'],production_by_side=counts,
                count_source='REVIEWED_OFFICIAL_GAMEBOOK_FINAL_TOTALS_WITH_REGULATION_SCOPE_PROOF'if result else'UNCHANGED_V3_PBP_COUNT_PROOF',
                original_evaluation_labels_ref=m['evaluation_only_labels_ref'],event_level_unknowns_reinterpreted=False))
        old_coverage={f:sum(side[f]is not None for g in truth['games']for side in g['production_by_side'])for f in FIELDS}
        new_coverage={f:sum(side[f]is not None for g in games for side in g['production_by_side'])for f in FIELDS}
        assert new_coverage==dict.fromkeys(FIELDS,10)
        assert preserved==[ref(r['path'])for r in preserved]
        report=dict(version='fixed5_independent_official_regulation_counts_v1',started_at=stamp,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,whole_job_cap_seconds=60,
            recipe_ref=ref(D/'RECIPE.md'),reviewed_evidence_ref=ref(D/'GAMEBOOK_EVIDENCE.json'),sources=source_refs,schedule_manifest_ref=ref(schedule_path.parent/'manifest.json'),
            previous_label_coverage=old_coverage,new_label_coverage=new_coverage,games=games,reconciliations=reconciled,preserved_evidence_refs=preserved,
            helper_ref=ref(D/'count_labels.py'),runner_ref=ref(__file__),
            original_pregame_availability=False,previously_inspected_outcomes=True,source_state_validity_assessed=False,event_level_unknowns_resolved=False,
            player_identity_assignments=0,simulations=0,fits=0,new_accuracy_metrics=False,database_mutations=0,new_source_requests=0,activation=False)
        with destination.open('x')as sink:sink.write(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','previous_label_coverage','new_label_coverage','simulations','activation')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
