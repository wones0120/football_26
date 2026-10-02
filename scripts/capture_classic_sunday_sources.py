"""Capture new immutable public Sunday evidence through existing source services.

Only source captures and their normal ingests are written. No optimizer or
strategy defaults change. Prior-week usage explicitly excludes this week's games.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import uuid

import pandas as pd
import requests

from backend.app.db import SessionLocal
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.ingest import IngestService
from backend.app.services.source_capture import SourceCaptureService, fetch_nflreadpy_dataset
from scripts.capture_showdown_lock_sources import PageParser


CLUBS={'ARI':'azcardinals','BAL':'baltimoreravens','BUF':'buffalobills','CHI':'chicagobears',
       'CIN':'bengals','DAL':'dallascowboys','DEN':'denverbroncos','GB':'packers',
       'HOU':'houstontexans','JAX':'jaguars','KC':'chiefs','LAC':'chargers','LAR':'therams',
       'LV':'raiders','MIA':'miamidolphins','MIN':'vikings','NE':'patriots','NYG':'giants',
       'NYJ':'newyorkjets','PHI':'philadelphiaeagles','SEA':'seahawks','SF':'49ers',
       'TB':'buccaneers','TEN':'tennesseetitans'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control',type=Path,required=True)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--draft-group-id',type=int,required=True)
    args=parser.parse_args()
    comparison=json.loads(args.comparison.read_text())
    assert comparison['sha256']==__import__('backend.app.product_services.classic_prospective',fromlist=['digest_payload']).digest_payload({k:v for k,v in comparison.items() if k!='sha256'})
    inputs=json.loads(args.control.read_text());r=inputs['report'];meta=r['frozen_solver_snapshot']['payload']['metadata']
    season,week,slate=meta['season'],meta['week'],meta['slate'];kickoff=datetime.fromisoformat(r['prelock_timing']['first_saved_kickoff_at'])
    base=args.directory;raw=base/'public_sources';raw.mkdir(parents=True,exist_ok=True)
    if (base/'capture_manifest.json').exists():raise ValueError('Choose a new timestamped snapshot')
    urls={'dk_salary':f'https://www.draftkings.com/lineup/getavailableplayerscsv?draftGroupId={args.draft_group_id}',
          'nfl_injuries':'https://www.nfl.com/injuries/',
          'cin_jax_injuries':'https://www.bengals.com/news/jaguars-bengals-injury-report-week-4-2026',
          'dk_market':'https://dknetwork.draftkings.com/moneyline-total-spread/'}
    for team,club in CLUBS.items():
        for field,path in [('roster','team/players-roster/'),('depth','team/depth-chart/'),('injuries','team/injury-report/')]:
            urls[team.lower()+'_'+field]=f'https://www.{club}.com/{path}'
        if team in {'CIN','JAX','LAR','MIA','ARI','KC','LV','MIN'}:urls[team.lower()+'_news']=f'https://www.{club}.com/news/'
    def fetch(item):
        key,url=item;at=datetime.now(UTC).isoformat()
        try:
            response=requests.get(url,timeout=20);response.raise_for_status()
            path=raw/(key+('.csv' if key=='dk_salary' else '.raw'))
            with path.open('xb') as h:h.write(response.content)
            result={'url':url,'retrieved_at':at,'completed_at':datetime.now(UTC).isoformat(),
                    'status':response.status_code,'sha256':sha256(response.content).hexdigest(),
                    'path':str(path),'content_type':response.headers.get('content-type')}
            if key!='dk_salary':
                page=PageParser();page.feed(response.text)
                with (raw/(key+'.parsed.json')).open('x') as h:json.dump({'tables':page.tables,'links':page.links,'text':' '.join(page.text)},h,indent=2)
            else:
                frame=pd.read_csv(io.BytesIO(response.content))
                if not {'ID','TeamAbbrev','Game Info','Salary'}<=set(frame):raise ValueError('Not a native salary CSV')
                result['row_count']=len(frame)
            return key,result
        except Exception as error:return key,{'url':url,'retrieved_at':at,'error':str(error)}
    with ThreadPoolExecutor(max_workers=6) as pool:manifest=dict(pool.map(fetch,urls.items()))
    lineage={}
    # Refresh raw official evidence; HTTP success alone never confirms a role.
    for key,row in manifest.items():
        if 'sha256' not in row:continue
        try:
            with SessionLocal() as session:
                service=SourceCaptureService(session,snapshot_root=base/'immutable_source_snapshots')
                if key=='dk_salary':
                    result=service.capture_and_ingest_draftkings_salary(Path(row['path']),season=season,week=week,slate=slate,
                           slate_lock_at=kickoff,source_license='Official public DraftKings download; upstream terms apply',source_uri=row['url'])
                    lineage[key]={'snapshot_id':str(result.capture.snapshot.snapshot_id),'ingest':result.ingest.model_dump(mode='json')}
                else:
                    result=service.capture_file(Path(row['path']),source_system='draftkings_public' if key=='dk_market' else 'official_nfl_club',
                           dataset='classic_sunday_'+key,season=season,week=week,slate=slate,
                           slate_lock_at=kickoff,source_uri=row['url'],source_license='Public official source; upstream terms apply',
                           metadata={'fresh_retrieved_at':row['retrieved_at'],'capture_sha256':row['sha256']})
                    lineage[key]={'snapshot_id':str(result.snapshot.snapshot_id),'observed_at':result.snapshot.observed_at.isoformat(),'created':result.created}
        except Exception as error:lineage[key]={'error':str(error)}
    # Use existing NFL loaders and ingest transforms. Failures remain explicit.
    for dataset in ['weekly_rosters','depth_charts','injuries','weekly_stats','snap_counts']:
        try:
            frame,version=fetch_nflreadpy_dataset(dataset,season=season,week=None if dataset in {'weekly_stats','snap_counts'} else week)
            if dataset in {'weekly_stats','snap_counts'}:
                frame=frame.loc[pd.to_numeric(frame['week'],errors='coerce')<week].copy()
            with SessionLocal() as session:
                service=SourceCaptureService(session,snapshot_root=base/'immutable_source_snapshots')
                captured=service.capture_dataframe(frame,artifact_name=dataset+'.csv',source_system='nflreadpy',dataset=dataset,
                           season=season,week=week,slate=slate,slate_lock_at=kickoff,
                           source_license='nflverse data via nflreadpy; upstream terms apply',source_uri=f'nflreadpy://{dataset}/{season}',
                           metadata={'nflreadpy_version':version,'this_week_actuals_excluded':dataset in {'weekly_stats','snap_counts'}})
                row={'snapshot_id':str(captured.snapshot.snapshot_id),'path':captured.snapshot.artifact_path,
                     'rows':len(frame),'observed_at':captured.snapshot.observed_at.isoformat()}
                if dataset in {'weekly_rosters','weekly_stats','snap_counts'}:
                    # IDs derive from the preserved capture, making retries idempotent.
                    run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'classic_refresh/'+str(captured.snapshot.snapshot_id)))
                    request=NflReadPySeasonRequest(season=season,weeks=[week] if dataset=='weekly_rosters' else list(range(1,week)))
                    result=getattr(IngestService(session),'ingest_nflreadpy_'+dataset)(request,source_frame=pd.read_csv(captured.snapshot.artifact_path),
                        ingest_run_id=run_id,source_path=captured.snapshot.artifact_path)
                    service.link_ingest_run(captured.snapshot.snapshot_id,result.ingest_run_id)
                    row['ingest']=result.model_dump(mode='json')
                lineage['nflreadpy_'+dataset]=row
        except Exception as error:lineage['nflreadpy_'+dataset]={'error':str(error)}
        print(dataset,{k:v for k,v in lineage['nflreadpy_'+dataset].items() if k in {'rows','error'}},flush=True)
    envelope={'contract':'classic_sunday_source_refresh_v1','captured_at':datetime.now(UTC).isoformat(),
              'comparison_sha256':comparison['sha256'],'source_control':meta['optimizer_run_id'],
              'official_final_inactives':'not_yet_published','public_sources':manifest,'pipeline_lineage':lineage}
    with (base/'capture_manifest.json').open('x') as h:json.dump(envelope,h,sort_keys=True,indent=2)
    print('captured',sum('sha256' in row for row in manifest.values()),'failed',sum('sha256' not in row for row in manifest.values()),flush=True)


if __name__=='__main__':main()
