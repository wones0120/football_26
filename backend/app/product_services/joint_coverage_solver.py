"""Exact finite-state coverage via set-cover feasibility, without assignment binaries."""
from copy import deepcopy
import math
import pulp
from .cbc_solver import make_cbc_solver


def solve_bounded(model,seconds=5):
    solver=make_cbc_solver();solver.timeLimit=seconds;model.solve(solver)
    return model.status==pulp.LpStatusOptimal and model.sol_status==pulp.LpSolutionOptimal


def optimize_coverage(model,chosen,scores):
    """Count already fixed. Binary search exact attainable best-roster levels."""
    normalized={sid:[v/max(values)for v in values]for sid,values in scores.items()}
    levels=sorted({v for values in normalized.values()for v in values});attempts=[]
    def covers(target,variables,level):
        for sid,values in normalized.items():
            target+=pulp.lpSum(variables[i]for i,v in enumerate(values)if v>=level-1e-10)>=1
    lo,hi=0,len(levels)-1
    while lo<hi:
        mid=(lo+hi+1)//2;trial=deepcopy(model);mapping=trial.variablesDict();variables={i:mapping[var.name]for i,var in chosen.items()}
        covers(trial,variables,levels[mid]);trial.setObjective(pulp.lpSum([]));proven=solve_bounded(trial)
        status='feasible'if proven else'infeasible'if trial.status==pulp.LpStatusInfeasible else'unproven_limit'
        attempts.append({'threshold':levels[mid],'status':status})
        if status=='unproven_limit':return None,attempts
        if proven:lo=mid
        else:hi=mid-1
    covers(model,chosen,levels[lo])
    return levels[lo],attempts
