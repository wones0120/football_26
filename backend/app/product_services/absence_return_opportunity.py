"""Observed active-game return counts after literal official Not Active evidence."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,UTC
from uuid import UUID
import math
from .official_absence_source import VERSION as ABSENCE_VERSION
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .schedule_context_features import VERSION as SCHEDULE_VERSION
from .factual_designation import clock
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='observed_official_absence_return_opportunity_v1'
CHANNELS={'pass_attempts':'G04-M01','rush_attempts':'G07-M01','targets':'G09-M01'}
DEFINITIONS=dict(baseline='Exactly two immediately preceding scheduled same-team/season games; counts pooled then divided by two',
 participation='Strictly positive official pass/rush/target opportunity establishes observed offensive participation; all-zero/missing weekly rows remain unknown',
 ordinals='First, second, third proven ACTIVE games after an ordinary Not Active anchor; any earlier unknown scheduled participation blocks later ordinal certification',
 response='Official count in certified active game minus fixed preabsence two-game mean, separate pass/rush/target units',
 role='Anchor literal offensive role and each measured weekly source role retained; pass channel requires source-proven QB',
 no_causal_claim='No health, injury cause, recovery probability, future role or guaranteed workload interpretation')


def _counts(row):
    if row is None:return {c:None for c in CHANNELS}
    counts={}
    for channel,mid in CHANNELS.items():
        value=row['metrics'].get(mid,{}).get('denominator')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0 or value!=int(value)):
            raise ValueError('Finite nonnegative integer official opportunity required')
        if channel=='pass_attempts' and not row.get('QB_scope_source_proven'):value=None
        counts[channel]=value
    return counts


def build_absence_return_opportunity(absences,weekly,schedule,*,before_period,cutoff):
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture cutoff required')
    if type(before_period) is not int or not 1<=before_period%100<=18:raise ValueError('Declared REG period required')
    if (absences.get('version')!=ABSENCE_VERSION or weekly.get('version')!=WEEKLY_VERSION
            or schedule.get('version')!=SCHEDULE_VERSION or weekly.get('before_period')<before_period
            or any(x.get('pregame_serving_eligible') is not False for x in (absences,weekly,schedule))):
        raise ValueError('Reviewed nonserving absence/weekly/schedule inputs required')
    for source,field in ((absences,'actual_publication_at'),(weekly,'actual_derived_at')):
        t=clock(source.get('provenance',{}).get(field))
        if t is None or t>decision:raise ValueError('Source publication unavailable at cutoff')
    games=defaultdict(list);binding={}
    for g in schedule['game_rows']:
        if g['game_type']!='REG' or g['season']*100+g['week']>=before_period:continue
        home,away=canonical_team(g['home_team']),canonical_team(g['away_team'])
        if home==away:raise ValueError('Distinct native game teams required')
        for team in (home,away):
            key=(g['season'],g['week'],team)
            if key in binding:raise ValueError('Unique native team/week schedule required')
            binding[key]=g['game_id'];games[(g['season'],team)].append(g)
    for gs in games.values():gs.sort(key=lambda g:g['week'])
    native=defaultdict(list)
    for r in weekly['rows']:
        if r['season']*100+r['week']>=before_period:continue
        if r['season_type']!='REG':raise ValueError('REG weekly source required')
        native[(r['season'],r['source_player_id'])].append(r)
    anchors=[];seen=set()
    for a in absences['rows']:
        if not a['ordinary_absence_anchor'] or a['source_position'] not in {'QB','RB','FB','WR','TE'}:continue
        if a['source_status']!='NOT_ACTIVE':raise ValueError('Only ordinary source Not Active can anchor return')
        season,week,team=a['season'],a['week'],canonical_team(a['team'])
        if binding.get((season,week,team))!=a['native_game_id']:raise ValueError('Absence native game differs from schedule')
        key=(season,week,team,a['source_native_gsis_id'],a['source_row_key'])
        if key in seen:raise ValueError('Duplicate source absence anchor')
        seen.add(key);anchors.append(a)
    rows=[]
    for a in anchors:
        season,team,pid,nid=a['season'],canonical_team(a['team']),a['player_master_id'],a['source_native_gsis_id']
        if pid is not None and str(UUID(str(pid)))!=pid:raise ValueError('Canonical UUID spelling required')
        by_week={}
        for r in native.get((season,nid),[]) if nid is not None else []:
            rt=canonical_team(r['team']) if r['team'] else None
            if rt!=team:continue
            if r['week'] in by_week:raise ValueError('Duplicate native weekly actor/team/game')
            gid=binding.get((season,r['week'],team))
            if gid is None or r['native_game_id'] not in (None,'',gid):raise ValueError('Weekly native game differs from schedule')
            if pid is not None and r['player_master_id']!=pid:raise ValueError('Frozen canonical attachment differs')
            by_week[r['week']]=r
        gs=games[(season,team)];idx=next(i for i,g in enumerate(gs) if g['game_id']==a['native_game_id'])
        prior=gs[max(0,idx-2):idx];baseline_slots=[]
        for g in prior:
            r=by_week.get(g['week']);baseline_slots.append(dict(week=g['week'],native_game_id=g['game_id'],counts=_counts(r),weekly_row_present=r is not None))
        baseline={}
        for c in CHANNELS:
            known=[x['counts'][c] for x in baseline_slots if x['counts'][c] is not None]
            baseline[c]=dict(required_scheduled_games=2,observed_scheduled_slots=len(prior),known_count_slots=len(known),
                pooled_count=sum(known) if len(prior)==2 and len(known)==2 and pid is not None else None,
                mean_count=sum(known)/2 if len(prior)==2 and len(known)==2 and pid is not None else None,
                known_sample_counts=known)
        anchor_count=_counts(by_week.get(a['week']))
        if any(v is not None and v>0 for v in anchor_count.values()):raise ValueError('Positive offensive opportunity contradicts official ordinary absence')
        slots=[];verified={};active_lower=0;unknown_before=False
        for offset,g in enumerate(gs[idx+1:],1):
            prior_unknown=unknown_before
            r=by_week.get(g['week']);counts=_counts(r)
            positive=any(v is not None and v>0 for v in counts.values()) and pid is not None
            explicit_absence=pid is not None and nid is not None and any(f['ordinary_absence_anchor'] and f['source_status']=='NOT_ACTIVE'
                and (f['season'],f['week'],canonical_team(f['team']),f['source_native_gsis_id'],f['player_master_id'])==(season,g['week'],team,nid,pid)
                for f in absences['rows'])
            if positive and explicit_absence:raise ValueError('Positive offensive opportunity contradicts later official absence')
            state='observed_positive_offensive_opportunity' if positive else 'ordinary_not_active' if explicit_absence else 'unknown_participation'
            ordinal=None
            if positive:
                active_lower+=1
                if not unknown_before:ordinal=active_lower
            elif not explicit_absence:unknown_before=True
            differences={c:counts[c]-baseline[c]['mean_count'] if ordinal in {1,2,3} and counts[c] is not None and baseline[c]['mean_count'] is not None else None for c in CHANNELS}
            slot=dict(week=g['week'],native_game_id=g['game_id'],scheduled_game_offset=offset,state=state,
                proven_active_appearance_lower_bound=active_lower,certified_active_ordinal=ordinal,earlier_unknown_participation=prior_unknown,
                counts=counts,source_position=r['source_position'] if r else None,weekly_row_present=r is not None,baseline_difference=differences)
            slots.append(slot)
            if ordinal in {1,2,3}:verified[ordinal]=deepcopy(slot)
        rows.append(dict(season=season,team=team,source_native_gsis_id=nid,player_master_id=pid,source_position=a['source_position'],
            absence_native_game_id=a['native_game_id'],absence_week=a['week'],absence_source_row_key=a['source_row_key'],
            preabsence_scheduled_slots=baseline_slots,baseline=baseline,scheduled_postabsence_slots=slots,
            metrics={'X03-M01':dict(first_verified_active=verified.get(1)),
                     'X03-M02':dict(second_verified_active=verified.get(2),third_verified_active=verified.get(3))}))
    basis=dict(version=VERSION,before_period=before_period,definitions=DEFINITIONS,rows=rows)
    return dict(**basis,semantic_sha256=digest(basis),pregame_serving_eligible=False,
        evidence_use='postlock_descriptive_not_pregame_or_serving',model_or_optimizer_consumed=False,
        provenance=dict(absence_source_provenance=deepcopy(absences['provenance']),weekly_source_provenance=deepcopy(weekly['provenance']),schedule_source_provenance=deepcopy(schedule['provenance'])))


def load_reviewed_absence_input(ref,*,cutoff):
    """Authenticate the already reviewed immutable adapter output, never ingest."""
    from pathlib import Path
    import hashlib,json
    decision=clock(cutoff);p=Path(ref['path']).resolve()
    if (p.parent!=Path('artifacts/official_absence_source').resolve() or p.name!=ref['sha256']+'.json'
            or not 0<ref['bytes']<=1024*1024):raise ValueError('Managed bounded absence artifact required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Absence artifact bytes differ')
    result=json.loads(raw)
    from . import official_absence_source
    producer=hashlib.sha256(Path(official_absence_source.__file__).read_bytes()).hexdigest()
    if (result.get('version')!=ABSENCE_VERSION or result.get('pregame_serving_eligible') is not False
            or result['provenance'].get('producer_code_sha256')!=producer):raise ValueError('Reviewed absence producer binding differs')
    for field in ('actual_read_at','identity_derivation_cutoff','actual_derived_at','actual_publication_at'):
        t=clock(result['provenance'].get(field))
        if decision is None or t is None or t>decision:raise ValueError('Absence source clock missing or future')
    times=[clock(result['provenance'][f]) for f in ('actual_read_at','identity_derivation_cutoff','actual_derived_at','actual_publication_at')]
    if times!=sorted(times):raise ValueError('Absence source chronology differs')
    return result
