"""Immutable frozen-lineup comparisons, refreshed automatically by result imports."""
from datetime import datetime, timezone
import json
import logging

from sqlalchemy import text

from .entry_history import enrich_contests, load_history
from .gpp_historical_audit import digest, field_outcome
from .optimizer_effectiveness import actual_points_by_player, candidate_signature, score_signature


def evaluate_snapshot(snapshot, observations, contests, histograms, tiers):
    """Only canonical outcome joins; never rerank or regenerate a frozen choice."""
    fmt = snapshot['contest_format']
    actuals = actual_points_by_player(observations, fmt)
    arms = []
    for label, arm in snapshot['arms'].items():
        roster = arm['roster']
        signature = candidate_signature({'players': roster}, fmt)
        if signature is None:
            raise ValueError('Invalid frozen canonical roster')
        points, missing = score_signature(signature, actuals)
        player_errors = []
        for player_id, captain in signature:
            saved = next(p for p in roster if p['player_id'] == player_id)
            actual = actuals.get(player_id)
            if actual is not None and captain:
                actual *= 1.5
            forecast = saved.get('projection')
            player_errors.append(dict(player_id=player_id, captain=captain,
                forecast_points=forecast, actual_points=actual,
                error=None if actual is None or forecast is None else round(actual-float(forecast), 2)))
        outcomes = [field_outcome(points, c, histograms.get(str(c['contest_id']), []),
                                  tiers.get(str(c['contest_id']), [])) for c in contests]
        outcomes = [c for c in outcomes if c['classification']['contest_type'] == 'gpp']
        arms.append(dict(label=label, actual_points=points, missing_player_ids=missing,
                         forecast_points=arm['forecast_points'], contests=outcomes,
                         projection_error=None if points is None else round(points-arm['forecast_points'], 2),
                         player_projection_errors=player_errors,
                         known_paid_finishes=sum(c['paid_finish'] is True for c in outcomes),
                         known_non_paid_finishes=sum(c['paid_finish'] is False for c in outcomes),
                         unknown_finishes=sum(c['paid_finish'] is None for c in outcomes)))
    status = ('pending_actuals' if any(a['missing_player_ids'] for a in arms) else
              'pending_contest_evidence' if any(not a['contests'] or a['unknown_finishes'] for a in arms) else
              'evaluated_from_imports')
    used_ids = {p['player_id'] for arm in snapshot['arms'].values() for p in arm['roster']}
    frozen_evidence = sorted([dict(row) for row in observations if row.get('player_id') in used_ids], key=digest)
    return dict(status=status, arms=arms, actual_evidence=frozen_evidence,
                interpretation='Counterfactual placement against imported fields, not entered-lineup winnings. Imported standings may be provisional; this does not certify game finality or promote a model.',
                live_selection_changed=False)


class ShadowLearningService:
    def __init__(self, engine):
        self.engine = engine

    def register(self, snapshot):
        # Registration is explicit and idempotent; never discover arbitrary files.
        fmt = snapshot['contest_format']
        if fmt not in {'classic', 'showdown'} or not snapshot['arms']:
            raise ValueError('Unsupported or empty shadow snapshot')
        lock = datetime.fromisoformat(snapshot['first_kickoff_at'])
        now = datetime.now(timezone.utc)
        if lock.tzinfo is None or now >= lock:
            raise ValueError('Prospective registration must precede the first kickoff')
        for arm in snapshot['arms'].values():
            completed = datetime.fromisoformat(arm['completed_at'])
            if completed.tzinfo is None or completed >= lock or completed > now:
                raise ValueError('Shadow completion must precede registration and kickoff')
            if candidate_signature({'players': arm['roster']}, fmt) is None:
                raise ValueError('Invalid frozen canonical roster')
        sha = digest(snapshot)
        with self.engine.begin() as c:
            c.execute(text('''INSERT INTO target.gpp_shadow_experiment
                (experiment_id,season,week,slate,contest_format,snapshot_json)
                VALUES (:id,:season,:week,:slate,:fmt,CAST(:snapshot AS JSONB)) ON CONFLICT DO NOTHING'''),
                dict(id=sha, season=snapshot['season'], week=snapshot['week'], slate=snapshot['slate'],
                     fmt=fmt, snapshot=json.dumps(snapshot,allow_nan=False)))
        self.refresh(season=snapshot['season'],week=snapshot['week'],slate=snapshot['slate'])
        return sha

    def refresh(self, *, season=None, week=None, slate=None):
        with self.engine.begin() as c:
            snapshots = c.execute(text('''SELECT experiment_id,snapshot_json FROM target.gpp_shadow_experiment
                WHERE (CAST(:season AS INTEGER) IS NULL OR season=:season) AND (CAST(:week AS INTEGER) IS NULL OR week=:week)
                AND (CAST(:slate AS TEXT) IS NULL OR upper(slate)=upper(:slate)) ORDER BY registered_at'''),
                dict(season=season,week=week,slate=slate)).mappings().all()
            if not snapshots:
                return 0
            history, conflicts, sources = load_history(c)
            for row in snapshots:
                c.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key':row['experiment_id']})
                snapshot = row['snapshot_json']
                scope = dict(season=snapshot['season'],week=snapshot['week'],slate=snapshot['slate'],fmt=snapshot['contest_format'])
                contests = enrich_contests([dict(r) for r in c.execute(text('''SELECT * FROM target.dfs_contest
                    WHERE season=:season AND week=:week AND upper(slate_id)=upper(:slate) AND contest_format=:fmt'''),scope).mappings()],history)
                histograms, tiers, observations = {}, {}, []
                for contest in contests:
                    cid = str(contest['contest_id'])
                    histograms[cid] = [dict(r) for r in c.execute(text('''SELECT entry_points,count(*) entries FROM target.dfs_contest_entry_result
                        WHERE contest_id=:id GROUP BY entry_points ORDER BY entry_points'''),dict(id=cid)).mappings()]
                    tiers[cid] = [dict(r) for r in c.execute(text('SELECT min_rank,max_rank,payout FROM target.dfs_contest_payout_tier WHERE contest_id=:id ORDER BY min_rank'),dict(id=cid)).mappings()]
                    observations.extend(dict(r) for r in c.execute(text('''SELECT observation_id,source_file_id,player_id,roster_position,actual_points,resolution_status
                        FROM target.contest_ownership_observation WHERE contest_id=:id'''),dict(id=cid)).mappings())
                result = evaluate_snapshot(snapshot, observations, contests, histograms, tiers)
                result['entry_history_conflicts'] = conflicts
                result['source_history_hashes'] = [s['content_sha256'] for s in sources]
                result['experiment_id'] = row['experiment_id']
                result = json.loads(json.dumps(result,default=str,allow_nan=False))
                previous = c.execute(text('SELECT report_id,report_json FROM target.gpp_shadow_report WHERE experiment_id=:id ORDER BY created_at DESC,report_id DESC LIMIT 1'), {'id':row['experiment_id']}).mappings().first()
                if previous and previous['report_json'] == result:
                    continue
                report_id = digest([previous['report_id'] if previous else None, result])
                c.execute(text('''INSERT INTO target.gpp_shadow_report(report_id,experiment_id,status,report_json,created_at)
                    VALUES (:id,:experiment,:status,CAST(:report AS JSONB),clock_timestamp()) ON CONFLICT DO NOTHING'''),
                    dict(id=report_id,experiment=row['experiment_id'],status=result['status'],report=json.dumps(result,default=str,allow_nan=False)))
        return len(snapshots)

    def latest(self, season, week):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(text('''SELECT e.experiment_id,e.slate,e.contest_format,e.registered_at,
                e.snapshot_json->>'label' AS label,r.created_at AS evaluated_at,r.report_json
                FROM target.gpp_shadow_experiment e LEFT JOIN LATERAL
                (SELECT * FROM target.gpp_shadow_report WHERE experiment_id=e.experiment_id ORDER BY created_at DESC,report_id DESC LIMIT 1) r ON TRUE
                WHERE e.season=:season AND e.week=:week ORDER BY e.registered_at'''),dict(season=season,week=week)).mappings()]


def refresh_after_import(engine, **scope):
    """An import is already committed; report failures must remain visible to callers."""
    try:
        count = ShadowLearningService(engine).refresh(**scope)
        return f'Shadow comparisons refreshed: {count}.'
    except Exception:
        logging.getLogger(__name__).exception('Automatic shadow comparison failed')
        return 'Shadow comparison refresh failed; retry from Learning after resolving the logged error.'
