"""Immutable research captures of public nflverse release assets. No DB writes."""
from datetime import datetime,timezone
import hashlib,json,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCES=HERE/'sources'
BASE='https://github.com/nflverse/nflverse-data/releases/download/'
ASSETS={'players.parquet':'players/players.parquet','games.parquet':'schedules/games.parquet'}
for year in [2023,2024,2025,2026]:
 ASSETS[f'snaps_{year}.parquet']=f'snap_counts/snap_counts_{year}.parquet'
 ASSETS[f'pbp_{year}.parquet']=f'pbp/play_by_play_{year}.parquet'

def capture():
 SOURCES.mkdir(exist_ok=True)
 manifest_path=SOURCES/'manifest.json'
 manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
 for filename,asset in ASSETS.items():
  path=SOURCES/filename
  if path.exists():
   digest=hashlib.sha256(path.read_bytes()).hexdigest()
   if filename not in manifest or manifest[filename]['sha256']!=digest:raise ValueError('Untracked/changed source: '+filename)
   print('Verified',filename,flush=True);continue
  url=BASE+asset
  req=urllib.request.Request(url,headers={'User-Agent':'football26-research/1.0'})
  try:
   with urllib.request.urlopen(req,timeout=60) as response:
    content=response.read();headers=dict(response.headers)
  except Exception as error:
   if filename not in {'snaps_2026.parquet','pbp_2026.parquet'}:raise
   failures=SOURCES/'optional_unavailable.json'
   missing=json.loads(failures.read_text()) if failures.exists() else {}
   missing[filename]={'url':url,'checked_at':datetime.now(timezone.utc).isoformat(),'error':str(error)}
   failures.write_text(json.dumps(missing,indent=2)+'\n')
   print('Optional source unavailable',filename,str(error),flush=True);continue
  with path.open('xb') as output:output.write(content)
  manifest[filename]={'url':url,'received_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'http_last_modified':headers.get('Last-Modified'),'etag':headers.get('ETag'),'usage':'revised historical data; capture clock not contemporaneous game evidence'}
  manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
  print('Captured',filename,len(content),'bytes',flush=True)
if __name__=='__main__':capture()
