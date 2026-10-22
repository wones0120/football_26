"""Scoped Sunday amendment; no raw, historical or saved-result edits."""
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.evaluation_record import append_record
from backend.app.product_services.official_injuries import resolve_official_player
r=Path(__file__).parent
before=json.loads((r/'sills_before.json').read_text());previous=json.loads(Path('artifacts/all_source_repair_20261022/sills_identity_amendment.json').read_text())
old=previous['old_vendor_id'];new=previous['canonical_id'];salary=before['salary'];assert len(salary)==1
s=salary[0];assert s['player_master_id']==old and (s['source_player_key'],s['team'],s['position'])==('44557506','TB','WR')
with engine.begin() as c:
 aliases=[dict(x) for x in c.execute(text("select * from player_alias where (source_system='draftkings' and source_key=:native) or (source_system='nflreadpy' and source_key='00-0035359') or (source_system='nfl_official' and source_key='/players/david-sills')"),dict(native=s['source_player_key'])).mappings()]
 assert all(a['player_master_id']==new for a in aliases if a['source_system']!='draftkings')
 changed=[a for a in aliases if a['source_system']=='draftkings'];assert len(changed)==1 and changed[0]['player_master_id']==old
 roster=[dict(x) for x in c.execute(text("select raw_nfl_weekly_roster_id,gsis_id,team,position from raw_nfl_weekly_roster where season=2026 and week=7 and gsis_id='00-0035359' and team='TB' and position='WR'")).mappings()];assert roster
 assert c.execute(text('update curated_salary set player_master_id=:new where curated_salary_id=:id and player_master_id=:old'),dict(new=new,id=s['curated_salary_id'],old=old)).rowcount==1
 assert c.execute(text('update player_alias set player_master_id=:new where alias_id=:id and player_master_id=:old'),dict(new=new,id=changed[0]['alias_id'],old=old)).rowcount==1
 p=dict(scope=dict(season=2026,week=7,slate='SUNDAY_MAIN'),operation='extend_retained_source_identity_correction',parent_record_id=previous['record_id'],canonical_id=new,old_vendor_id=old,salary_before=salary,aliases_before=changed,stable_native_evidence=aliases,roster_evidence=roster,official_activation_snapshot_id=previous['official_activation_snapshot_id'],raw_rows_changed=0,historical_aliases_changed=0,masters_merged=0,status_changed=False,reason='Official native profile and stable NFL GSIS bind TB WR canonical actor; Sunday vendor salary retained the duplicate corrected separately in ALL. Original salary IR flag preserved; activation is not game-day clearance.')
 record=append_record(c,'current_vendor_identity_correction',p,source=str(r/'sills_before.json'))
 (r/'sills_amendment.json').write_text(json.dumps(dict(record_id=record,**p),default=str,indent=2))
 salaries=[dict(player_id=new,team='TB',position='WR',player_name=s['player_name'],full_name=s['player_name'])]
 assert resolve_official_player(dict(team='TB',position='WR',source_key='/players/david-sills',player_name='David Sills'),salaries,aliases)==(new,'source_native_id')
print('One Sunday salary and one current vendor alias corrected:',record)
