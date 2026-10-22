"""Source-classified prior coverage tendency, separate from full eligible exposure."""
from copy import deepcopy
from .scheduled_pressure_model_inputs import build_contexts,TEAM_COLUMNS as PRESSURE_TEAM_COLUMNS,PLAYER_COLUMNS as PRESSURE_PLAYER_COLUMNS,TEAM_VERSION as PRESSURE_TEAM_VERSION,PLAYER_VERSION as PRESSURE_PLAYER_VERSION
from .market_snapshots import canonical_team
from .evaluation_record import digest
VERSION='scheduled_coverage_model_inputs_v1'
TEAM_VERSION='team_opportunity_matrix_pressure_coverage3_v1'
PLAYER_VERSION='player_opportunity_matrix_pressure_coverage3_v1'
FIELDS=('man_rate','zone_rate','classified_dropbacks','mixed_dropbacks','other_dropbacks','unclassified_dropbacks','known_eligible_dropbacks','unknown_eligible_dropbacks','unknown_classified_membership','known_games','unknown_games')
COVERAGE_COLUMNS=tuple('opponent_coverage3_'+k for k in FIELDS)
TEAM_COLUMNS=(*PRESSURE_TEAM_COLUMNS,*COVERAGE_COLUMNS)
PLAYER_COLUMNS=(*PRESSURE_PLAYER_COLUMNS,*(f'team_{k}'for k in COVERAGE_COLUMNS))
COUNTS=('classified_dropbacks','man_dropbacks','zone_dropbacks','mixed_dropbacks','other_dropbacks','unclassified_dropbacks','known_eligible_dropbacks','unknown_eligible_dropbacks','unknown_classified_membership')


def build_coverage_contexts(sources,schedule):
    # Reuse the reviewed native calendar/prior-date/no-skip validation only.
    calendar=build_contexts(dict(version='pfr_pressure_catalog_v1',pregame_serving_eligible=False,game_rows=[]),schedule)
    index={}
    for source in sources:
        if source.get('version')!='participation_defense_catalog_v1'or source.get('pregame_serving_eligible')is not False:raise ValueError('Exact reviewed native coverage source required')
        season=source['season']
        for r in source['team_game_rows']:
            key=(r['game_id'],canonical_team(r['team']))
            if key in index or int(r['game_id'][:4])!=season:raise ValueError('Duplicate or conflicting source season')
            if any(type(r[k])is not int or r[k]<0 for k in COUNTS):raise ValueError('Exact nonnegative native category counters required')
            if sum(r[k]for k in('man_dropbacks','zone_dropbacks','mixed_dropbacks','other_dropbacks'))!=r['classified_dropbacks']or r['classified_dropbacks']+r['unclassified_dropbacks']!=r['known_eligible_dropbacks']:raise ValueError('Coverage partition differs')
            for mid,category in(('G14-M04','man_dropbacks'),('G14-M05','zone_dropbacks')):
                expected=r[category]/r['classified_dropbacks']if r['classified_dropbacks']and not r['unknown_classified_membership']else None
                if r['metrics'][mid]['value']!=expected:raise ValueError('Approved classified metric differs')
            index[key]=r
    valid={(r['game_id'],r['team'])for r in calendar['rows']}
    if not set(index)<=valid:raise ValueError('Coverage native game/team absent schedule')
    rows=[]
    for target in calendar['rows']:
        prior=target['axes']['opponent_generated'];ids=prior['contributing_game_ids'];opponent=target['opponent']
        observed=[index.get((gid,opponent))for gid in ids];known=[r for r in observed if r is not None and r['unknown_classified_membership']==0]
        complete=len(ids)==3 and len(known)==3
        # Classified exposure includes mixed/other, not just MAN+ZONE. Unknown
        # possible classified members mask all exact counts and rates.
        totals={k:sum(r[k]for r in known)if complete else None for k in COUNTS}
        den=totals['classified_dropbacks'];features=dict(man_rate=totals['man_dropbacks']/den if complete and den else None,zone_rate=totals['zone_dropbacks']/den if complete and den else None,**{k:totals[k]for k in FIELDS if k in totals},known_games=len(known),unknown_games=3-len(known))
        rows.append(dict(game_id=target['game_id'],team=target['team'],opponent=opponent,period=target['period'],features={'opponent_coverage3_'+k:features[k]for k in FIELDS},window=dict(contributing_game_ids=ids,contributing_periods=prior['contributing_periods'],complete_classified=complete,category_totals=totals,known_games=len(known),unknown_games=3-len(known),observed_sample_totals={k:sum(r[k]for r in observed if r is not None)for k in COUNTS},full_eligible_fraction_proven=complete and totals['unknown_eligible_dropbacks']==0 and totals['unclassified_dropbacks']==0 and totals['unknown_classified_membership']==0)))
    return dict(version=VERSION,rows=rows,definition='Direct source MAN/ZONE counts divided by all classified eligible nonspike DBs (including mixed/other), exactly3 immediate prior scheduled opponent-defense games',full_eligible_fraction_inputs=False,original_pregame_backtest_eligible=False)


def append_coverage_context(matrix,contexts,*,grain,parent_refs):
    expected=list(PRESSURE_TEAM_COLUMNS if grain=='team'else PRESSURE_PLAYER_COLUMNS)
    if grain not in{'team','player'}or matrix.get('version')!=(PRESSURE_TEAM_VERSION if grain=='team'else PRESSURE_PLAYER_VERSION)or matrix['feature_columns']!=expected or contexts.get('version')!=VERSION:raise ValueError('Reviewed pressure input/context/grain contract required')
    if digest({k:v for k,v in matrix.items()if k not in{'matrix_sha256','provenance'}})!=matrix['matrix_sha256']:raise ValueError('Pressure matrix semantic differs')
    lookup={(r['game_id'],r['team']):r for r in contexts['rows']}
    if len(lookup)!=len(contexts['rows']):raise ValueError('Duplicate coverage target')
    out=deepcopy(matrix);out['version']=TEAM_VERSION if grain=='team'else PLAYER_VERSION;out['feature_columns']=list(TEAM_COLUMNS if grain=='team'else PLAYER_COLUMNS)
    for row in out['rows']:
        context=lookup.get((row['game_id'],canonical_team(row['team'])))
        if context is None or context['period']!=row['period']:raise ValueError('Coverage target native binding differs')
        periods=context['window']['contributing_periods']
        if any(p>=row['period']or p//100!=row['period']//100 for p in periods):raise ValueError('Coverage prior period leak')
        row['features'].update({(''if grain=='team'else'team_')+k:v for k,v in context['features'].items()});row['coverage_context']=deepcopy(context['window']);row['context_periods']=sorted(set(row.get('context_periods',[]))|set(periods))
    out['coverage_adapter']=dict(version=VERSION,source_refs=deepcopy(parent_refs),catalog_ids=['G14-M04','G14-M05'],columns=list(COVERAGE_COLUMNS),source_availability='Postseason revised observations; NOT original historical pregame proof.2026 source absent stays unknown',denominator='All classified nonspike dropbacks: MAN+ZONE+mixed+other; explicit unclassified and possible membership retained separately',no_assignment_inference=True)
    out['matrix_sha256']=digest({k:v for k,v in out.items()if k not in{'matrix_sha256','provenance'}})
    return out
