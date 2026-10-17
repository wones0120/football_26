import hashlib,json

import pandas as pd
import pytest

from backend.app.product_services.dst_training_labels import SCORING_CONTRACT,read_verified_correction,select_corrected_dst_labels


def fixture():
    row=dict(player_game_feature_matrix_id=1,season=2026,week=5,player_master_id='canonical-uuid',team='PHI',opponent='JAX',game_id='2026_05_PHI_JAX',source_system='draftkings',position='DST',label_dk_total_points=0.,salary=3000)
    correction={**row,'dk_points':5.,'dst_scoring_contract':SCORING_CONTRACT,'dst_source_sha256':'source-hash'}
    return pd.DataFrame([row]),dict(contract_id=SCORING_CONTRACT,rows=[correction])


def select(frame,data):return select_corrected_dst_labels(frame,data,target_season=2026,target_week=6)


def test_exact_selection_changes_only_label_and_preserves_input():
    frame,data=fixture();result,audit=select(frame,data)
    assert result.label_dk_total_points.tolist()==[5.]
    assert frame.label_dk_total_points.tolist()==[0.]
    assert result.drop(columns='label_dk_total_points').equals(frame.drop(columns='label_dk_total_points'))
    assert audit['changed_rows']==1


def test_known_zero_is_truth_not_missing():
    frame,data=fixture();frame['label_dk_total_points']=8.;data['rows'][0]['dk_points']=0.
    assert select(frame,data)[0].label_dk_total_points.tolist()==[0.]


@pytest.mark.parametrize('value',[None,float('nan'),float('inf')])
def test_missing_or_invalid_label_rejects_instead_of_zero(value):
    frame,data=fixture();data['rows'][0]['dk_points']=value
    with pytest.raises(ValueError,match='finite'):select(frame,data)


def test_missing_correction_cannot_fall_back_to_legacy():
    frame,data=fixture();data['rows']=[]
    with pytest.raises(ValueError,match='Missing verified'):select(frame,data)


@pytest.mark.parametrize('field',['player_master_id','team','opponent','game_id','source_system','week'])
def test_canonical_source_identity_required(field):
    frame,data=fixture();data['rows'][0][field]='wrong'
    with pytest.raises(ValueError,match='identity mismatch'):select(frame,data)


@pytest.mark.parametrize('field',['dst_scoring_contract','dst_source_sha256'])
def test_scoring_version_and_source_required(field):
    frame,data=fixture();data['rows'][0][field]=''
    with pytest.raises(ValueError,match='Unverified'):select(frame,data)


def test_future_placeholders_and_offense_are_unchanged():
    frame,data=fixture();future=frame.copy();future['week']=6;future['player_game_feature_matrix_id']=2
    offense=frame.copy();offense['position']='QB';offense['player_game_feature_matrix_id']=3
    combined=pd.concat([frame,future,offense],ignore_index=True)
    assert select(combined,data)[0].label_dk_total_points.tolist()==[5.,0.,0.]


def test_source_hash_and_contract_are_verified(tmp_path):
    _,data=fixture();path=tmp_path/'labels.json';path.write_text(json.dumps(data));checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    assert read_verified_correction(path,expected_sha256=checksum)==data
    with pytest.raises(ValueError,match='checksum'):read_verified_correction(path,expected_sha256='bad')
    data['contract_id']='legacy';path.write_text(json.dumps(data));checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='contract'):read_verified_correction(path,expected_sha256=checksum)


def test_no_opponent_qb_shadow_features_in_live_or_candidate_contract():
    from backend.app.product_services.canonical_projection_inputs import FEATURE_COLUMNS
    from backend.app.product_services.opponent_qb_context import FEATURE_COLUMNS as shadow
    assert not(set(FEATURE_COLUMNS)&set(shadow))


def test_missing_legacy_game_id_uses_exact_row_and_canonical_team_week_lineage():
    frame,data=fixture();frame['game_id']=None
    result,audit=select(frame,data)
    assert result.label_dk_total_points.tolist()==[5.]
    assert result.game_id.isna().all()
    assert audit['original_missing_game_ids']==1


def test_duplicate_source_row_identity_rejects():
    frame,data=fixture();data['rows'].append(dict(data['rows'][0]))
    with pytest.raises(ValueError,match='Duplicate'):select(frame,data)


def test_dataset_scoring_contract_mismatch_rejects():
    frame,data=fixture();data['contract_id']='legacy_approximation'
    with pytest.raises(ValueError,match='contract mismatch'):select(frame,data)
