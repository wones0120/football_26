"""Read-only returned-shortlist replay; never regenerate historical forecasts."""
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.gpp_historical_audit import freeze_choice, field_outcome, digest
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player, candidate_signature, score_signature
from scripts.audit_weekly_validation import AUDIT_PLAYER_KEYS
from scripts.shadow_single_gpp_shortlist import wr_rb_captain_allowed


def run(c, prior):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    history,_,_=load_history(c)
    results=[]
    for block in prior['blocks']:
        if block['contest_format']!='showdown': continue
        primary=block['primary_run']
        row=dict(week=block['week'],slate=block['slate'])
        if primary is None:
            results.append(dict(row,status='unavailable',reason='no_clock_eligible_replay',gaps=block['gaps']));continue
        rid=primary['run_id']
        source=dict(c.execute(text('SELECT optimizer_run_id,projection_run_id,season,week,slate_id,contest_format,data_cutoff_at FROM target.optimizer_run WHERE optimizer_run_id=:id'),{'id':rid}).mappings().one())
        lineups=[]
        for lid in c.execute(text('SELECT lineup_id FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number'),{'id':rid}).scalars():
            lineups.append(list(c.execute(text('SELECT (SELECT jsonb_object_agg(key,value) FROM jsonb_each(player_json) WHERE key=ANY(:keys)) FROM target.lineup_player WHERE lineup_id=:id ORDER BY slot_index'),{'id':lid,'keys':AUDIT_PLAYER_KEYS}).scalars()))
        if digest(lineups)!=primary['candidate_snapshot_sha256']: raise ValueError('Saved shortlist changed since timing audit')
        original=freeze_choice(source,lineups)
        if original['recommended']['candidate_id']!=primary['selected']['candidate_id']: raise ValueError('Baseline parity failed')
        # Filter before reading any outcome labels. No fallback to a rule-breaking lineup.
        allowed=[r for r in lineups if wr_rb_captain_allowed(r)]
        choice=freeze_choice(source,allowed)
        row.update(run_id=rid,total_candidates=len(lineups),qualifying_candidates=len(allowed))
        if not choice['recommended']:
            results.append(dict(row,status='unavailable',reason='no_valid_qualifying_returned_candidate'));continue
        arms={'control':lineups[original['recommended']['lineup_number']-1], 'wr_rb_captain':allowed[choice['recommended']['lineup_number']-1]}
        contests=enrich_contests([dict(r) for r in c.execute(text("SELECT * FROM target.dfs_contest WHERE season=2026 AND week=:week AND slate_id=:slate AND contest_format='showdown'"),row).mappings()],history)
        observations=[];hist={};tiers={}
        for ct in contests:
            cid=str(ct['contest_id'])
            observations.extend(dict(r) for r in c.execute(text('SELECT player_id,roster_position,actual_points,resolution_status FROM target.contest_ownership_observation WHERE contest_id=:id'),{'id':cid}).mappings())
            hist[cid]=[dict(r) for r in c.execute(text('SELECT entry_points,count(*) AS entries FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY entry_points'),{'id':cid}).mappings()]
            tiers[cid]=[dict(r) for r in c.execute(text('SELECT min_rank,max_rank,payout FROM target.dfs_contest_payout_tier WHERE contest_id=:id'),{'id':cid}).mappings()]
        actuals=actual_points_by_player(observations,'showdown');scored={}
        for label,roster in arms.items():
            points,missing=score_signature(candidate_signature({'players':roster},'showdown'),actuals)
            outcomes=[field_outcome(points,ct,hist[str(ct['contest_id'])],tiers[str(ct['contest_id'])]) for ct in contests]
            outcomes=[o for o in outcomes if o['classification']['contest_type']=='gpp']
            scored[label]=dict(roster=roster,actual_points=points,missing=missing,outcomes=outcomes,paid=sum(o['paid_finish'] is True for o in outcomes),known=sum(o['paid_finish'] is not None for o in outcomes))
        row.update(status='replayed',arms=scored,changed=choice['recommended']['candidate_id']!=original['recommended']['candidate_id'])
        results.append(row)
    return dict(policy='wr_rb_captain_shadow_v1',scope='latest clock-eligible saved returned shortlist per slate; no fresh generation or hidden-pool reconstruction',results=results,live_selection_changed=False)


if __name__=='__main__':
    prior=json.loads(Path('artifacts/weekly_validation_2026_w1_w4/final/report.json').read_text())
    with engine.connect() as c: report=run(c,prior)
    p=Path('artifacts/wr_rb_captain_shadow/historical.json');p.write_text(json.dumps(report,indent=2,default=str)+'\n')
    for row in report['results']:
        print(row['week'],row['slate'],row['status'],row.get('reason',''),row.get('qualifying_candidates'),[(k,a['actual_points'],a['paid'],a['known']) for k,a in row.get('arms',{}).items()])
