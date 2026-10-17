from urllib.request import Request,urlopen
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
p=Path(__file__).resolve().parent;dest=p/'NE_oct13_primary.html'
if dest.exists():raise SystemExit('Immutable capture already exists')
uri='https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-oct-13'
observed=datetime.now(timezone.utc).isoformat()
with urlopen(Request(uri,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:data=r.read();resolved=r.url
dest.write_bytes(data);(p/'NE_oct13_primary.json').write_text(json.dumps({'source_id':'NE_oct13_primary','uri':uri,'resolved_uri':resolved,'coverage':'verified','observed_at':observed,'available_at':observed,'published_at':None,'publication_clock_note':'Oct13display; no verified publicationtimezone','capture_sha256':hashlib.sha256(data).hexdigest(),'capture_kind':'raw_http_html'},indent=2)+'\n');print(observed,len(data))
