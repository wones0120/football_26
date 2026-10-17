from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,collections
import pandas as pd
from backend.app.product_services.dst_scoring_reconciliation import score_game,apply_research_corrections,DstScoringUnresolved
from backend.app.product_services.optimizer import _json_safe
from Database.dst import normalize_team
P=Path(__file__).resolve().parent;old=Path('research/opponent_qb_context_20261015/v1');schedule=json.load(open(old/'schedule.json'))['rows'];bygame={r['game_id']:r for r in schedule};results=[];errors=[];identity=[];original=json.load(open(old/'dst_matrix.json'))['rows'];id_sets=collections.defaultdict(set)
for r in original:id_sets[normalize_team(r['team'])].add(r['player_master_id'])
assert all(len(v)==1 for v in id_sets.values());canonical_ids={k:next(iter(v)) for k,v in id_sets.items()}
for year in [2024,2025,2026]:
 path=P/f'play_by_play_{year}.parquet';sha=hashlib.sha256(path.read_bytes()).hexdigest();f=pd.read_parquet(path)
 for gid,g in f.groupby('game_id',sort=True):
  s=bygame.get(gid);first=g.iloc[0];h=normalize_team(first.home_team);a=normalize_team(first.away_team)
  # Only the captured historical matrix needs prior years; all2026completed games audited.
  if not s:errors.append(dict(game_id=gid,reason='Independent canonical schedule missing'));continue
  raw=s['raw_row_json'];valid=normalize_team(s['home_team'])==h and normalize_team(s['away_team'])==a and str(raw.get('gameday'))==str(first.game_date)
  if not valid:errors.append(dict(game_id=gid,reason='Independent game/team/date mismatch'));continue
  score=None
  if raw.get('home_score') is not None and raw.get('away_score') is not None:score={h:raw['home_score'],a:raw['away_score']}
  try:
   rows=score_game(g.to_dict('records'),expected_game_id=gid,expected_teams=[h,a],canonical_player_ids=canonical_ids,expected_score=score)
   for r in rows:r.update(season=year,week=int(first.week),source_sha256=sha,source_file=str(path),source_kind='nflverse_pbp',game_date=str(first.game_date),independent_schedule_score_verified=score is not None)
   results.extend(rows);identity.append(dict(game_id=gid,team_date_verified=True,score_verified=score is not None))
  except DstScoringUnresolved as exc:errors.append(dict(game_id=gid,reason=str(exc)))
original=json.load(open(old/'dst_matrix.json'))['rows'];corrected=apply_research_corrections(original,results);corrected.update(created_at=datetime.now(UTC).isoformat(),original_dataset_sha256=hashlib.sha256((old/'dst_matrix.json').read_bytes()).hexdigest(),source_code_sha256=hashlib.sha256(Path('backend/app/product_services/dst_scoring_reconciliation.py').read_bytes()).hexdigest())
(P/'corrected_dst_matrix.json').write_text(json.dumps(_json_safe(corrected),indent=2,allow_nan=False)+'\n');(P/'scored_games.json').write_text(json.dumps(_json_safe(results),indent=2,allow_nan=False)+'\n');(P/'source_validation.json').write_text(json.dumps(dict(game_identity=identity,unresolved_games=errors),indent=2)+'\n')
print('source games',len(identity),'unresolved',len(errors));print(collections.Counter(e['reason'] for e in errors));print('matrix',len(corrected['rows']),collections.Counter(r['status'] for r in corrected['receipts']))
for y in [2024,2025,2026]:print(y,collections.Counter(r['status'] for r in corrected['receipts'] if str(r.get('game_id','')).startswith(str(y))))
print('first errors',errors[:10])
