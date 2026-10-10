"""Offline full-universe audit of the corrected ATL–NO projection freeze.

No optimizer defaults, projection values, or database rows are written.
Run with .venv/bin/python -m scripts.audit_atl_no_projection_landscape.
"""
from collections import Counter
from itertools import combinations
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pulp

from scripts.enumerate_showdown_policy_universe import certify
from scripts.run_showdown_qb_policy_experiment import read, write, solver, POLICIES, TEAM_LIMITS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/current_slate_role_audit/corrected_v2"
DEST = ROOT / "artifacts/atl_no_projection_landscape"
FLOORS = (.95, .94, .93, .92, .90)


def certify_batch(template, captains, indices):
    """Vectorized binary interval propagation against every saved constraint.

    Fully resolved assignments are exact witnesses. Ambiguous cases use the
    existing scalar certifier/CBC; no soft score rule is treated as legality.
    """
    variables = template["variables"]
    names = [v["name"] for v in variables]
    lookup = {name: i for i, name in enumerate(names)}
    lo = np.tile([v["lowBound"] for v in variables], (len(indices), 1)).astype(float)
    hi = np.tile([v["upBound"] for v in variables], (len(indices), 1)).astype(float)
    alive = np.ones(len(indices), dtype=bool)
    roles = {name for name in names if name.startswith(("captain_", "flex_"))}
    for name in roles:
        i = int(name.split("_")[1])
        value = (captains == i) if name.startswith("captain_") else ((indices == i).any(axis=1) & (captains != i))
        j = lookup[name]
        alive &= (value >= lo[:, j]) & (value <= hi[:, j])
        lo[:, j] = hi[:, j] = value
    constraints = []
    for c in template["constraints"]:
        js = np.array([lookup[t["name"]] for t in c["coefficients"]])
        co = np.array([t["value"] for t in c["coefficients"]])
        constraints.append((js, co, c["constant"], c["sense"]))
    for _ in range(len(names)):
        changed = False
        for js, co, constant, sense in constraints:
            lower_terms = np.where(co >= 0, lo[:, js], hi[:, js]) * co
            upper_terms = np.where(co >= 0, hi[:, js], lo[:, js]) * co
            lower = lower_terms.sum(axis=1) + constant
            upper = upper_terms.sum(axis=1) + constant
            alive &= ~(((sense <= 0) & (lower > 1e-6)) | ((sense >= 0) & (upper < -1e-6)))
            for k, j in enumerate(js):
                if names[j] in roles:
                    continue
                pending = alive & (lo[:, j] != hi[:, j])
                if not pending.any():
                    continue
                l0, u0 = lower - lower_terms[:, k], upper - upper_terms[:, k]
                zero = ~(((sense <= 0) & (l0 > 1e-6)) | ((sense >= 0) & (u0 < -1e-6)))
                one = ~(((sense <= 0) & (l0 + co[k] > 1e-6)) | ((sense >= 0) & (u0 + co[k] < -1e-6)))
                alive &= ~(pending & ~zero & ~one)
                forced = pending & (zero != one)
                if forced.any():
                    lo[forced, j] = hi[forced, j] = one[forced]
                    changed = True
        if not changed:
            break
    objective = np.zeros(len(indices))
    for term in template["objective"]["coefficients"]:
        objective += term["value"] * lo[:, lookup[term["name"]]]
    unresolved = alive & (lo != hi).any(axis=1)
    for row in np.flatnonzero(unresolved):
        score = certify(template, int(captains[row]), tuple(indices[row]))
        alive[row] = score is not None
        if score is not None:
            objective[row] = score
    return alive, objective, int(unresolved.sum())


def enumerate_full(snapshot):
    target = DEST / "full_universe.npz"
    if target.exists():
        return dict(np.load(target)), read(DEST / "enumeration.json")
    players = snapshot["player_pool"]
    groups = np.array(list(combinations(range(len(players)), 6)), dtype=np.int16)
    indices = np.repeat(groups, 6, axis=0)
    captains = groups.reshape(-1)
    salaries = np.array([p["salary"] for p in players])
    salary = salaries[indices].sum(axis=1) + .5 * salaries[captains]
    teams = np.array([p["player_team"] == "NO" for p in players])
    no_count = teams[indices].sum(axis=1)
    pre = (salary <= 50000 + 1e-8) & (no_count >= 1) & (no_count <= 5)
    indices, captains = indices[pre], captains[pre]
    salary, no_count = salary[pre], no_count[pre]
    legal, selectors = [], []
    unresolved = 0
    for start in range(0, len(indices), 10000):
        stop = min(start + 10000, len(indices))
        ok, score, ambiguous = certify_batch(snapshot["solver_model"], captains[start:stop], indices[start:stop])
        legal.append(ok); selectors.append(score); unresolved += ambiguous
        if start % 100000 == 0:
            print("certified", stop, "of", len(indices), flush=True)
    ok = np.concatenate(legal)
    ids, cpt = indices[ok], captains[ok]
    projections = np.array([p["projection"] for p in players])
    p90 = np.array([p["p90"] for p in players])
    qb = np.array([p["position"] == "QB" for p in players])
    arrays = dict(indices=ids, captain=cpt, salary=salary[ok], no_count=no_count[ok],
                  mean=projections[ids].sum(axis=1)+.5*projections[cpt],
                  p90=p90[ids].sum(axis=1)+.5*p90[cpt], selector=np.concatenate(selectors)[ok],
                  qb_count=qb[ids].sum(axis=1), qb_captain=qb[cpt])
    np.savez_compressed(target, **arrays)
    summary = dict(all_six_player_captain_signatures=len(groups)*6,
                   salary_team_legal_signatures=int(pre.sum()), saved_model_legal_signatures=int(ok.sum()),
                   ambiguous_scalar_fallback=unresolved,
                   method="Full enumeration, all saved binary bounds and MILP constraints; vectorized interval certificates with scalar/CBC fallback")
    write(DEST / "enumeration.json", summary)
    return arrays, summary


def row_detail(a, index, players):
    ids = a["indices"][index]
    captain = int(a["captain"][index])
    qb_stacks = {}
    for i in ids:
        p = players[i]
        if p["position"] == "QB":
            qb_stacks[p["name"]] = [players[j]["name"] for j in ids
                if players[j]["position"] in ("WR", "TE") and players[j]["player_team"] == p["player_team"]]
    return dict(index=int(index), captain=players[captain]["name"],
                captain_player_id=players[captain]["player_id"],
                players=[players[i]["name"] for i in ids],
                player_ids=[players[i]["player_id"] for i in ids],
                **{k:float(a[k][index]) for k in ("mean", "p90", "selector", "salary")},
                team_split=f"ATL {6-int(a['no_count'][index])}/NO {int(a['no_count'][index])}",
                qb_count=int(a["qb_count"][index]), qb_stacks=qb_stacks)


def frequencies(a, rows, players):
    return {p["name"]:float((a["indices"][rows] == i).any(axis=1).mean()) if len(rows) else None
            for i,p in enumerate(players)}


def universe_stats(a, rows, players):
    appearances = np.bincount(a["indices"][rows].ravel(), minlength=len(players))
    n = len(rows)
    overlap = sum(int(x)*(int(x)-1)/2 for x in appearances) / (n*(n-1)/2) if n > 1 else None
    return dict(count=n, unique_captains=len(set(a["captain"][rows].tolist())),
                unique_players=int((appearances > 0).sum()), player_frequencies=frequencies(a,rows,players),
                average_pairwise_overlap=overlap,
                team_split_distribution=dict(Counter(f"ATL {6-int(v)}/NO {int(v)}" for v in a["no_count"][rows])),
                qb_count_distribution=dict(Counter(map(str,a["qb_count"][rows]))),
                average_mean=float(a["mean"][rows].mean()) if n else None,
                average_p90=float(a["p90"][rows].mean()) if n else None)


def portfolio(a, rows, players, limits, captain_limit, *, relax_players=False, relax_captains=False):
    """Maximize count (up to requested five), then summed frozen selector."""
    model = pulp.LpProblem("FrozenLandscapePortfolio", pulp.LpMaximize)
    vs = [pulp.LpVariable(f"signature_{i}", cat="Binary") for i in range(len(rows))]
    count = pulp.lpSum(vs)
    model += count <= 5
    for i,p in enumerate(players):
        if not relax_players:
            model += pulp.lpSum(vs[j] for j,r in enumerate(rows) if i in a["indices"][r]) <= limits[p["player_id"]]
        if not relax_captains:
            model += pulp.lpSum(vs[j] for j,r in enumerate(rows) if a["captain"][r] == i) <= captain_limit
    model.setObjective(count)
    assert model.solve(solver()) == pulp.LpStatusOptimal
    maximum = int(round(pulp.value(count) or 0))
    model += count == maximum
    model.setObjective(pulp.lpSum(v*a["selector"][r] for v,r in zip(vs,rows)))
    assert model.solve(solver()) == pulp.LpStatusOptimal
    selected = np.array([r for v,r in zip(vs,rows) if v.value() > .5],dtype=int)
    counts=Counter(i for r in selected for i in a["indices"][r])
    cpts=Counter(a["captain"][selected])
    assert len(selected)==maximum and len(set(selected))==maximum
    if not relax_players:
        assert all(counts[i] <= limits[p["player_id"]] for i,p in enumerate(players))
    if not relax_captains:
        assert all(x <= captain_limit for x in cpts.values())
    return dict(maximum_feasible_count=maximum, selector=float(a["selector"][selected].sum()),
                metrics=universe_stats(a,selected,players), witness=[row_detail(a,r,players) for r in selected],
                proof="CBC optimal on exhaustive signature set; count first, selector second; unique signatures")


def analyze(snapshot,a):
    players=snapshot["player_pool"]
    result={}
    shough=next(i for i,p in enumerate(players) if p["name"]=="Tyler Shough")
    for label in POLICIES:
        allow,maximum=POLICIES[label]
        legal=(a["qb_count"]<=maximum) & ((~a["qb_captain"]) | allow)
        team_limit=TEAM_LIMITS.get(label,5)
        legal &= (a["no_count"]<=team_limit) & (6-a["no_count"]<=team_limit)
        rows=np.flatnonzero(legal)
        maxima={k:float(a[k][rows].max()) for k in ("mean","p90")}
        run=read(SOURCE/f"controlled-{label}.json")
        assert abs(maxima["mean"]-run["selection_report"]["best_mean"])<1e-6
        assert abs(maxima["p90"]-run["selection_report"]["best_p90"])<1e-6
        limits=run["selection_kwargs"]["player_limits"]; captain_limit=run["selection_kwargs"]["captain_limit"]
        ratios={k:a[k]/maxima[k] for k in maxima}
        quality=np.minimum(ratios["mean"],ratios["p90"])
        thresholds={}
        base90=legal & (quality>=.9-1e-8)
        for floor in FLOORS:
            qm=ratios["mean"]>=floor-1e-8; qp=ratios["p90"]>=floor-1e-8
            eligible=np.flatnonzero(legal & qm & qp)
            rejection=lambda mask:dict(mean_only=int((mask & ~qm & qp).sum()),
                p90_only=int((mask & qm & ~qp).sum()),both=int((mask & ~qm & ~qp).sum()),pass_both=int((mask & qm & qp).sum()))
            entry=dict(fraction=floor,legal_physical_rosters=len(rows),
                       quality_universe=universe_stats(a,eligible,players),
                       mean_only_pass=int((legal & qm).sum()),p90_only_pass=int((legal & qp).sum()),
                       rejection_all_legal=rejection(legal),rejection_within_joint90=rejection(base90))
            entry['rejection_within_either90']=rejection(legal & ((ratios['mean']>=.90-1e-8)|(ratios['p90']>=.90-1e-8)))
            if label in "AEB" or floor==.95:
                entry["portfolio"]=portfolio(a,eligible,players,limits,captain_limit)
            thresholds[str(floor)]=entry
            print(label,floor,len(eligible),entry.get("portfolio",{}).get("maximum_feasible_count"),flush=True)
        ranked=rows[np.argsort(-a["selector"][rows],kind="stable")]
        top={}
        for pct in (.01,.05,.1,.25):
            n=math.ceil(len(ranked)*pct)
            # Include ties at the boundary, so arbitrary ID order cannot change frequency.
            rankrows=rows[a["selector"][rows]>=a["selector"][ranked[n-1]]-1e-6]
            top[str(pct)]=dict(nominal_count=n,tie_inclusive_count=len(rankrows),
                             minimum_selector=float(a["selector"][ranked[n-1]]),
                             player_frequencies=frequencies(a,rankrows,players))
        extrema={k:row_detail(a,rows[np.argmax(a[k][rows])],players) for k in ("mean","p90","selector")}
        has=(a["indices"]==shough).any(axis=1)
        shough_best={}
        for presence in (True,False):
            subset=rows[has[rows]==presence]
            best={k:row_detail(a,subset[np.argmax(a[k][subset])],players) for k in ("mean","p90","selector")}
            joint=subset[np.argmax(quality[subset])]
            best["joint_quality"]=row_detail(a,joint,players)
            best["maximum_joint_fraction"]=float(quality[joint])
            best["independent_threshold_gaps"]={k:float(a[k][subset].max()-.95*maxima[k]) for k in maxima}
            best["joint_witness_threshold_gaps"]={k:float(a[k][joint]-.95*maxima[k]) for k in maxima}
            shough_best[str(presence)]=best
        eligible=np.flatnonzero(legal & (quality>=.95-1e-8))
        ablations={name:portfolio(a,eligible,players,limits,captain_limit,**kw)["maximum_feasible_count"]
            for name,kw in (("no_player_caps",dict(relax_players=True)),("no_captain_caps",dict(relax_captains=True)),
                            ("no_exposure_caps",dict(relax_players=True,relax_captains=True)))}
        without={}
        for i,p in enumerate(players):
            subset=rows[~(a["indices"][rows]==i).any(axis=1)]
            without[p["name"]]=dict(best_joint_fraction=float(quality[subset].max()),
                best_mean=float(a["mean"][subset].max()),best_p90=float(a["p90"][subset].max()))
        # Isolate salary relief with the original policy-specific floors held fixed.
        # This diagnostic never changes football projections or a live constraint.
        from scripts.audit_showdown_qb_policy_feasibility import policy_model, quality_expressions
        for i,p in enumerate(players):
            if p['salary']>3000 and i!=shough:
                continue
            model,cap,flex=policy_model(snapshot,label)
            salary_names={f'{role}_{j}' for j in range(len(players)) for role in ('captain','flex')}
            salary_constraints=[name for name,c in model.constraints.items()
                if abs(c.constant+50000)<1e-8 and {v.name for v in c.keys()}.issubset(salary_names)
                and len(c)==2*len(players)]
            assert len(salary_constraints)==1
            del model.constraints[salary_constraints[0]]
            model += cap[i]+flex[i]==0
            fraction=pulp.LpVariable('fixed_floor_quality',lowBound=0)
            ex=quality_expressions(snapshot,cap,flex)
            model += ex['projection']>=fraction*maxima['mean']
            model += ex['p90']>=fraction*maxima['p90']
            model.setObjective(fraction)
            assert model.solve(solver())==pulp.LpStatusOptimal
            without[p['name']]['no_salary_limit_joint_fraction']=float(fraction.value())
        with gzip.open(DEST/f'rejection_band_{label}.csv.gz','wt') as f:
            w=csv.writer(f);w.writerow(['universe_index','captain_player_id','player_ids','mean_ratio','p90_ratio']+[f'reason_{floor:.0%}' for floor in FLOORS])
            for r in np.flatnonzero(legal & ((ratios['mean']>=.90-1e-8)|(ratios['p90']>=.90-1e-8))):
                reasons=[]
                for floor in FLOORS:
                    failed=[k for k in ratios if ratios[k][r]<floor-1e-8]
                    reasons.append('both' if len(failed)==2 else f'{failed[0]}_only' if failed else 'pass_both')
                w.writerow([int(r),players[a['captain'][r]]['player_id'],';'.join(players[i]['player_id'] for i in a['indices'][r]),ratios['mean'][r],ratios['p90'][r]]+reasons)
        result[label]=dict(legal_physical_rosters=len(rows),raw_maxima=maxima,extrema=extrema,
            independent_maxima_same_signature=extrema["mean"]["index"]==extrema["p90"]["index"],
            thresholds=thresholds,selector_rank_frequencies=top,shough_best=shough_best,
            cap_ablation95=ablations,best_without_player=without,player_limits=limits,captain_limit=captain_limit)
    return result


def capture_decomposition():
    """Read one exact fitted artifact and cutoff-safe source evidence."""
    from sqlalchemy import text
    import pandas as pd
    from backend.app.db import engine
    from backend.app.product_services.model_artifacts import load_run_artifact,tree_path_attributions
    from backend.app.product_services.predictions import blend_point_predictions,apply_opportunity_point_adjustment,kicker_point_estimates,derive_calibration_roles,apply_residual_calibration
    s=read(SOURCE/'prepared_input.json')
    with engine.connect() as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        payload,lineage=load_run_artifact(c,s['projection_run_id'])
        target=payload['target'];train=payload['train'];cols=payload['feature_columns']
        raw=payload['raw_predictions'];base=blend_point_predictions(raw,train,target)
        means,details=apply_opportunity_point_adjustment(base,train,target)
        kicker,_=kicker_point_estimates(target)
        roles=derive_calibration_roles(target)
        players=[]
        for p in s['player_pool']:
            index=target.index[target['player_id'].eq(p['player_id'])][0];t=target.loc[index].to_dict()
            position=t['position'];role=roles.loc[index]
            explicit=str(t.get('pregame_role_label') or '').upper()
            if explicit in {'LEAD','COMMITTEE','PRIMARY','SECONDARY','ROTATION'}:role=explicit
            key=f'{position}|{role}'
            split=payload['calibration'].get('importance_splits_by_role',{}).get(key)
            if split is not None:key += '|importance_'+('high' if t['offensive_role_importance']>=split else 'low')
            profiles=payload['profiles'];profile=profiles.get(key,profiles.get(f'{position}|{role}',profiles.get(position,profiles['__ALL__'])))
            market=float(t.get('market_team_point_adjustment',0))
            point=float(kicker.loc[index]) if position=='K' else float(means[index])+market
            participation=float(t.get('pregame_availability_probability',1))*(float(t.get('pregame_start_probability',1)) if position=='QB' else 1)
            final=point*participation;p90=apply_residual_calibration(point,profile)['p90']*participation
            assert abs(final-p['projection'])<1e-6,(p['name'],final,p['projection'])
            assert abs(p90-p['p90'])<1e-6
            drivers=tree_path_attributions(payload['model'],target.loc[[index],cols].apply(pd.to_numeric,errors='coerce').fillna(0))
            # Exact intercept plus all path terms reproduces the raw tree prediction.
            intercept=float(raw[index])-sum(drivers.values())
            history=.6*float(t['player_roll3_mean'])+.4*float(t['player_roll8_mean'])
            fallback=t['player_games_history']<3
            if fallback:history=payload['calibration']['point_estimate']['position_training_means'][position]
            players.append(dict(player_id=p['player_id'],name=p['name'],target_features=t,
                raw_tree_mean=float(raw[index]),tree_intercept=intercept,tree_path_drivers=drivers,
                history_anchor=history,history_fallback=fallback,base_blended_mean=float(base[index]),
                opportunity=details.loc[index].to_dict(),market_residual_adjustment=market,
                mean=final,p90=p90,participation=participation,calibration_key=key,
                calibration_profile=dict(sample_size=profile.sample_size,source=profile.source,residual_quantiles=profile.residual_quantiles)))
        cutoff=target['data_cutoff_at'].iloc[0] if 'data_cutoff_at' in target else '2026-10-05T21:06:44.629683+00:00'
        usage=[dict(r) for r in c.execute(text('''
            WITH latest AS (
                SELECT DISTINCT ON (season,week,player_id) raw_nfl_weekly_stat_id,season,week,player_id,team,position,raw_row_json,created_at
                FROM public.raw_nfl_weekly_stat WHERE created_at<=:cutoff AND (season<2026 OR (season=2026 AND week<4))
                ORDER BY season,week,player_id,created_at DESC,raw_nfl_weekly_stat_id DESC)
            SELECT raw.*,alias.player_master_id::TEXT AS canonical_player_id FROM latest raw
            JOIN public.player_alias alias ON alias.source_system='nflreadpy' AND alias.source_key=raw.player_id
            WHERE alias.player_master_id::TEXT=ANY(:ids)
            ORDER BY canonical_player_id,season,week
        '''),dict(cutoff=cutoff,ids=[p['player_id'] for p in s['player_pool']])).mappings()]
        snaps=[dict(r) for r in c.execute(text('''
            SELECT * FROM public.curated_player_game_participation
            WHERE player_master_id::TEXT=ANY(:ids) AND created_at<=:cutoff AND (season<2026 OR (season=2026 AND week<4))
            ORDER BY player_master_id,season,week,created_at
        '''),dict(cutoff=cutoff,ids=[p['player_id'] for p in s['player_pool']])).mappings()]
    write(DEST/'projection_bridge.json',dict(projection_run_id=s['projection_run_id'],artifact_sha256=lineage['artifact_sha256'],training_dataset_sha256=lineage['training_dataset_sha256'],feature_columns=cols,players=players))
    write(DEST/'prior_usage.json',dict(cutoff=cutoff,weekly_stats=usage,participation=snaps))
    print('Exact mean/P90 bridge verified for',len(players),'players',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['capture','enumerate','analyze'],default='analyze')
    args=p.parse_args();DEST.mkdir(exist_ok=True)
    if args.stage=='capture':capture_decomposition();return
    snapshot=read(SOURCE/'prepared_input.json')
    assert snapshot['projection_run_id']=='023ae6d0-a700-4608-95fd-453029585d94'
    a,enum=enumerate_full(snapshot)
    # Independent scalar certificate check includes all prior retained signatures
    # plus deterministic samples throughout the complete universe.
    prior=read(SOURCE/'ranked-universe.json')['rows']
    keyed={(int(c),tuple(ids)):r for r,(c,ids) in enumerate(zip(a['captain'],a['indices']))}
    for row in prior:
        index=keyed[(row['captain_index'],tuple(row['indices']))]
        assert abs(a['selector'][index]-row['selector'])<1e-6
    for r in np.linspace(0,len(a['captain'])-1,101,dtype=int):
        assert abs(certify(snapshot['solver_model'],int(a['captain'][r]),tuple(a['indices'][r]))-a['selector'][r])<1e-6
    if args.stage=='enumerate':return
    result=analyze(snapshot,a)
    certificates=read(SOURCE/'corrected_feasibility.json')
    for label in POLICIES:
        baseline=result[label]['thresholds']['0.95']
        assert baseline['quality_universe']['count']==certificates[label]['complete_quality_signatures']
        assert baseline['portfolio']['maximum_feasible_count']==certificates[label]['exact_maximum_count']
        assert abs(baseline['portfolio']['selector']-certificates[label]['global_optimal_selector'])<1e-6
    manifest={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [SOURCE/'prepared_input.json',SOURCE/'input_freeze.json',SOURCE/'corrected_feasibility.json',Path(__file__)]}
    write(DEST/'analysis_v2.json',dict(projection_run_id=snapshot['projection_run_id'],source_sha256=manifest,
        enumeration=enum,policies=result,validation='All A–F 95% counts/maxima/selectors match independent prior certificates; all prior retained selector values and 101 full-universe scalar certificates match.'))
    with (DEST/'player_efficiency.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['player_id','name','team','position','salary','mean','p90','mean_per_1000','p90_per_1000'])
        for row in snapshot['player_pool']:
            w.writerow([row[k] for k in ['player_id','name','player_team','position','salary','projection','p90']]+[1000*row[k]/row['salary'] for k in ['projection','p90']])


if __name__=='__main__':main()
