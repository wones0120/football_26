"""One bounded local two-week reference audit, no operational consumers."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from pypdf import PdfReader
from research.game_progression_pilot_20261020.player_role_evidence.build import load_snapshot
from research.game_progression_pilot_20261020.player_opportunity_accounting.allocation import clock
from .reference import build_reference

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CAP=10


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def check_book(book):
    path=ROOT/book['pdf_path'];capture=json.loads((ROOT/book['capture_path']).read_text())
    if digest(path)!=book['pdf_sha256'] or capture['pdf_sha256']!=book['pdf_sha256'] or capture['game_id']!=book['game_id']:
        raise ValueError('Official source hash/native identity conflict')
    if capture['pdf_uri']!=book['pdf_source_uri'] or capture['pdf_observed_at']!=book['pdf_observed_at']:
        raise ValueError('Original official capture lineage differs')
    reader=PdfReader(path)
    individual=reader.pages[book['individual_page']-1].extract_text(extraction_mode='layout')
    team=reader.pages[book['team_page']-1].extract_text(extraction_mode='layout')
    index=book['game_id'].split('_')[2:].index(book['team'])
    def cell(label):
        lines=[line for line in team.splitlines() if label in line]
        if len(lines)!=1:raise ValueError('Unique official team count line required')
        return lines[0].split()[-2:][index]
    passing=int(cell('PASS ATTEMPTS-COMPLETIONS-HAD INTERCEPTED').split('-')[0])
    rushing=int(cell('Total Rushing Plays'))
    receiving=individual.split('PASS RECEIVING',1)[1].split('INTERCEPTIONS',1)[0]
    totals=[line.split() for line in receiving.splitlines() if line.strip().startswith('Total')]
    if len(totals)!=1:raise ValueError('Unique official receiving total required')
    tokens=totals[0];start=0 if index==0 else tokens.index('Total',1)
    target=int(tokens[start+1])
    if book['counts']!=dict(pass_attempts=passing,rush_attempts=rushing,targets=target):
        raise ValueError('Reviewed annotations disagree with published PDF totals')
    if int(cell('Total Offensive Plays'))!=book['physical_plays']:
        raise ValueError('Official physical play count differs')
    return dict(game_id=book['game_id'],individual_page=book['individual_page'],team_page=book['team_page'],
                individual_text=individual,team_text=team)


def main():
    started=time.monotonic()
    with (HERE/'RUN_STARTED.json').open('x') as f:json.dump(dict(cap_seconds=CAP,automatic_retry=False),f);f.write('\n')
    prior=HERE.parent/'player_role_evidence'
    prior_manifest=json.loads((prior/'MANIFEST.json').read_text())
    expected=next(r['sha256'] for r in prior_manifest['files'] if r['path'].endswith('player_role_evidence/EVIDENCE.json'))
    if digest(prior/'EVIDENCE.json')!=expected:raise ValueError('Retained canonical role evidence changed')
    evidence=json.loads((prior/'EVIDENCE.json').read_text());cutoff=evidence['original_source_cutoff']
    rows=[];sources=[];exclusions=0
    for week,sid in [(4,'87fd7eb4-fe32-5937-bb06-8117abd42b05'),(5,'dc5539a0-da3d-5348-b7bc-7dbcf89276b4')]:
        base=ROOT/f'artifacts/source_snapshots/nflreadpy/weekly_stats/season=2026/week={week:02d}'/sid
        snap=load_snapshot(base/'manifest.json')
        if not clock(snap.observed_at.isoformat())<=clock(snap.captured_at.isoformat())<=clock(cutoff):
            raise ValueError('Original weekly snapshot unavailable at cutoff')
        with Path(snap.artifact_path).open(newline='') as f:raw=list(csv.DictReader(f))
        if len(raw)!=snap.row_count or snap.dataset!='weekly_stats':raise ValueError('Weekly source cardinality/dataset differs')
        for ordinal,r in enumerate(raw):
            if int(r['season'])!=2026 or int(r['week'])!=week or r['season_type']!='REG':
                raise ValueError('Weekly snapshot REG period differs')
            if r['team'] not in {'SF','WAS'}:exclusions+=1;continue
            if not re.fullmatch(r'00-\d{7}',r['player_id']):raise ValueError('Native GSIS identity required')
            counts={}
            for channel,field in [('pass_attempts','attempts'),('rush_attempts','carries'),('targets','targets')]:
                counts[channel]=None if r[field]=='' else float(r[field])
            rows.append(dict(source_player_id=r['player_id'],period=202600+week,team=r['team'],game_id=r['game_id'],
                position=r['position'],counts=counts,source_snapshot_id=sid,source_ordinal=ordinal,
                received_at=snap.captured_at.isoformat()))
        sources += [base/'manifest.json',Path(snap.artifact_path)]
    official=json.loads((HERE/'GAMEBOOK_EVIDENCE.json').read_text())['games']
    pages=[check_book(book) for book in official]
    result=build_reference(rows,evidence['actors'],official,periods=[202604,202605],before_period=202606,cutoff=cutoff)
    baseline=json.loads((HERE/'PRESERVATION_BASELINE.json').read_text())
    changed=[name for name,sha in baseline.items() if digest(ROOT/name)!=sha]
    if changed:raise ValueError(f'Preserved files changed: {changed}')
    elapsed=time.monotonic()-started
    if elapsed>=CAP:raise TimeoutError('Prior workload audit cap exceeded')
    def save(name,value):
        with (HERE/name).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
    save('EXTRACTED_PAGES.json',pages);save('REFERENCE.json',result)
    supported={c:sum(p['channels'][c]['status']=='SUPPORTED_OBSERVED_REFERENCE' for p in result['players']) for c in ('pass_attempts','rush_attempts','targets')}
    refs=sources+[prior/'EVIDENCE.json',prior/'MANIFEST.json']
    refs += [HERE/n for n in ('reference.py','build.py','RECIPE.md','PRESERVATION_BASELINE.json','GAMEBOOK_EVIDENCE.json','EXTRACTED_PAGES.json','REFERENCE.json')]
    refs += [ROOT/'backend/app/tests/product/test_prior_workload_reference.py']
    for book in official:refs += [ROOT/book['pdf_path'],ROOT/book['capture_path']]
    save('MANIFEST.json',dict(status='RETROSPECTIVE_PRIOR_ONLY_WORKLOAD_REFERENCE',recorded_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=elapsed,cap_seconds=CAP,scoped_source_rows=len(rows),excluded_other_team_rows=exclusions,
        current_actors=len(result['players']),supported_observed_reference_actors=supported,
        supported_positive_observed_reference_actors={c:sum(p['channels'][c]['status']=='SUPPORTED_OBSERVED_REFERENCE' and p['channels'][c]['observed_window_sum']>0 for p in result['players']) for c in supported},
        supported_team_game_channels=sum(c['status']=='RECONCILED_FULL_SOURCE_AND_OFFICIAL' for t in result['team_reconciliation'] for c in t['channels'].values()),
        preservation_files=len(baseline),changed_preserved_files=changed,network_requests=0,fits=0,simulations=0,activation=False,
        files=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p)) for p in refs]))
    print(json.dumps(dict(elapsed_seconds=elapsed,preserved=len(baseline),source_rows=len(rows),current_actors=len(result['players']),supported_reference_actors=supported)))


if __name__=='__main__':main()
