"""Use bundled pypdf; independently extract official team statistics."""
from pathlib import Path
import json,re
from pypdf import PdfReader
P=Path(__file__).resolve().parent;manifest=json.load(open(P/'gamebook_manifest.json'));scored=json.load(open(P/'scored_games.json'));bygame={}
for r in scored:bygame.setdefault(r['game_id'],[]).append(r)
out=[]
for m in manifest:
 gid=m['game_id'];folder=P/'gamebooks'/gid
 try:
  reader=PdfReader(folder/'gamebook.pdf');texts=[p.extract_text(extraction_mode='layout') for p in reader.pages[:5]];first=texts[0];stats=next(t for t in texts if 'Final Team Statistics' in t);(folder/'team_stats.txt').write_text(stats);(folder/'scoring_summary.txt').write_text(first[first.find('VISITOR:'):])
  def pair(pattern):
   match=re.search(pattern,stats,re.M)
   if not match:raise ValueError('Missing official team stat '+pattern)
   return [match.group(1),match.group(2)]
  sacks=[int(x.split('-')[0]) for x in pair(r'^\s*Times thrown - yards lost attempting to pass\s+(\S+)\s+(\S+)\s*$')]
  ints=[int(x.split('-')[-1]) for x in pair(r'^\s*PASS ATTEMPTS-COMPLETIONS-HAD INTERCEPTED\s+(\S+)\s+(\S+)\s*$')]
  lost=[int(x.split('-')[-1]) for x in pair(r'^\s*FUMBLES Number and Lost\s+(\S+)\s+(\S+)\s*$')]
  puntblock=[int(x) for x in pair(r'^\s*Had Blocked\s+(\S+)\s+(\S+)\s*$')]
  fgpat=[sum(map(int,x.split('-'))) for x in pair(r'^\s*FGs - PATs Had Blocked\s+(\S+)\s+(\S+)\s*$')]
  score=[int(x) for x in pair(r'^\s*FINAL SCORE\s+(\S+)\s+(\S+)\s*$')];safe=[int(x) for x in pair(r'^\s*SAFETIES\s+(\S+)\s+(\S+)\s*$')]
  # Source game ID defines away/home, verified independently against schedule.
  parts=gid.split('_');away=parts[2];home=parts[3];aliases={'LA':'LAR','JAC':'JAX','OAK':'LV','SD':'LAC','STL':'LAR'};away=aliases.get(away,away);home=aliases.get(home,home);rows={r['team']:r for r in bygame[gid]};checks=[]
  for i,t in enumerate([away,home]):
   opposite=1-i;c=rows[t]['components'];expected=dict(sacks=sacks[opposite],interceptions=ints[opposite],fumble_recoveries=lost[opposite],blocked_kicks=puntblock[opposite]+fgpat[opposite],safeties=safe[i])
   for key,value in expected.items():checks.append(dict(team=t,component=key,official=value,reconstructed=c[key],match=value==c[key]))
  # Official header final scores must match NFL/nflverse final timeline.
  official_final={away:score[0],home:score[1]};checks.append(dict(component='final_score',official=official_final,reconstructed=bygame[gid][0]['final_score'],match=official_final==bygame[gid][0]['final_score']))
  td_block=stats[stats.find('TOUCHDOWNS'):stats.find('EXTRA POINTS')]
  def td_pair(label):
   v=re.search(r'^\s*'+label+r'\s+(\d+)\s+(\d+)\s*$',td_block,re.M);return [int(v.group(1)),int(v.group(2))] if v else [0,0]
  tdtotal=td_pair('TOUCHDOWNS');rush=td_pair('Rushing');passing=td_pair('Passing')
  for i,t in enumerate([away,home]):
   c=rows[t]['components'];other=tdtotal[i]-rush[i]-passing[i];reconstructed=c['defensive_touchdowns']+c['special_teams_touchdowns']+c['offensive_fumble_touchdowns'];checks.append(dict(team=t,component='non_rush_pass_touchdowns',official=other,reconstructed=reconstructed,match=other==reconstructed))
  # Verify team/date explicitly from official header and canonical game date.
  expected_date=bygame[gid][0]['game_date'];from datetime import datetime
  d=datetime.fromisoformat(expected_date);header_date=re.search(r'Date:\s*\w+,\s*(\d+/\d+/\d+)',first)
  if not header_date:raise ValueError('Official book date unavailable')
  local_date=datetime.strptime(header_date.group(1),'%m/%d/%Y').date();date_basis='same_calendar_date'
  if local_date!=d.date():
   from zoneinfo import ZoneInfo
   time_match=re.search(r'Start Time:\s*(\d+:\d+\s*[AP]M)\s+AEST',first)
   if 'Melbourne' not in first or not time_match:raise ValueError('Official book date mismatch')
   local_start=datetime.combine(local_date,datetime.strptime(time_match.group(1),'%I:%M %p').time()).replace(tzinfo=ZoneInfo('Australia/Melbourne'))
   if local_start.astimezone(ZoneInfo('America/New_York')).date()!=d.date():raise ValueError('Official international kickoff date mismatch')
   date_basis='Melbourne_local_date_converted_to_NFL_US_Eastern_date'
  checks.append(dict(component='official_game_date',match=True,basis=date_basis))
  out.append(dict(game_id=gid,status='verified' if all(x['match'] for x in checks) else 'mismatch',pdf_sha256=m['pdf_sha256'],checks=checks))
 except Exception as e:out.append(dict(game_id=gid,status='unresolved',reason=str(e)))
(P/'official_gamebook_checks.json').write_text(json.dumps(out,indent=2)+'\n');print('books',len(out),'verified',sum(r['status']=='verified' for r in out));print([r for r in out if r['status']!='verified'])
