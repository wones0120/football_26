"""Focused chronology, input, stopping and checkpoint contracts."""
import importlib.util,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tree_tuning_run',HERE/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)

def test_frozen_inputs_chronology_no_label_predictors():
 frame,families=run.load();freeze=json.loads((HERE/'freeze.json').read_text());assert freeze['fit_budget']==180;assert not freeze['production_mutations'];assert not freeze['future_labels_loaded']
 for fold in freeze['folds']:assert fold['fit_end']<min(fold['stop'])<=max(fold['stop'])<min(fold['select'])<min(fold['calibrate'])<min(fold['assess'])
 for cols in families.values():assert not set(cols)&set(run.v4.TARGETS);assert not any(c.startswith('ctx_') for c in cols)
 assert frame.player_master_id.notna().all();assert not frame.index.duplicated().any()

def test_selection_and_stopping_only_use_past_scores():
 result=json.loads((HERE/'results.json').read_text())
 for key,record in result['records'].items():
  assert record['selected']==min(range(len(record['options'])),key=lambda i:(record['options'][i]['selection_score'],i))
  for item in record['options']:
   assert item['complexity']['iterations']<=item['config']['max_iter']
   if 'curve' in item:
    best=min(item['curve'],key=lambda s:(s['stopping_selection_score'],s['iterations']));assert item['complexity']['iterations']==best['iterations'];assert np.isclose(item['best_stop_score'],best['stopping_selection_score'])
    assert item['fit_period_end']<min(item['stop_periods']);assert item['complexity']['maximum_actual_depth']<=item['config']['max_depth'] if item['config']['max_depth'] is not None else True

def test_exact_model_replay_and_prior_control_parity():
 summary=json.loads((HERE/'summary.json').read_text());assert len(summary['verification'])==36;assert summary['rows_replayed']==33072;assert all(x['max_error']<1e-10 for x in summary['verification']);assert summary['f3_old_control_parity_max_error']<1e-8
