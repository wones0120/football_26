"""One factual game designation, separate from roster membership and preferences.

Only the versioned official final-report producer can express an affirmative
no-designation fact. A blank salary/injury cell and ACT roster never clear Q.
"""
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlparse

from .salary_eligibility import normalize_salary_status
from .player_roles import UNAVAILABLE, PRACTICE

CONTRACT = 'factual_game_designation_v1'
FINAL_REPORT = 'official_final_team_report_v1'
NO_DESIGNATION = 'NO_GAME_DESIGNATION'
QUESTIONABLE = {'Q', 'QUESTIONABLE'}
ADVERSE = UNAVAILABLE | PRACTICE | {'CUT'}
DRESSING_REPORT = 'official_game_dressing_v1'


def clock(value):
    value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def status(value):
    value = normalize_salary_status(value)
    return {'Q':'QUESTIONABLE', 'O':'OUT', 'D':'DOUBTFUL', 'ACT':'ACTIVE',
        'AVAILABLE':'ACTIVE','HEALTHY':'ACTIVE','SUSP':'SUSPENDED','P':'PROBABLE'}.get(value, value)


def final_report_fact(fact):
    return (fact.get('report_contract') == FINAL_REPORT and fact.get('report_phase') == 'final'
            and fact.get('scope_verified') is True and fact.get('published_at')
            and fact.get('source_uri') and fact.get('source_ids'))


def explicit_game_dressing(fact, value):
    """Roster ACT is not an official game-active/inactive publication."""
    from .classic_official_context import CLUBS
    host=urlparse(str(fact.get('source_uri') or '')).hostname
    hosts={'nfl.com','www.nfl.com',*(domain+'.com' for domain in CLUBS.values()),
        *('www.'+domain+'.com' for domain in CLUBS.values())}
    return (fact.get('kind')=='game_status' and host in hosts and
        fact.get('report_contract')==DRESSING_REPORT and fact.get('scope_verified') is True
        and fact.get('season') is not None and fact.get('week') is not None and fact.get('kickoff_at') and
        ((fact.get('game_active') is True and value=='ACTIVE') or
         (fact.get('game_active') is False and value=='INACTIVE')))


def resolve_designation(facts, *, cutoff, player_id, team, position, max_age_hours=24,
                        season=None, week=None, kickoff_at=None):
    """Resolve scoped current game facts, preserving conflicts and all raw facts.

    Final report publication is the semantic event clock, while its current HTTP
    observation proves the report was actually verified. Neither replaces the
    other. Later adverse game evidence cannot silently disappear behind it.
    """
    cutoff = clock(cutoff); candidates=[]
    for original in facts:
        if (str(original.get('player_id')) != str(player_id)
                or original.get('team') != team or original.get('position') != position
                or original.get('kind') not in {'game_status', 'injury_status'}):
            continue
        try:
            observed=clock(original['observed_at']); received=clock(original['received_at'])
            if not original.get('source') or not original.get('source_ids') or observed>cutoff or received>cutoff or observed>received:
                continue
            if (cutoff-observed).total_seconds()>max_age_hours*3600:continue
            value=status(original.get('status'))
            final=bool(final_report_fact(original))
            if ((season is not None and original.get('season') is not None and original['season']!=season)
                    or (week is not None and original.get('week') is not None and original['week']!=week)
                    or (kickoff_at and original.get('kickoff_at') and clock(original['kickoff_at'])!=clock(kickoff_at))):continue
            if final and ((season is not None and original.get('season') is None)
                    or (week is not None and original.get('week') is None)):continue
            if original.get('game_active') is True and not explicit_game_dressing(original,value):continue
            if value==NO_DESIGNATION and not final:continue
            if value not in ADVERSE | {'QUESTIONABLE','DOUBTFUL','ACTIVE','PROBABLE',NO_DESIGNATION}:continue
            event=clock(original.get('modified_at') or original['published_at']) if final else observed
            if event>observed or (final and not event < clock(original['kickoff_at'])):continue
            candidates.append((original,value,event,final))
        except (KeyError,ValueError,TypeError):continue
    chosen=None; conflicts=[]
    if candidates:
        latest=max(candidates,key=lambda f:(f[2],str(f[0].get('source_ids'))))
        finals=[f for f in candidates if f[3]]
        chosen=max(finals,key=lambda f:(f[2],str(f[0].get('source_ids')))) if finals else latest
        dressing=[f for f in candidates if explicit_game_dressing(f[0],f[1]) and f[2]>=chosen[2]]
        if dressing:chosen=max(dressing,key=lambda f:(f[2],str(f[0].get('source_ids'))))
        # A later substantive observation contradicting the final report needs
        # review; finalness is not permission to ignore late Q/OUT/inactives.
        conflicting=[f for f in candidates if f[1]!=chosen[1] and f[2]>=chosen[2]]
        # Later explicit adverse designations supersede the old report. Q vs
        # cleared status remains a source conflict unless a new final report or
        # explicit game-active/inactive publication resolves it.
        adverse=[f for f in candidates if f[2]>chosen[2] and f[1] in ADVERSE]
        if adverse:
            chosen=max(adverse,key=lambda f:f[2]);conflicting=[f for f in candidates if f[2]>=chosen[2] and f[1]!=chosen[1]]
        conflicts=[deepcopy(f[0]) for f in conflicting]
    return dict(contract=CONTRACT,player_id=str(player_id),team=team,position=position,
        evaluated_at=cutoff.isoformat(),status='conflict' if conflicts else 'resolved' if chosen else 'unknown',
        effective_designation=None if conflicts or not chosen else chosen[1],
        chosen_fact=deepcopy(chosen[0]) if chosen else None,conflicts=conflicts,
        source_facts=deepcopy([f[0] for f in candidates]),
        superseded_facts=deepcopy([f[0] for f in candidates if chosen and f is not chosen and f[0] not in conflicts]))


def effective_designation(row):
    """Read a versioned canonical resolution; legacy records retain old policy."""
    evidence=row.get('evidence_json') or row.get('evidence') or {}
    resolved=row.get('designation_resolution') or (evidence.get('designation_resolution') if isinstance(evidence,dict) else None)
    if isinstance(resolved,dict) and resolved.get('contract')==CONTRACT:
        pid=str(row.get('player_id') or row.get('player_master_id') or '')
        if pid and pid!=str(resolved.get('player_id')):return 'UNKNOWN'
        team=row.get('player_team') or row.get('team')
        if team and team!=resolved.get('team'):return 'UNKNOWN'
        if row.get('position') and row['position']!=resolved.get('position'):return 'UNKNOWN'
        if resolved.get('status')=='conflict':return 'UNKNOWN'
        if resolved.get('status')=='resolved':return resolved.get('effective_designation') or 'UNKNOWN'
    # Backward-compatible union: absence/ACT never erases an archived Q flag.
    context=status(row.get('pregame_injury_status')) or status(row.get('injury_status'))
    values=[status(row.get('player_status')),context]
    if not any(values):
        values=[status(row.get(k)) for k in ('availability_status','official_availability_status')]
    for group in (ADVERSE,{'QUESTIONABLE'},{'DOUBTFUL'}):
        if set(values)&group:return next(v for v in values if v in group)
    return next((v for v in values if v),'UNKNOWN')
