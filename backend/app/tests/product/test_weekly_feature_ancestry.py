from copy import deepcopy
import pytest
from backend.app.product_services.weekly_feature_ancestry import build_weekly_feature_ancestry,FIELDS,METRICS
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row,build


def run(records=None):
    records=records or [row()];return build_weekly_feature_ancestry(dict(rows=records),build(records))


def cell(x,field):return x['rows'][0]['fields'][FIELDS.index(field)]


def test_actual_source_zero_and_ratio_ancestry_not_imputation():
    r=row();r['raw_row_json'].update(passing_yards=0,targets=0,receptions=0)
    x=run([r]);assert cell(x,'passing_yards')[:2]==['KNOWN',0]
    assert x['rows'][0]['metric_branches'][METRICS.index('G09-M01')]=='ZERO_DENOM'
    assert x['imputation_ancestry']['upstream_provider_preprocessing']=='UNKNOWN_NOT_ASSESSED'


@pytest.mark.parametrize('value,state',[(None,'NULL_OR_EMPTY'),('','NULL_OR_EMPTY'),('bad','INVALID'),(-1,'INVALID'),(True,'INVALID')])
def test_missing_invalid_counts_are_unknown_never_zero(value,state):
    r=row();r['raw_row_json']['attempts']=value;x=run([r]);assert cell(x,'attempts')[0]==state and cell(x,'attempts')[1] is None


def test_alias_conflict_and_exposure_subset_violation_distinct():
    r=row();r['raw_row_json'].update(passing_attempts=21);assert cell(run([r]),'attempts')[0]=='CONFLICT'
    r=row();r['raw_row_json']['completions']=21;assert cell(run([r]),'completions')[0]=='SUBSET_VIOLATION'


def test_absent_field_not_present_null():
    r=row();del r['raw_row_json']['targets'];assert cell(run([r]),'targets')[0]=='ABSENT'
    r=row();r['raw_row_json']['targets']=None;assert cell(run([r]),'targets')[0]=='NULL_OR_EMPTY'


def test_quarantine_retains_source_field_diagnostics_and_no_actor():
    r=row(source_player_id='not-native');x=run([r]);assert x['rows'][0]['quarantined']
    assert set(x['rows'][0]['metric_branches'])=={'QUARANTINED_NATIVE'} and cell(x,'attempts')[1]==20


def test_nonQB_role_has_no_fake_passing_metrics():
    r=row(position='WR');r['raw_row_json']['position']='WR';x=run([r])
    assert x['rows'][0]['metric_branches'][METRICS.index('G04-M01')]=='ROLE_INAPPLICABLE'


@pytest.mark.parametrize('change',['value','raw','missing','duplicate'])
def test_transform_and_lineage_guard(change):
    r=row();w=build([r]);source=dict(rows=[r])
    if change=='value':w['rows'][0]['metrics']['G04-M01']['value']=.7
    if change=='raw':r['raw_row_json']['attempts']=21
    if change=='missing':source['rows']=[]
    if change=='duplicate':source['rows'].append(deepcopy(r))
    with pytest.raises(ValueError):build_weekly_feature_ancestry(source,w)


def test_signed_source_yards_and_no_source_row_loss():
    r=row();r['raw_row_json']['passing_yards']=-7;x=run([r]);assert cell(x,'passing_yards')[:2]==['KNOWN',-7]
    assert len(x['rows'])==1 and all(sum(v.values())==1 for v in x['field_state_counts'].values())


def test_model_serving_forbidden_and_independent_stage_scope():
    from backend.app.product_services.weekly_feature_ancestry import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_diagnostic') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='forecast')
    assert x['imputation_ancestry']['model_preprocessing']=='NOT_ASSESSED_MODELS_PAUSED'
