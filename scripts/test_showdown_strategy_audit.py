"""Independent correctness checks for research evidence, not production changes."""
from contextlib import redirect_stdout
from io import StringIO
from itertools import combinations
from collections import Counter
import json
import subprocess
import numpy as np
import pandas as pd
from scripts.audit_showdown_strategy import OUT, SOURCE, DTYPE, prepare, export, read, PROFILE
from backend.app.product_services.optimizer import OptimizerService

def test_exhaustive_physical_denominator(tmp_path):
    data=read(SOURCE);rows=[r for r in data['forced_captains'] if (r['season'],r['week'],r['slate'])==(2024,7,'sunday_night')]
    frame,_=prepare(rows)
    # Canonical IDs, both teams and several positions; small exhaustive oracle.
    frame=frame.sort_values('salary',ascending=False).head(9).reset_index(drop=True)
    frame['salary']=(frame.salary//2).astype(int)
    frame['captain_salary']=(1.5*frame.salary).astype(int)
    export(frame,tmp_path/'input.txt')
    subprocess.run([str(OUT/'enumerator'),str(tmp_path/'input.txt'),str(tmp_path/'rows.bin'),str(tmp_path/'h.json')],check=True)
    expected=Counter()
    for ids in combinations(range(len(frame)),6):
        if frame.iloc[list(ids)].player_team.nunique()!=2:continue
        salary=frame.iloc[list(ids)].salary.sum();actual=frame.iloc[list(ids)].actual_points.sum()
        for cap in ids:
            if salary+frame.iloc[cap].captain_salary-frame.iloc[cap].salary<=50000:
                expected[round(actual+.5*frame.iloc[cap].actual_points,3)]+=1
    h=read(tmp_path/'h.json')
    assert h['physical_count']==sum(expected.values())
    assert {round(v,3):n for v,n in h['histogram']}==dict(expected)
    assert abs(h['oracle']-max(expected))<1e-8

def test_production_numeric_objective_parity():
    directory=OUT/'2024_7_sunday_night'
    frame=pd.DataFrame(read(directory/'prepared.json')['players'])
    a=np.fromfile(directory/'universe.bin',dtype=DTYPE)
    service=OptimizerService()
    eligible=np.flatnonzero(a['gate']==1)
    # Diverse score/rank witnesses, full frozen pool preserves QB reward scaling.
    samples=[int(eligible[np.argmax(a['scores'][eligible,0])]),int(eligible[np.argmax(a['mean'][eligible])]),
             int(eligible[np.argmax(a['p90'][eligible])]),int(eligible[len(eligible)//2]),int(eligible[-1])]
    for i in samples:
        row=a[i];ids=set(frame.iloc[list(row['ids'])].player_id);cap=frame.iloc[int(row['cap'])].player_id
        with redirect_stdout(StringIO()):
            solver_pool=frame.loc[frame.audit_gate & frame.showdown_qb_eligible].reset_index(drop=True)
            lineup=service._solve_lineup(solver_pool,score_col='optimizer_context_ceiling_score',contest_type='captain',
              stack_params={'hard_qb_correlations':True,'require_starting_qb':True,'saturate_correlations':True,
                 'opportunity_gate':True,'use_role_ownership':False,'max_players_per_team':5},
              locked_player_ids=ids,locked_captain_player_id=cap,rule_profile=PROFILE,include_control_comparison=False)
        assert lineup is not None
        assert {r['player_id'] for r in lineup}==ids
        assert abs(lineup[0]['solver_objective_value']-row['scores'][0])<1e-5
