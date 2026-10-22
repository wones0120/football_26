"""One cached JSON/PDF source assessment; no model or ledger changes."""
from pathlib import Path
from collections import Counter
from datetime import datetime,UTC
import json,signal,time
from pypdf import PdfReader
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from research.game_progression_pilot_20261020.alternative_clock_sources.assess import bind_event,plays,schema_counts,pdf_mentions

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'ASSESSMENT_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second cached source assessment cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        capture_ref=ref(D/'CAPTURE.json');capture=load(capture_ref)
        assert all(r['status']=='CAPTURED'for r in capture['receipts'])
        source_refs=[r['source_ref']for r in capture['receipts']]
        for r in source_refs:assert ref(r['path'])==r
        summary=load(source_refs[0]);event=bind_event(summary,'401547477','2023-10-15','HOU','NO');rows=plays(summary)
        schema=schema_counts(rows)
        runoff=[p for p in rows if 'runoff'in p.get('text','').lower()or'run-off'in p.get('text','').lower()]
        # Keep provider-native references, never equate ESPN and NFL play IDs.
        examples=[]
        for p in runoff:
            index=rows.index(p)
            examples.append(dict(espn_play_id=p['id'],period=p['period'],clock=p['clock'],isPenalty=p.get('isPenalty'),
                start=p.get('start'),end=p.get('end'),next_espn_play_id=rows[index+1]['id']if index+1<len(rows)else None,
                next_start=rows[index+1].get('start')if index+1<len(rows)else None,
                narrative_status='REPORTED_RUNOFF_CANDIDATE;NOT_ADJUDICATED',native_nfl_play_link_proven=False))
        book=PdfReader(source_refs[1]['path']);assert 1<=len(book.pages)<=30
        texts=[p.extract_text()or''for p in book.pages]
        assert all(token in texts[0]for token in ('New Orleans Saints','Houston Texans','10/15/2023'))
        book_mentions=[dict(page_one_based=i+1,mention_kinds=pdf_mentions(t))for i,t in enumerate(texts)if pdf_mentions(t)]
        protocol=PdfReader(source_refs[2]['path']);assert len(protocol.pages)==8
        protocol_text='\n'.join(p.extract_text()or''for p in protocol.pages)
        assert 'Clock Source'in protocol_text and 'Last play start time'in protocol_text
        prior_ref=ref(D.parent/'clock_stop_amendment/MANIFEST.json');prior=load(prior_ref)
        preserved=prior['preserved_refs']+prior['source_refs']+[prior_ref,prior['amendment_ref']]+[ref(D.parent/'clock_stop_amendment'/n)for n in ('RESULTS.md','VALIDATION.json')]
        inputs=[capture_ref]+source_refs+[ref(D/n)for n in ('RECIPE.md','PRIMARY_REVIEW.json','assess.py','inventory.py')]
        for r in inputs+preserved+prior['current_runtime_refs']:assert ref(r['path'])['sha256']==r['sha256']
        report=dict(version='alternative_clock_source_assessment_v1',elapsed_seconds=time.monotonic()-start,cap_seconds=30,
            input_refs=inputs,preserved_refs=preserved,current_runtime_refs=prior['current_runtime_refs'],
            espn_event_binding=event,espn_play_schema=schema,espn_examples=examples,
            gamebook=dict(pages=len(book.pages),native_game_context_matched=True,mention_pages=book_mentions,
                native_nfl_play_link_proven=False,new_play_end_clock_supported=False,new_restart_enforcement_supported=False),
            gsis_protocol=dict(pages=len(protocol.pages),documentation_only=True,legacy_date='2008-11-04',
                stadium_source_and_fallback_distinction_documented=True,archive_obtained=False,current_access_verified=False),
            new_supported_play_end_clock_records=0,new_supported_restart_enforcement_records=0,
            disposition='PUBLIC_SAMPLES_DO_NOT_CLOSE_GAP;TIMING_STREAM_ARCHIVE_AND_EVENT_LINKAGE_REQUIRED',
            game_scope_count=1,ledger_rows_added=0,paid_access=False,provider_contact=False,reconstruction_runs=0,simulation_runs=0,fits=0,activation=False)
        with (D/'ASSESSMENT.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','espn_event_binding','espn_play_schema','gamebook','disposition')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
