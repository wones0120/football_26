"""Missingness and transformation ancestry for one frozen weekly feature stage."""
from collections import Counter
from copy import deepcopy
import math,re
from .weekly_effectiveness_catalog_features import DEFINITIONS, ALIASES, COUNTS, SOURCE_FIELDS, VERSION as INPUT_VERSION, _values
from .defense_context_evidence import _hash
from .evaluation_record import digest

VERSION='weekly_feature_stage_missingness_ancestry_v1'
FIELDS=tuple(sorted({v for d in DEFINITIONS.values() for v in d[:2]}))
METRICS=tuple(DEFINITIONS)
FIELD_SCHEMA=['normalization_state','normalized_value','alias_presence_states']
STATE_DEFINITIONS={
 'KNOWN':'Unique finite compatible source value; source numeric zero is preserved',
 'ABSENT':'All aliases absent from raw projection',
 'NULL_OR_EMPTY':'Aliases present but all null/empty',
 'INVALID':'Invalid source numeric/count value; no replacement',
 'CONFLICT':'Conflicting valid alias values; no arbitrary selection',
 'SUBSET_VIOLATION':'Source numerator exceeds compatible exposure; normalized unknown',
}
METRIC_BRANCHES={'DEFINED':'Raw-derived compatible numerator / positive denominator',
 'ZERO_DENOM':'Known zero denominator; undefined, no replacement',
 'UNKNOWN_N':'Unknown numerator, known nonzero denominator',
 'UNKNOWN_D':'Known numerator, unknown denominator',
 'UNKNOWN_BOTH':'Both required inputs unknown',
 'ROLE_INAPPLICABLE':'Producer has no source-proven QB metric for this row',
 'QUARANTINED_NATIVE':'No feature actor attached; original malformed native source row retained'}


def _numeric(v, count):
    if v in (None,'') or isinstance(v,bool):return None
    try:n=float(v)
    except (ValueError,TypeError):return None
    return n if math.isfinite(n) and (not count or (n>=0 and n==int(n))) else None


def _field(raw, field, value, quality):
    present=[];known=[];invalid=False
    for alias in ALIASES.get(field,(field,)):
        if alias not in raw:present.append('ABSENT');continue
        v=raw[alias]
        if v is None:present.append('NULL');continue
        if v=='':present.append('EMPTY');continue
        n=_numeric(v,field in COUNTS)
        if n is None:present.append('INVALID');invalid=True
        else:present.append('ZERO' if n==0 else 'VALUE');known.append(n)
    if quality.get(field,{}).get('reason')=='source_count_exceeds_compatible_exposure':state='SUBSET_VIOLATION'
    elif invalid:state='INVALID'
    elif len(set(known))>1:state='CONFLICT'
    elif known:state='KNOWN'
    elif all(p=='ABSENT' for p in present):state='ABSENT'
    else:state='NULL_OR_EMPTY'
    expected=known[0] if state=='KNOWN' else None
    if value!=expected:raise ValueError('Normalization is not source-preserving or declared unknown')
    return [state,value,present]


def build_weekly_feature_ancestry(source,weekly):
    if weekly.get('version')!=INPUT_VERSION or weekly.get('pregame_serving_eligible') is not False:
        raise ValueError('Bound nonserving weekly producer required')
    accepted={r['source_ref']['source_id']:r for r in weekly['rows']}
    quarantine={r['source_id']:r for r in weekly['identity_review_requests'] if 'source_id' in r and 'source_row_sha256' in r}
    expected_quarantine=Counter((r['native_player_id'],r['source_row_sha256']) for r in weekly['quarantined_source_rows'])
    if Counter((r['native_player_id'],r['source_row_sha256']) for r in quarantine.values())!=expected_quarantine:
        raise ValueError('Semantic quarantine and original raw identity incidents differ')
    if len(accepted)!=len(weekly['rows']) or len(quarantine)!=len(weekly['quarantined_source_rows']) or set(accepted)&set(quarantine):
        raise ValueError('Unique disjoint accepted/quarantined source lineage required')
    rows=[];seen=set();field_counts={f:Counter() for f in FIELDS};metric_counts={m:Counter() for m in METRICS}
    for r in source['rows']:
        sid=r['source_id'];raw={k:deepcopy(v) for k,v in r['raw_row_json'].items() if k in SOURCE_FIELDS}
        if sid in seen:raise ValueError('Duplicate raw source lineage')
        seen.add(sid);old=accepted.get(sid);bad=quarantine.get(sid)
        native=r.get('source_player_id');malformed=not isinstance(native,str) or re.fullmatch(r'00-\d{7}',native) is None
        if malformed != (bad is not None) or (old is None)==(bad is None):raise ValueError('Native quarantine transformation differs')
        sha=_hash(raw)
        if old is not None:
            if old['source_ref']['projected_source_row_sha256']!=sha or (old['source_player_id'],old['season'],old['week'])!=(native,r['season'],r['week']):
                raise ValueError('Raw source/feature row binding differs')
        elif bad['source_row_sha256']!=sha:raise ValueError('Quarantine raw source checksum differs')
        values,quality=_values(raw);fields=[]
        for field in FIELDS:
            d=_field(raw,field,values[field],quality);fields.append(d);field_counts[field][d[0]]+=1
        branches=[]
        role=r.get('position')=='QB' and (raw.get('position') if raw.get('position') is not None else raw.get('pos')) in (None,'QB')
        for mid in METRICS:
            num,den,unit,scope=DEFINITIONS[mid];n,d=values[num],values[den]
            if malformed:branch='QUARANTINED_NATIVE'
            elif scope=='QB' and not role:
                branch='ROLE_INAPPLICABLE'
                if mid in old['metrics']:raise ValueError('Unexpected inapplicable metric')
            else:
                if d==0:branch='ZERO_DENOM'
                elif n is None and d is None:branch='UNKNOWN_BOTH'
                elif n is None:branch='UNKNOWN_N'
                elif d is None:branch='UNKNOWN_D'
                else:branch='DEFINED'
                expected=n/d if n is not None and d is not None and d>0 else None
                m=old['metrics'].get(mid)
                if m is None or (m['numerator'],m['denominator'],m['value'])!=(n,d,expected):
                    raise ValueError('Feature transformation differs; no undeclared imputation allowed')
            branches.append(branch);metric_counts[mid][branch]+=1
        rows.append(dict(source_id=sid,source_player_id=native,player_master_id=old['player_master_id'] if old else None,
            season=r['season'],week=r['week'],team=old['team'] if old else r.get('team'),quarantined=malformed,
            fields=fields,metric_branches=branches))
    if seen!=set(accepted)|set(quarantine):raise ValueError('Raw source universe differs from feature plus quarantine')
    rows.sort(key=lambda r:str(r['source_id']))
    basis=dict(version=VERSION,candidate_id='X08-M08',before_period=weekly['before_period'],field_order=FIELDS,
        metric_order=METRICS,field_schema=FIELD_SCHEMA,field_state_definitions=STATE_DEFINITIONS,metric_branch_definitions=METRIC_BRANCHES,
        source_field_aliases={f:ALIASES.get(f,(f,)) for f in FIELDS},rows=rows,
        field_state_counts={f:dict(v) for f,v in field_counts.items()},metric_branch_counts={m:dict(v) for m,v in metric_counts.items()},
        imputation_ancestry=dict(bound_feature_stage='No imputation: unique validated source value or unknown; ratios only on compatible positive denominator',
            upstream_provider_preprocessing='UNKNOWN_NOT_ASSESSED',model_preprocessing='NOT_ASSESSED_MODELS_PAUSED',
            known_zero_basis='Actual compatible numeric source zero; not missing or absent-player fill',
            quarantine='Raw source rows retained; no actor value manufactured'))
    return basis|dict(semantic_sha256=digest(basis),provenance=deepcopy(weekly['provenance']),
        identity_review_requests=deepcopy(weekly['identity_review_requests']),pregame_serving_eligible=False,
        evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,models_or_optimizer_consumed=False)


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_diagnostic':
        raise ValueError('Feature-stage ancestry cannot serve forecasts/models/optimizer')
    return value
