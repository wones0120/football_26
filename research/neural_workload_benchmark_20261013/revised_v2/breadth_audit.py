"""Source-inspection audit of production model/context versus research adapters."""
import ast, gzip, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
paths=[ROOT/'backend/app/product_services/canonical_projection_inputs.py',ROOT/'backend/app/product_services/predictions.py',ROOT/'Database/features.py']
module=ast.parse(paths[0].read_text());env={}
for node in module.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in {'BASE_FEATURE_COLUMNS','POSITION_FEATURE_COLUMNS','MARKET_FEATURE_COLUMNS','OPPORTUNITY_FEATURE_COLUMNS','FEATURE_COLUMNS'}:
                expr=ast.Expression(node.value)
                env[target.id]=eval(compile(expr,'feature_list','eval'),{'__builtins__':{}},env)
manifest=json.loads((HERE/'input_manifest.json').read_text())
with gzip.open(ROOT/'artifacts/classic_opportunity_repair/weekly_stats.json.gz','rt') as source:
    raw=json.load(source)
eligible=[r['raw_row_json'] for r in raw if r['season'] in (2023,2024,2025) and r['position'] in {'QB','RB','WR','TE'} and r['raw_row_json'].get('season_type')=='REG']
unused=['passing_epa','passing_cpoe','passing_air_yards','receiving_epa','rushing_epa',
        'receiving_yards_after_catch','rushing_first_downs','receiving_first_downs',
        'passing_first_downs','air_yards_share','wopr','rushing_fumbles_lost','receiving_fumbles_lost']
result={'production_source_audit_only':True,'live_feature_coverage_checked':False,
    'production_fitted_feature_contract':env['FEATURE_COLUMNS'],
    'production_model':'GradientBoostingRegressor(random_state=42), not this benchmark HistGradientBoosting',
    'production_context_not_direct_fitted_inputs':env['OPPORTUNITY_FEATURE_COLUMNS'],
    'production_context_behavior':'Opportunity columns derive offensive-role inputs and feed point adjustment; explicit pregame availability/start/workload context, current markets and position calibration also affect final projections.',
    'production_legacy_feature_builder_hooks':'Database/features.py exposes routes, red-zone, situational pass rate/PROE, pace and historical production hooks; hook presence does not establish populated data or inclusion in current canonical fitted feature list.',
    'families':[
        {'family':'Lagged fantasy production / position','production':'Fitted: roll3/8 mean, std, opponent and positional defense history, position','research':'Both baseline/enriched: prior3/last PPR and position; enriched opponent position PPR','coverage':'Measured stat history; revised data'},
        {'family':'Targets/carries/team shares','production':'Context, offensive role and opportunity postprocessing; six opportunity columns not directly in FEATURE_COLUMNS','research':'Both paired feature matrices: prior workload/share/team volumes/trend','coverage':'Observed prior rows only; partial skill totals'},
        {'family':'Receiving/rushing/passing production and efficiency','production':'Some legacy feature hooks; not directly in current fitted canonical FEATURE_COLUMNS','research':'Enriched: ten lagged stats plus four ratio features','coverage':'Measured 2023–25 weekly source fields; undefined ratio remains missing'},
        {'family':'Opponent / team situational context','production':'Positional allowed roll3/8/p90 and missing-share fitted features','research':'Enriched: lagged opponent positional targets/carries/PPR and team attempts/pass-fraction proxy','coverage':'Reconstructed matchup linkage; previous completed weeks only. Pass fraction is not situation-adjusted play-by-play'},
        {'family':'Salary / market / home context','production':'Fitted salary/home/total/spreads/implied totals; latest market changes also postprocessed','research':'Excluded from this historical packet','coverage':'No 2023–25 salary or contemporary markets/home fixture was captured for the common comparison'},
        {'family':'Snap participation / routes / depth / injuries','production':'Snap share and role importance/completeness fitted; explicit availability/depth/workload inputs contextual','research':'Excluded, no guesses','coverage':'No usable 2023–25 snaps, routes or timestamped pregame roster/news in this captured source'},
        {'family':'Red zone / goal line / game-state pace / PROE','production':'Legacy/explicit context hooks exist, not all in fitted matrix','research':'Excluded, no inferred routes or situational counts','coverage':'Unsupported by selected weekly snapshot'},
    ],
    'feature_coverage':manifest['coverage'],
    'available_historical_raw_fields_not_selected':{key:sum(r.get(key) is not None for r in eligible)/len(eligible) for key in unused},
    'why_not_all_numeric_fields':'Avoid redundant/noisy predictors and enlarge only the predefined football feature set; EPA/CPOE and further efficiency/context variants remain candidates for another frozen experiment, not post-test tuning.',
    'answer_to_full_breadth':'No. Both models now share baseline and enriched supported historical inputs, but neither research model has all production/source families. Production also does not fit every collected field; distinguish training inputs from context and unavailable hooks.',
    'next_data_work':'Read-only historical participation/snaps and schedules/rosters, then versioned historical markets and injury/depth evidence; audit time/missingness before adding common features. No provider installation or live ingestion was started.',
    'sources_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(HERE/'data_breadth_audit.json').write_text(json.dumps(result,indent=2)+'\n')
