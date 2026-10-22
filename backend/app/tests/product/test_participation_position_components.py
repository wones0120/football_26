from copy import deepcopy
from pathlib import Path
import hashlib,json
import pytest
from backend.app.product_services.participation_position_components import project_participation_positions,load_position_component,URL


def row():
    return dict(nflverse_game_id='2023_01_BUF_MIA',play_id=1,season=2023,week=1,season_type='REG',possession_team='BUF',offense_players=[f'00-{i:07d}'for i in range(1,12)],offense_positions=['QB','C','G','G','T','T','TE','WR','WR','RB','TE'],defense_players=[f'00-{i:07d}'for i in range(12,23)],defense_positions=['DE','DE','DT','LB','LB','CB','CB','CB','FS','SS','S'],n_offense=11,n_defense=11,defense_man_zone_type='MAN_COVERAGE',defense_coverage_type='COVER_1')


def test_exact_native_offense_defense_positions_labels_and_originals_retained():
    x=project_participation_positions([row()],season=2023);r=x['rows'][0]
    assert all(r['participant_scopes'][s]['exact_eleven_positions_proven']for s in ('offense','defense'))
    assert r['participant_scopes']['offense']['position_by_native_id']['00-0000007']=='TE'
    assert r['measurements']['defense_man_zone_type']=='MAN_COVERAGE'
    assert r['source_row_ordinal']==0 and r['original_possession_team']=='BUF'


def test_published_source_phase_and_all_rows_not_eligibility_inferred():
    r=row();r['season_type']=None;r['possession_team']=None
    x=project_participation_positions([r],season=2023)['rows'][0]
    assert x['native_phase']is None and x['possession_team']is None
    assert 'physical_snap'not in x


@pytest.mark.parametrize('season',[2022,2026])
def test_no_earlier_NGS_or_current_source_fallback(season):
    with pytest.raises(ValueError,match='historical'):project_participation_positions([row()],season=season)


def test_cross_side_conflict_masks_both_but_raw_lists_remain():
    r=row();r['defense_players'][0]=r['offense_players'][0];x=project_participation_positions([r],season=2023)['rows'][0]
    for s in ('offense','defense'):
        p=x['participant_scopes'][s];assert p['status']=='conflicting_cross_side_native_identity'and p['position_by_native_id']is None and not p['exact_eleven_positions_proven']and p['reported_native_positions']


@pytest.mark.parametrize('change',['missing_positions','mismatched_positions','count_conflict','invalid_count','duplicate_player','bad_native_key'])
def test_absent_or_conflicting_alignment_never_certifies(change):
    r=row()
    if change=='missing_positions':r.pop('offense_positions')
    elif change=='mismatched_positions':r['offense_positions']=r['offense_positions'][:10]
    elif change=='count_conflict':r['n_offense']=12
    elif change=='invalid_count':r['n_offense']=True
    elif change=='duplicate_player':r['offense_players'][1]=r['offense_players'][0]
    else:r['offense_players'][0]='not-a-GSIS'
    s=project_participation_positions([r],season=2023)['rows'][0]['participant_scopes']['offense']
    assert not s['exact_eleven_positions_proven']and s['position_by_native_id']is None


def test_unknown_position_does_not_prevent_native_membership_but_not_roleproof():
    r=row();r['offense_positions'][0]='UNKNOWN';s=project_participation_positions([r],season=2023)['rows'][0]['participant_scopes']['offense']
    assert s['exact_eleven_native_proven']and not s['exact_eleven_positions_proven']and s['position_by_native_id']['00-0000001']=='UNKNOWN'


def test_native_list_string_formats_reuse_same_reviewed_token_semantics():
    r=row();r['offense_players']=';'.join(r['offense_players']);r['offense_positions']=' '.join(r['offense_positions'])
    assert project_participation_positions([r],season=2023)['rows'][0]['participant_scopes']['offense']['exact_eleven_positions_proven']


def test_control_ten_players_is_aligned_not_exact11():
    r=row();r['offense_players']=r['offense_players'][:10];r['offense_positions']=r['offense_positions'][:10];r['n_offense']=10
    s=project_participation_positions([r],season=2023)['rows'][0]['participant_scopes']['offense'];assert s['status']=='aligned_native_position_list'and not s['exact_eleven_native_proven']


def test_bad_native_period_side_duplicate_bound_rejected():
    for k,v in [('week',2),('season',2024),('possession_team','DEN'),('play_id',-1)]:
        r=row();r[k]=v
        with pytest.raises(ValueError):project_participation_positions([r],season=2023)
    with pytest.raises(ValueError,match='Unique'):project_participation_positions([row(),row()],season=2023)
    with pytest.raises(ValueError,match='row bound'):project_participation_positions([row()],season=2023,max_rows=0)


def test_invalid_coverage_label_kept_unknown_not_text_coerced():
    r=row();r['defense_man_zone_type']=3;x=project_participation_positions([r],season=2023)['rows'][0]
    assert x['measurements']['defense_man_zone_type']is None and x['issues']


def save_component(tmp_path):
    x=project_participation_positions([row()],season=2023);p=tmp_path/'producer.py';p.write_text('# frozen')
    x['provenance']=dict(source_ref=dict(source_uri=URL.format(season=2023),captured_at='2026-10-20T00:00:00Z'),actual_read_at='2026-10-20T00:01:00Z',actual_publication_at='2026-10-20T00:02:00Z',producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()})
    def save(v):
        b=json.dumps(v,sort_keys=True).encode();sha=hashlib.sha256(b).hexdigest();f=tmp_path/(sha+'.json');f.write_bytes(b);return dict(path=str(f),sha256=sha,bytes=len(b))
    return x,p,save


def test_managed_reader_hash_publication_source_uri_and_producer_guards(tmp_path):
    x,p,save=save_component(tmp_path);ref=save(x)
    assert load_position_component(ref,cutoff='2026-10-20T00:03:00Z',directory=tmp_path)['row_count']==1
    with pytest.raises(ValueError,match='clock lineage'):load_position_component(ref,cutoff='2026-10-20T00:01:30Z',directory=tmp_path)
    p.write_text('# drift')
    with pytest.raises(ValueError,match='producer'):load_position_component(ref,cutoff='2026-10-20T00:03:00Z',directory=tmp_path)


@pytest.mark.parametrize('change',['semantic','source_uri','empty_producers','bytes'])
def test_managed_component_tamper_or_lineage_change_rejected(tmp_path,change):
    x,p,save=save_component(tmp_path)
    if change=='semantic':x['rows'][0]['play_id']='999'
    elif change=='source_uri':x['provenance']['source_ref']['source_uri']='wrong'
    elif change=='empty_producers':x['provenance']['producer_code_hashes']={}
    ref=save(x)
    if change=='bytes':Path(ref['path']).write_text('{}')
    with pytest.raises(ValueError):load_position_component(ref,cutoff='2026-10-20T00:03:00Z',directory=tmp_path)


@pytest.mark.parametrize('side',['offense','defense'])
@pytest.mark.parametrize('fault',['count','missing_position'])
def test_reported_cross_side_overlap_masks_both_even_if_one_scope_unqualified(side,fault):
    r=row();other='offense'if side=='defense'else'defense'
    r[side+'_players'][0]=r[other+'_players'][0]
    if fault=='count':r['n_'+side]=12
    else:r[side+'_positions']=None
    x=project_participation_positions([r],season=2023)['rows'][0]
    for name in ('offense','defense'):
        p=x['participant_scopes'][name]
        assert p['status']=='conflicting_cross_side_native_identity'and not p['exact_eleven_native_proven']and not p['exact_eleven_positions_proven']


def test_duplicate_or_partially_malformed_raw_list_still_contributes_known_overlap_candidates():
    for malformed in ('duplicate','missing_token'):
        r=row();r['defense_players'][0]=r['offense_players'][0]
        r['defense_players'][1]=r['defense_players'][0]if malformed=='duplicate'else None
        x=project_participation_positions([r],season=2023)['rows'][0]
        assert x['participant_scopes']['offense']['status']=='conflicting_cross_side_native_identity'
        assert not x['participant_scopes']['offense']['exact_eleven_positions_proven']
