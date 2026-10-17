"""All-game, bounded paired cheaper-teammate opportunity-cost research.

A cheaper player is not promoted for price alone. Conditional opportunity shares
conserve an attributed budget; both primary and secondary remain productive.
"""
from collections import Counter
from copy import deepcopy
import math,time
import pulp
from pydantic import BaseModel,ConfigDict,Field
from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver

class TeammateControls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_pairs:int=Field(default=3,ge=1,le=4,strict=True)
    max_solver_calls:int=Field(default=6,ge=2,le=8,strict=True)
    max_seconds:float=Field(default=30,ge=1,le=60,allow_inf_nan=False)
    minimum_salary_savings:int=Field(default=500,ge=0,le=4000,strict=True)
    minimum_backup_carries:float=Field(default=3,ge=0,le=10,allow_inf_nan=False)
    minimum_backup_targets:float=Field(default=2,ge=0,le=8,allow_inf_nan=False)
    share_transfer:float=Field(default=.10,ge=0,le=.15,allow_inf_nan=False)
    opportunity_shift:float=Field(default=.2,ge=.05,le=.25,allow_inf_nan=False)
    minimum_credibility:float=Field(default=.45,ge=.35,le=1,allow_inf_nan=False)


def number(row,key):
    value=row.get(key)
    return float(value) if type(value) in (int,float) and math.isfinite(value) else None

def team(row):return row.get('player_team',row.get('team'))
def pid(row):return str(row.get('player_id',row.get('player_master_id')))
def name(row):return row.get('name',row.get('player_name',pid(row)))


def scan_pairs(packet,source_rows,legal_rows,ideas,params,controls):
    legal={pid(r) for r in legal_rows};games=[];pairs=[]
    for game in packet['games']:
        if game.get('format_membership',{}).get('CLASSIC')!='confirmed_in_scope':continue
        game_pairs=[]
        for t in game['teams']:
            backs=[r for r in source_rows if team(r)==t and r['position']=='RB'];primaries=[r for r in backs if r.get('canonical_role',r.get('expected_depth_role'))=='expected_starter' and number(r,'projection') is not None]
            for primary in primaries:
                for backup in backs:
                    if pid(primary)==pid(backup) or number(backup,'salary') is None or float(backup['salary'])>=float(primary['salary']):continue
                    gap=float(primary['salary'])-float(backup['salary']);reason=None;story=None;channel=None
                    carries=number(backup,'projected_carries');targets=number(backup,'projected_targets')
                    if pid(primary) not in legal or pid(backup) not in legal:
                        reasons=[]
                        if str(backup.get('availability_status','')).upper() in {'Q','QUESTIONABLE'} and params.get('exclude_questionable'):reasons.append('current questionable exclusion retained; not an absence fact')
                        if float(backup['salary'])<float(params.get('minimum_rb_salary',0)):reasons.append('below explicit RB salary minimum')
                        if backup.get('role_optimizer_eligible') is False or backup.get('salary_status_eligible') is False:reasons.append('source role/salary ineligible')
                        reason='; '.join(reasons) or 'not in exact prepared legal pool (role/favored/exclusion/distribution controls retained)'
                    elif backup.get('canonical_role',backup.get('expected_depth_role'))!='expected_backup':reason='No reliable canonical secondary role'
                    elif gap<controls.minimum_salary_savings:reason='salary savings below configured threshold'
                    else:
                        options=[i for i in ideas if i['team']==t and i['credibility_score']>=controls.minimum_credibility and i.get('verified_source_ids')]
                        runs=[i for i in options if i['script']=='run_control'];passes=[i for i in options if i['script']=='passing']
                        if carries is not None and carries>=controls.minimum_backup_carries and runs:story=max(runs,key=lambda i:i['credibility_score']);channel='carries'
                        elif targets is not None and targets>=controls.minimum_backup_targets and passes:story=max(passes,key=lambda i:i['credibility_score']);channel='targets'
                        else:reason='No sourced credible matching game branch with supported secondary opportunity; cheapness alone insufficient'
                    item=dict(pair_id=game['game_id']+':'+pid(primary)+':'+pid(backup),game_id=game['game_id'],team=t,primary_id=pid(primary),backup_id=pid(backup),primary_name=name(primary),backup_name=name(backup),primary_salary=float(primary['salary']),backup_salary=float(backup['salary']),salary_saved=gap,primary_base_mean=number(primary,'projection'),backup_base_mean=number(backup,'projection'),primary_carries=number(primary,'projected_carries'),backup_carries=carries,primary_targets=number(primary,'projected_targets'),backup_targets=targets,backup_source_status=backup.get('availability_status'),backup_status_observed_at=backup.get('availability_observed_at'),backup_role_source=backup.get('role_source'),status='rejected' if reason else 'prescreened',reason=reason,idea_id=story['idea_id'] if story else None,channel=channel,source_ids=story['source_ids'] if story else [],credibility=story['credibility_score'] if story else None,
                        conditional_mechanism=('Run-control/late-volume rotation could increase a measured secondary carry share; primary remains active/productive' if channel=='carries' else 'Competitive passing/receiving-back usage could increase a measured secondary RB target share; primary remains active/productive') if story else None,
                        counterevidence=['Depth role does not prove a coaching split or late-game score.','Primary may retain every valuable touch/TD; saved averages can misrepresent current roles.','Unknown current practice/game-day dressing is not assumed healthy.','A user Q exclusion creates no factual vacancy.'])
                    game_pairs.append(item['pair_id']);pairs.append(item)
        games.append(dict(game_id=game['game_id'],teams=game['teams'],scanned_rb_count=sum(r['position']=='RB' and team(r) in game['teams'] for r in source_rows),pair_ids=game_pairs,coverage_status='scanned; no forced substitution' if game_pairs else 'scanned; no canonical cheaper secondary pairing'))
    ranked=sorted([p for p in pairs if p['status']=='prescreened'],key=lambda p:(-p['credibility']*min(1,p['salary_saved']/3000)*min(1,((p['backup_carries'] or 0)/8 if p['channel']=='carries' else (p['backup_targets'] or 0)/4)),p['pair_id']))
    return games,pairs,ranked


def paired_world(idea,pair,rows,packet,allocation_controls,controls):
    from .scenario_allocation import conditional_world
    world=conditional_world(idea,rows,packet,allocation_controls.model_copy(update={'opportunity_shift':controls.opportunity_shift}));channel=pair['channel'];members=[r for r in rows if team(r)==pair['team'] and r['position']=='RB'];values={pid(r):number(r,'projected_'+channel) for r in members}
    if any(v is None or v<0 for v in values.values()) or sum(values.values())<=0:raise ValueError('Complete attributed eligible RB opportunity budget unavailable')
    total=sum(values.values());base={p:v/total for p,v in values.items()};recipient=pair['backup_id'];donor=1-base[recipient];shift=controls.share_transfer
    if base[recipient]<=0 or donor<shift:raise ValueError('Positive secondary opportunity/donor budget missing')
    conditional={p:(v+shift if p==recipient else v*(1-shift/donor)) for p,v in base.items()}
    if any(v and not .5<=conditional[p]/v<=2 for p,v in base.items()):raise ValueError('Requested secondary share exceeds coherent 0.5–2 ratios')
    for r in members:
        p=pid(r);ratio=conditional[p]/base[p] if base[p] else 1;targets=number(r,'projected_targets') or 0;carries=number(r,'projected_carries') or 0;receiving=targets/(targets+carries) if targets+carries else 0;component=receiving if channel=='targets' else 1-receiving;response=1+.7*component*(ratio-1);m=world['moments'][p];spread=m['p90']-m['mean'];m['mean']*=response;m['p90']=m['mean']+spread*math.sqrt(response)
    world['scenario_id']='teammate:'+pair['pair_id'];world['paired_opportunity_budget']=dict(channel=channel,budget_scope='eligible RB '+channel,base_shares=base,conditional_shares=conditional,sum_before=sum(base.values()),sum_after=sum(conditional.values()),shift=shift,attributed_total_before=total,meaning='Conserved eligible-position allocation sensitivity; no excluded-player vacancy and no measured new forecast')
    return world


def investigate(snapshot,packet,source_rows,rows,ideas,params,allocation_controls,selected=None,discovery=None):
    controls=TeammateControls.model_validate(params.get('analyst_teammate_controls') or {});games,pairs,ranked=scan_pairs(packet,source_rows,rows,ideas,params,controls);lookup={pid(r):r for r in rows};by_idea={i['idea_id']:i for i in ideas};start=time.monotonic();calls=0;seen=set();evaluated=0
    report=dict(contract_id='analyst_teammate_opportunity_v1',mode='PAIRED_RESEARCH',baseline_mutation=False,automatic_portfolio_promotion=False,controls=controls.model_dump(),scanned_games=games,pairs=pairs,source_rows_sha256=digest(source_rows),legal_rows_sha256=digest(rows),scoring='DK-trained base forecasts with uncalibrated conditional opportunity response; conditional point checks are user what-ifs, not forecasts or objective bonuses')
    if params.get('analyst_teammate_choice'):ranked.sort(key=lambda pair:pair['pair_id']!=params['analyst_teammate_choice']['pair_id'])
    for pair in ranked:
        if evaluated>=controls.max_pairs or calls+2>controls.max_solver_calls or time.monotonic()-start>=controls.max_seconds:pair.update(status='not_evaluated_budget',reason='Bounded paired solver budget; no generic fallback');continue
        evaluated+=1;idea=by_idea[pair['idea_id']]
        try:world=paired_world(idea,pair,rows,packet,allocation_controls,controls)
        except ValueError as exc:pair.update(status='rejected',reason=str(exc));continue
        branches={}
        for label,required,omitted in [('primary',pair['primary_id'],pair['backup_id']),('cheaper',pair['backup_id'],pair['primary_id'])]:
            from .scenario_allocation import apply_idea
            variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']));player_vars={ref['player_master_id']:variables[n] for n,ref in snapshot['variable_players'].items()};apply_idea(model,variables,snapshot['variable_players'],rows,idea,allocation_controls)
            model+=player_vars[required]==1;model+=player_vars[omitted]==0
            for p,rate in (params.get('maximum_exposure_by_player') or {}).items():
                if float(rate)==0 and p in player_vars:model+=player_vars[p]==0
            model.setObjective(pulp.lpSum((world['moments'][p]['mean']+.35*(world['moments'][p]['p90']-world['moments'][p]['mean']))*v for p,v in player_vars.items()))
            if params.get('analyst_joint_opportunity_enabled'):
                from .joint_opportunity import enable_world,attach_objective
                enable_world(world,source_rows,packet);attach_objective(model,variables,snapshot['variable_players'],world,world['joint_opportunity'])
            solver=make_cbc_solver();solver.timeLimit=max(.1,controls.max_seconds-(time.monotonic()-start));solver.options.extend(['randomSeed 7','randomCbcSeed 7']);model.solve(solver);calls+=1
            branch=dict(solver_status=pulp.LpStatus[model.status],required_player_id=required,omitted_player_id=omitted,interpretation='Full same-branch roster research; omission is opportunity-cost comparison, not an absence or global eligibility rule')
            if model.status==pulp.LpStatusOptimal:
                chosen=sorted(p for p,v in player_vars.items() if pulp.value(v)>.5);signature=tuple(chosen);branch.update(roster=[dict(player_master_id=p,name=name(lookup[p]),position=lookup[p]['position'],team=team(lookup[p]),salary=float(lookup[p]['salary']),base_mean=float(lookup[p]['projection']),conditional_mean=world['moments'][p]['mean'],conditional_p90=world['moments'][p]['p90']) for p in chosen],roster_sha256=digest(chosen),duplicate_in_research=signature in seen,salary=sum(float(lookup[p]['salary']) for p in chosen),base_mean=sum(float(lookup[p]['projection']) for p in chosen),conditional_mean=sum(world['moments'][p]['mean'] for p in chosen),conditional_score=sum(world['moments'][p]['mean']+.35*(world['moments'][p]['p90']-world['moments'][p]['mean']) for p in chosen));seen.add(signature)
            if branch.get('roster') and params.get('analyst_joint_opportunity_enabled'):
                from .joint_opportunity import candidate_metric
                branch['conditional_score']=candidate_metric({'roster':[{'player_master_id':p['player_master_id'],'role':'SELECTED'} for p in branch['roster']]},world)
            branches[label]=branch
        pair.update(branches=branches,conditional_world=world)
        if any(b['solver_status']!='Optimal' for b in branches.values()):pair.update(status='infeasible',reason='Pair conflicts with exact frozen legality/locks/preferences; not relaxed');continue
        a,b=branches['primary'],branches['cheaper'];aid={p['player_master_id'] for p in a['roster']};bid={p['player_master_id'] for p in b['roster']};backup_mean=world['moments'][pair['backup_id']]['mean'];break_even=a['conditional_mean']-(b['conditional_mean']-backup_mean)
        checks=(params.get('analyst_teammate_point_checks') or {}).get(pair['backup_id'],[])
        from .analyst_challenger import feasible_portfolio
        candidate={'roster':[{'player_master_id':p['player_master_id'],'role':'SELECTED'} for p in b['roster']],'allocated_idea_id':pair['idea_id'],'discovery_finding_ids':[]}
        reservations=[i for i in (discovery or {}).get('reserved_idea_ids',[]) if any(c['allocated_idea_id']==i and c.get('discovery_finding_ids') for c in (selected or []))]
        possible=[i for i in range(len(selected or [])) if feasible_portfolio([c for j,c in enumerate(selected) if j!=i]+[candidate],rows,params,len(selected),allocation_controls,reservations)]
        pair['possible_portfolio_replacement_slots']=[i+1 for i in possible]
        pair['portfolio_admission_status']='hard-controls-feasible research alternative' if possible else 'cannot replace a selected slot under unchanged portfolio/user/discovery controls'
        pair.update(status='paired_evaluated',mean_improves=b['conditional_mean']>a['conditional_mean'],score_improves=b['conditional_score']>a['conditional_score'],base_mean_delta=b['base_mean']-a['base_mean'],conditional_mean_delta=b['conditional_mean']-a['conditional_mean'],conditional_score_delta=b['conditional_score']-a['conditional_score'],salary_saved_reinvested=pair['salary_saved']-(a['salary']-b['salary']),added_player_ids=sorted(bid-aid),removed_player_ids=sorted(aid-bid),conditional_secondary_mean=backup_mean,secondary_points_break_even=break_even,conditional_point_checks=[dict(secondary_points=float(points),full_lineup_conditional_mean=b['conditional_mean']-backup_mean+float(points),delta_vs_primary=b['conditional_mean']-backup_mean+float(points)-a['conditional_mean'],classification='USER_CONDITIONAL_WHAT_IF; not expected projection or optimization bonus') for points in checks],reason='Salary reinvestment improves the whole conditional roster' if b['conditional_score']>a['conditional_score'] else 'Salary savings do not offset conditional full-roster cost under this bounded share sensitivity')
    report.update(solver_calls=calls,evaluated_pairs=evaluated,distinct_research_rosters=len(seen),status='completed',constraints_relaxed=False,portfolio_effect='Research pairs are saved separately; no automatic promotion. Existing selected portfolio/discovery reservations/exposures remain unchanged.')
    return report


def validate_choice(service,params,packet,source_rows,projection_run_id):
    """A saved alternative can be reapplied only to its actual immutable inputs."""
    choice=params.get('analyst_teammate_choice')
    if not choice:return
    from .analyst_packets import packet_digest
    job=service.get_job(choice['source_optimizer_run_id'])
    report=((job.params.get('strategy_runtime') or {}).get('football_analyst') or {}) if job else {}
    if not job or job.status!='completed' or str(job.projection_run_id)!=str(projection_run_id):raise ValueError('Saved teammate choice requires its completed matching projection research run')
    if report.get('packet_sha256')!=packet_digest(packet) or (report.get('teammate_opportunity') or {}).get('source_rows_sha256')!=digest(source_rows):raise ValueError('Saved teammate choice packet/source snapshot mismatch; rescan the current inputs')
    pair=next((p for p in report['teammate_opportunity']['pairs'] if p['pair_id']==choice['pair_id']),None)
    if not pair or pair['status']!='paired_evaluated' or pair['branches']['cheaper']['solver_status']!='Optimal':raise ValueError('Saved teammate alternative is not a legal completed paired comparison')


def apply_choice(selected,worlds,report,rows,params,allocation_controls,discovery):
    """Explicit human choice gets one lineup after full portfolio revalidation."""
    choice=params.get('analyst_teammate_choice')
    if not choice:return selected,worlds
    from .analyst_challenger import feasible_portfolio,metric,canonical_roster
    pair=next((p for p in report['pairs'] if p['pair_id']==choice['pair_id']),None)
    if not pair or pair['status']!='paired_evaluated':raise ValueError('Requested teammate alternative is infeasible under current role/salary/locks/preferences')
    branch=pair['branches']['cheaper'];candidate=dict(roster=[dict(player_master_id=p['player_master_id'],role='SELECTED') for p in branch['roster']],allocated_idea_id=pair['idea_id'],allocation_slot=len(selected)+1,planned_idea_id=pair['idea_id'],scenario_ids=[pair['conditional_world']['scenario_id']],opportunity_budget=pair['conditional_world']['opportunity_budget'],discovery_finding_ids=[],construction_compliance=True,construction_audit={'passed':True,'meaning':'Exact same-branch paired legal model, independently roster-verified in saved research'},teammate_pair_id=pair['pair_id'],teammate_source_optimizer_run_id=choice['source_optimizer_run_id'])
    combined=worlds+[pair['conditional_world']];reservations=[i for i in discovery['reserved_idea_ids'] if any(c['allocated_idea_id']==i and c.get('discovery_finding_ids') for c in selected)]
    possibilities=[]
    for slot in range(len(selected)):
        portfolio=selected[:slot]+[candidate]+selected[slot+1:]
        if not feasible_portfolio(portfolio,rows,params,len(selected),allocation_controls,reservations):continue
        score=sum(max(metric(c,w) for c in portfolio) for w in combined);possibilities.append((score,slot,portfolio))
    if not possibilities:raise ValueError('Requested teammate choice conflicts with hard portfolio exposures/uniqueness/discovery reservations; no relaxation')
    _,slot,portfolio=max(possibilities,key=lambda item:(item[0],-item[1]))
    for c in portfolio:c['scores']={w['scenario_id']:metric(c,w) for w in combined}
    report['applied_choice']=dict(source_optimizer_run_id=choice['source_optimizer_run_id'],pair_id=pair['pair_id'],branch='cheaper',replaced_allocation_slot=slot+1,possible_replacement_slots=[s+1 for _,s,_ in possibilities],negative_conditional_cost_accepted_by_explicit_choice=not pair['score_improves'],conditional_assumption='User explicitly chose this saved same-game cheaper-player hypothesis; no source status or base projection changed',constraints_relaxed=False)
    report.update(mode='APPLIED_CONDITIONAL_ALTERNATIVE',portfolio_effect='Explicit user choice replaced one allocation slot after hard portfolio revalidation; remaining slots and discovery reservations retained. Paired comparison deltas are separate from the selected portfolio revision.')
    return portfolio,combined
