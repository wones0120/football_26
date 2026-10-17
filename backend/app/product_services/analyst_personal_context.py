"""Version-bound personal hypotheses for Analyst evidence review, never model truth."""
from copy import deepcopy

from .analyst_packets import clock, packet_digest
from .analyst_shadow import digest
from .market_snapshots import canonical_team

CONTRACT = 'analyst_personal_context_v1'


def load_inputs(engine):
    """One immutable snapshot of current beliefs and their latest preview decision."""
    from sqlalchemy import text
    with engine.begin() as connection:
        rows = connection.execute(text('''
            WITH current AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY belief_id ORDER BY belief_version DESC) AS rn
                FROM target.human_belief
            )
            SELECT b.*, p.preview_id, p.modifier_json, p.season AS approval_season,
                   p.week AS approval_week, p.slate AS approval_slate,
                   p.contest_format AS approval_contest_format, p.objective AS approval_objective,
                   d.decision_id, d.decision, d.created_at AS decided_at
            FROM current b
            LEFT JOIN LATERAL (
                SELECT * FROM target.belief_impact_preview p
                WHERE p.belief_version_id=b.belief_version_id
                  AND p.policy_id='analyst_personal_context_v1'
                ORDER BY p.created_at DESC, p.preview_id DESC LIMIT 1
            ) p ON true
            LEFT JOIN target.belief_impact_decision d ON d.preview_id=p.preview_id
            WHERE b.rn=1 ORDER BY b.belief_id
        ''')).mappings().all()
    return [dict(row) for row in rows]


def evaluate(inputs, *, scope, games, checked_at, packet=None):
    """Review only approved exact versions; copy authored scenario evidence verbatim."""
    now = clock(checked_at)
    report = dict(contract_id=CONTRACT, checked_at=checked_at, considered=[], rejected=[],
                  baseline_mutation=False, affected_construction=False, changed_selected_rosters=False, packet_sha256=packet_digest(packet) if packet else None)
    scoped_teams = {canonical_team(t) for g in games for t in (g.get('teams') or [g.get('home_team'), g.get('away_team')]) if t}
    for row in inputs:
        item = {k: row.get(k) for k in ('belief_id','belief_version_id','belief_version','source','preview_id','decision_id')}
        reasons=[]
        if packet is None: reasons.append('no_checked_analyst_packet')
        if row.get('status')!='active': reasons.append('inactive')
        if row.get('is_retrospective'): reasons.append('retrospective_not_forward_evidence')
        if row.get('expires_at') and clock(str(row['expires_at'])) <= now: reasons.append('expired')
        if row.get('created_at') and clock(str(row['created_at'])) > now: reasons.append('future_belief')
        for key in ('season','week','slate','contest_format','objective'):
            expected=row.get(key); actual=scope.get(key)
            if expected is not None and (actual is not None and str(expected).upper()!=str(actual).upper()): reasons.append('wrong_'+key)
        modifier=row.get('modifier_json') or {}
        if row.get('decision')!='approved' or modifier.get('modifier_type')!='analyst_context_review': reasons.append('no_current_version_context_approval')
        if row.get('decided_at') and clock(str(row['decided_at']))>now: reasons.append('future_approval')
        for key in ('season','week','slate','contest_format','objective'):
            expected=row.get('approval_'+key)
            if row.get('decision')=='approved' and expected is not None and scope.get(key) is not None and str(expected).upper()!=str(scope.get(key)).upper():reasons.append('approval_wrong_'+key)
        team=modifier.get('team')
        if team not in scoped_teams: reasons.append('team_not_in_slate')
        declared=row.get('metadata_json') or row.get('metadata') or {}
        if declared.get('resolved_team') and declared['resolved_team']!=team:reasons.append('wrong_resolved_team')
        if declared.get('canonical_game_id') and declared['canonical_game_id'] not in {g['game_id'] for g in games}:reasons.append('wrong_canonical_game')
        if reasons:
            report['rejected'].append(dict(**item,reasons=reasons));continue
        hypotheses=[h for h in (packet or {}).get('hypotheses',[]) if any(p.get('team')==team and p.get('player_master_id') in h.get('player_master_ids',[]) for p in (packet or {}).get('players',[]))]
        scenarios=[s for s in ((packet or {}).get('scenario_assumptions') or {}).get('scenarios',[]) if any(a.get('team')==team for a in s.get('assumptions',[]))]
        report['considered'].append(dict(**item, thought_text=row['thought_text'], expires_at=str(row.get('expires_at') or ''),
            resolved_scope=dict(**{**scope,'objective':row.get('approval_objective')},team=team,game_ids=[g['game_id'] for g in games if team in [canonical_team(t) for t in (g.get('teams') or [g.get('home_team'),g.get('away_team')]) if t]]),
            interpreted_action='review_conditional_mechanism', status='read_qualitative_only',
            evidence_assessment='unverified_user_hypothesis',
            conditional_mechanism=modifier.get('conditional_mechanism'),
            supporting_evidence=[dict(hypothesis_id=h['hypothesis_id'],text=deepcopy(h.get('supporting_evidence')),source_ids=h.get('source_ids',[])) for h in hypotheses],
            challenging_evidence=[dict(hypothesis_id=h['hypothesis_id'],text=deepcopy(h.get('contrary_evidence')),source_ids=h.get('source_ids',[])) for h in hypotheses],
            evidence_limitation='Team-linked research is context, not independent confirmation of this personal hypothesis. No independently verified measurement or calibrated operation for the personal mechanism is supplied.',
            related_scenario_ids=[s['scenario_id'] for s in scenarios], applied_scenario_ids=[],
            not_applied_reason='Approval authorizes qualitative evidence review only. No separately approved typed scenario effect; prose supplies no coefficients.',
            affected_construction=False, changed_selected_rosters=False))
    report['sha256']=digest(report)
    return report


def validate_current(report, inputs, *, checked_at):
    """Fail closed on revision, revocation, or expiry after preparation."""
    current={r['belief_version_id']:r for r in inputs}
    for item in report.get('considered',[]):
        row=current.get(item['belief_version_id'])
        if not row or row.get('status')!='active' or row.get('decision')!='approved' or row.get('decision_id')!=item['decision_id'] or (row.get('expires_at') and clock(str(row['expires_at']))<=clock(checked_at)):
            raise ValueError('Personal thought approval changed or expired; Prepare Slate again')
