import gzip,hashlib
import pytest
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import bounded_chunks,verify,expand

def test_stream_and_expansion_caps_accept_boundary_without_truncation():
    assert bounded_chunks([b'a',b'bc'],3)==b'abc'
    assert expand(gzip.compress(b'abc'),3)==b'abc'

def test_stream_cap_rejects_oversize_instead_of_truncating_source():
    with pytest.raises(ValueError,match='Compressed'):bounded_chunks([b'ab',b'cd'],3)

def test_expansion_cap_rejects_compression_amplification():
    with pytest.raises(ValueError,match='serialization'):expand(gzip.compress(b'a'*1000),100)

def test_changed_source_hash_is_rejected():
    expected=hashlib.sha256(b'original').hexdigest();verify(b'original',expected)
    with pytest.raises(ValueError,match='SHA256'):verify(b'revised',expected)

def test_invalid_serialization_compression_is_not_guessed():
    with pytest.raises(gzip.BadGzipFile):expand(b'not gzip',100)

def test_nested_dataframe_export_preserves_columns_index_values_and_missingness():
    import json
    import pandas as pd
    import numpy as np
    from research.game_progression_pilot_20261020.raw_source_feasibility.containers import plain
    frame=pd.DataFrame({'playId':[1890,1900],'clock':[None,'00:59']},index=['a','b'])
    result=plain({'plays':frame,'missing':np.array([np.nan]),'flag':np.bool_(False)})
    assert result['plays']==dict(__r_container__='DataFrame',columns=['playId','clock'],index=['a','b'],data=[[1890,None],[1900,'00:59']])
    assert result['missing']==[None]and result['flag']is False
    json.dumps(result,allow_nan=False)

def test_native_linkage_preserves_ambiguity_and_clock_or_order_disagreement():
    from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import compare
    raw=[dict(playId=10,orderSequence=2,quarter=2,clockTime='01:09',playType='PASS',playDeleted=False)]
    processed=[dict(play_id=10,order_sequence=1,qtr=2,quarter_seconds_remaining=45,play_type_nfl='PASS',play_deleted=0)]
    out=compare(raw,processed)
    assert out['matched_ids']==[10]and out['differences']==[dict(play_id=10,fields=['order','start_clock'])]
    out=compare(raw+raw,processed)
    assert out['raw_ambiguous_or_missing_id_rows']==2 and not out['matched_ids']

def test_source_table_columns_and_invalid_snap_clocks_are_not_guessed():
    from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import table_records,quarter_seconds
    assert quarter_seconds('01:09')==69
    for value in ('2023-10-15T18:21:04Z','00:60','16:00',None):assert quarter_seconds(value)is None
    with pytest.raises(ValueError):table_records(dict(__r_container__='DataFrame',columns=['playId','playId'],data=[[1,2]]))

def test_raw_only_control_stop_is_bracketed_but_not_a_play_end_or_timeout_debit():
    from research.game_progression_pilot_20261020.raw_source_feasibility.controls import additional_controls
    rows=[dict(playId=1,orderSequence=1,quarter=2,clockTime='02:10'),
        dict(playId=9,orderSequence=2,quarter=2,clockTime='01:58',playType='TIMEOUT',playDeleted=False,playReviewStatus=None,playDescription='Two-Minute Warning'),
        dict(playId=3,orderSequence=3,quarter=2,clockTime='01:58')]
    out=additional_controls(rows,{1,3})[0]
    assert out['status']=='SOURCE_TYPED_CLOCK_STOP_OBSERVATION'and out['reason']=='SOURCE_REPORTED_TWO_MINUTE_WARNING'
    assert out['physical_play_end_clock']is None and out['restart_policy']is None and not out['timeout_budget_debit_proven']
    rows[2]['quarter']=3
    assert additional_controls(rows,{1,3})[0]['status']=='UNQUALIFIED_RAW_ONLY_RECORD'
    rows[2]['quarter']=2;rows[1]['playDeleted']=True
    assert additional_controls(rows,{1,3})[0]['status']=='UNQUALIFIED_RAW_ONLY_RECORD'
