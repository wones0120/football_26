from scripts.audit_generation_selection import coverage, diagnose, paid_above_cutoff


def test_stage_diagnosis_does_not_blame_ranker_for_quality_rejection():
    assert diagnose(False, False, True, False, True) == 'quality_or_constraint_screen_or_unrecorded_eligibility'
    assert diagnose(False, False, True, True, True) == 'eligible_pool_shortlisting_miss'
    assert diagnose(False, True, True, True, True) == 'final_selection_miss'
    assert diagnose(False, False, False, False, False) == 'incomplete_pool_evidence'
    assert diagnose(False, False, False, False, True) == 'no_paid_candidate_in_saved_pool'
    assert diagnose(True, True, True, True, True) == 'recommended_paid'
    assert diagnose(None, True, True, True, True) == 'unknown'


def test_paid_cutoff_keeps_missing_and_boundary_ties_unknown():
    assert paid_above_cutoff(100,100) is None
    assert paid_above_cutoff(None,100) is None
    assert paid_above_cutoff(100,None) is None
    assert paid_above_cutoff(101,100) is True
    assert paid_above_cutoff(99,100) is False


def test_coverage_deduplicates_variants_and_does_not_zero_missing_actuals():
    rows=[dict(candidate_id='a',actual_points=150),dict(candidate_id='a',actual_points=150),
          dict(candidate_id='b',actual_points=None)]
    result=coverage(rows)
    assert result['unique']==2 and result['scoreable']==1
    assert result['best']['actual_points']==150
    assert result['complete'] is False
    assert coverage([])['complete'] is False
