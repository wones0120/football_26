"""Preserve and import the exact user files, verified against official public pools."""
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv,hashlib,json,requests

ROOT=Path(__file__).resolve().parent
NOW=datetime.now(UTC)
scopes=json.loads((ROOT/'verified_scope.json').read_text())
manifest=[]
for metadata,file,variant in zip(scopes,['DKSalaries_2026_6_SUNDAY_NIGHT_SINGLE_STAT_YARDS.csv','DKSalaries_2026_6_SUNDAY_MAIN_SINGLE_STAT_TDS.csv'],['total_yards','touchdowns']):
    source=Path('/Users/wones/NFL')/file;raw=source.read_bytes();snapshot=ROOT/file
    if snapshot.exists() and snapshot.read_bytes()!=raw:raise ValueError('Immutable source copy conflict')
    if not snapshot.exists():snapshot.write_bytes(raw)
    rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    group=metadata['draft_group'];gs=metadata['game_set'];dg=group['DraftGroupId'];draftables=json.loads((ROOT/f'group_{dg}_draftables.json').read_text())['draftables']
    ids={r['ID'] for r in rows}
    assert ids=={str(d['draftableId']) for d in draftables}
    games=[];game_ids={}
    for g in gs['Competitions']:
        if g['Status']!='Pre-Game' or g['ExceptionalMessages']:raise ValueError('Provider schedule requires review')
        matching=[info for info in {r['Game Info'] for r in rows} if info.split(' ')[0]==g['Description'].replace(' ','')]
        assert len(matching)==1
        game_ids[matching[0]]=str(g['GameId'])
        games.append(dict(game_id=str(g['GameId']),teams=matching[0].split(' ')[0].split('@'),original_start_at=g['StartDate'],scheduled_start_at=g['StartDate'],provider_status='confirmed',provider_observed_at=datetime.fromtimestamp((ROOT/'public_lobby.json').stat().st_mtime,UTC).isoformat(),provider_source='Official public DraftKings NFL lobby GameSets: '+gs['GameSetKey']))
    assert len(game_ids)==len({r['Game Info'] for r in rows})
    evidence={str(d['draftableId']):dict(status=d['status'],disabled=d['isDisabled'],source_reference=metadata['public_source'],observed_at=datetime.fromtimestamp((ROOT/f'group_{dg}_draftables.json').stat().st_mtime,UTC).isoformat()) for d in draftables}
    end=datetime(2026,10,21,23,59,tzinfo=ZoneInfo('America/New_York')).astimezone(UTC)
    package=dict(contest_format='single_stat',variant=variant,game_set_id=gs['GameSetKey'],season=2026,week=6,
        source_name=file,source_reference=str(source)+'; verified official draft group '+str(dg)+' '+metadata['types'][0],
        source_observed_at=NOW.isoformat(),source_file_observed_at=datetime.fromtimestamp(source.stat().st_mtime,UTC).isoformat(),scoring_period_end_at=end.isoformat(),scoring_period_source='Supplied NFL Single Stat rules: first Wednesday 23:59 Eastern after final scheduled game; no adjustment indicated in captured public provider metadata',
        contest_status='active',games=games,native_game_ids=game_ids,player_evidence=evidence,native_csv=raw.decode('utf-8'),columns=dict(source_player_id='ID',name='Name',team='TeamAbbrev',game_id='Game Info'),evaluation_id='official_native_20261016_v2_exact_source_clocks')
    (ROOT/(variant+'_package.json')).write_text(json.dumps(package,indent=2))
    response=requests.post('http://127.0.0.1:8000/api/single-stat/pools',json=package,timeout=180)
    response.raise_for_status();pool=response.json();(ROOT/(variant+'_import_response.json')).write_text(json.dumps(pool,indent=2))
    manifest.append(dict(variant=variant,draft_group_id=dg,game_set_id=gs['GameSetKey'],source=str(source),source_sha256=hashlib.sha256(raw).hexdigest(),rows=len(rows),pool_sha256=pool['sha256'],identity_resolved=sum(bool(p['player_master_id']) for p in pool['players']),status=pool['current_readiness']['status'],reason_codes=pool['current_readiness']['reason_codes']))
    print(json.dumps(manifest[-1]),flush=True)
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
