from pathlib import Path
import json
from backend.app.product_services.official_injuries import _Document,parse_official_report
P=Path(__file__).resolve().parent
snap=json.loads(Path('artifacts/preliminary_optimizer_snapshots/6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a.json').read_text());rows=snap['pool']
for f in P.glob('official_*.html'):
 doc=_Document(f.read_text()).root;out=[]
 for table in doc.find('table'):
  body=[]
  for tr in table.find('tr'):
   cells=list(tr.find('th')) or list(tr.find('td'))
   body.append([c.content() for c in cells])
  out.append(body)
 if out:(P/(f.stem+'_tables.json')).write_text(json.dumps(out,indent=2)+'\n')
for g in snap['source_manifest']['games']:
 rs=[r for r in rows if r.get('canonical_game_id')==g['game_id']];print('\n',g['game_id'])
 for t in [g['away_team'],g['home_team']]:
  rr=[r for r in rs if r['player_team']==t and r.get('projection') is not None and r['position']!='DST'];rr.sort(key=lambda r:-r['projection']);one=rr[0];print(t,'total',one.get('game_total_line'),'spread',one.get('team_spread_line'),'implied',one.get('team_implied_total'))
  print('; '.join(f"{r['name']} {r['position']} ${r['salary']} {r['projection']:.2f} {r.get('official_availability_status')}" for r in rr[:8]))
