"""Literal inactive history and observed first-return/source-role states."""
from copy import deepcopy
from datetime import datetime,UTC
from .factual_designation import clock
from .official_absence_source import VERSION as ABSENCE_VERSION
from .absence_return_opportunity import VERSION as RETURN_VERSION
from .weekly_effectiveness_catalog_features import VERSION as WEEKLY_VERSION
from .evaluation_record import digest

VERSION='source_scoped_availability_history_catalog_v1'


def build_availability_history(absences,returns,weekly,*,cutoff):
    decision=clock(cutoff)
    if (decision is None or decision>datetime.now(UTC) or absences.get('version')!=ABSENCE_VERSION
            or returns.get('version')!=RETURN_VERSION or weekly.get('version')!=WEEKLY_VERSION
            or any(x.get('pregame_serving_eligible') is not False for x in (absences,returns,weekly))):
        raise ValueError('Reviewed nonserving source trio and actual cutoff required')
    for src,f in ((absences,'actual_publication_at'),(returns,'actual_publication_at'),(weekly,'actual_derived_at')):
        t=clock(src.get('provenance',{}).get(f))
        if t is None or t>decision:raise ValueError('Source not available by actual cutoff')
    if (returns['provenance']['absence_source_provenance']!=absences['provenance']
            or returns['provenance']['weekly_source_provenance']!=weekly['provenance']):
        raise ValueError('Return and availability evidence source pairing differs')
    from datetime import date
    try:source_date=date.fromisoformat(absences['game_date']).isoformat()
    except (KeyError,TypeError,ValueError):raise ValueError('Bound source game date required')
    history=[];excluded=[];by_key={}
    for a in absences['rows']:
        if not a['ordinary_absence_anchor']:
            if a['source_status'] not in {'DID_NOT_PLAY','EMERGENCY_THIRD_QB_EXCEPTION'}:raise ValueError('Unknown official source status domain')
            excluded.append(deepcopy(a));continue
        if a['source_status']!='NOT_ACTIVE':raise ValueError('Ordinary history requires literal official Not Active')
        if a['source_row_key'] in by_key:raise ValueError('Duplicate official source fact')
        by_key[a['source_row_key']]=a
        history.append(dict(candidate_id='G17-M03',source_game_date=source_date,source_fact=deepcopy(a),ordinary_inactive_events_observed=1,
            history_coverage='This exact sourced player-game only; no assertion for unsourced games',
            current_active_status=None,complete_inactive_history=None))
    states=[]
    for r in returns['rows']:
        a=by_key.get(r['absence_source_row_key'])
        if a is None or any(r[k]!=a[k] for k in ('season','team','player_master_id','source_position')) or r['source_native_gsis_id']!=a['source_native_gsis_id'] or r['absence_native_game_id']!=a['native_game_id']:
            raise ValueError('Native/canonical return anchor binding differs')
        first=r['metrics']['X03-M01']['first_verified_active']
        positive=[s for s in r['scheduled_postabsence_slots'] if s['state']=='observed_positive_offensive_opportunity']
        latest=deepcopy(positive[-1]) if positive else None
        prior_slot=r['preabsence_scheduled_slots'][-1] if r['preabsence_scheduled_slots'] else None
        prior=[]
        if prior_slot:
            prior=[x for x in weekly['rows'] if (x['season'],x['week'],x['team'],x['source_player_id'],x['player_master_id'])==
                (r['season'],prior_slot['week'],r['team'],r['source_native_gsis_id'],r['player_master_id'])]
        if len(prior)>1:raise ValueError('Unique immediate preabsence weekly source role required')
        prior_role=prior[0]['source_position'] if prior else None
        role_path=[prior_role]+[s['source_position'] for s in positive]
        continuous=(all(x==a['source_position'] for x in role_path) if first is not None and all(x not in (None,'') for x in role_path) else None)
        states.append(dict(candidate_id='G17-M04',season=r['season'],team=r['team'],source_native_gsis_id=r['source_native_gsis_id'],
            player_master_id=r['player_master_id'],absence_source_row_key=r['absence_source_row_key'],absence_native_game_id=r['absence_native_game_id'],
            return_transition_state='proven_first_offensive_participation_after_verified_absence' if first is not None else 'unknown_first_return_chronology',
            first_return_proven=True if first is not None else None,first_verified_return=deepcopy(first),
            latest_proven_participating_game=latest,immediate_preabsence_source_role=prior_role,anchor_literal_role=a['source_position'],
            observed_source_role_continuity=continuous,observed_role_evidence_path=role_path,
            measured_scheduled_slots=deepcopy(r['scheduled_postabsence_slots']),current_means='Measured historical source prefix, not a confirmed upcoming role',
            health_recovery=None,full_workload_recovery=None))
    basis=dict(version=VERSION,candidate_ids=['G17-M03','G17-M04'],inactive_history_rows=history,return_status_rows=states,
        excluded_source_domains=excluded,observed_prefix_before_period=returns['before_period'])
    return dict(**basis,semantic_sha256=digest(basis),pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',
        missing_history_semantics='Unknown coverage, never active or zero inactive history',model_or_optimizer_consumed=False,
        provenance=dict(absence_provenance=deepcopy(absences['provenance']),return_provenance=deepcopy(returns['provenance']),weekly_provenance=deepcopy(weekly['provenance'])))


def load_reviewed_return_input(ref,*,cutoff):
    from pathlib import Path
    import hashlib,json
    from . import absence_return_opportunity
    p=Path(ref['path']).resolve();decision=clock(cutoff)
    if p.parent!=Path('artifacts/absence_return_opportunity').resolve() or p.name!=ref['sha256']+'.json' or not 0<ref['bytes']<=1024*1024:
        raise ValueError('Managed bounded return artifact required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Return input bytes differ')
    result=json.loads(raw)
    if result.get('version')!=RETURN_VERSION or result.get('pregame_serving_eligible') is not False:raise ValueError('Reviewed return input required')
    if result['provenance']['producer_code_sha256']!=hashlib.sha256(Path(absence_return_opportunity.__file__).read_bytes()).hexdigest():raise ValueError('Return producer differs')
    t=clock(result['provenance'].get('actual_publication_at'))
    if decision is None or t is None or t>decision:raise ValueError('Return source unavailable at cutoff')
    if result['semantic_sha256']!=digest({k:result[k] for k in ('version','before_period','definitions','rows')}):raise ValueError('Return semantic checksum differs')
    return result
