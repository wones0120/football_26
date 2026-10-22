import pytest
from backend.app.product_services.model_source_budget_ledger import build_source_budget_ledger
A='00000000-0000-0000-0000-000000000001';B='00000000-0000-0000-0000-000000000002'
def row(i,pid,count):return dict(game_id='2023_04_MIA_BUF',team='BUF',source_id=i,source_player_id='00-'+str(i).zfill(7),player_master_id=pid,counts=dict(pass_attempts=count,rush_attempts=0,targets=0))
def test_conserve_source_scored_excluded_unresolved_without_donation():
 records=[row(1,A,10),row(2,B,5),row(3,None,2)];x=build_source_budget_ledger(records,scored_subjects=[dict(game_id='2023_04_MIA_BUF',team='BUF',player_master_id=A)])['team_game_rows'][0]['channels']['pass_attempts']
 assert[x[k]for k in('exact_source_total','known_scored_sum','known_excluded_canonical_sum','known_unresolved_sum')]==[17,10,5,2]
 assert x['missing_actor_mass_donated']is False
@pytest.mark.parametrize('mode',['missing_count','positive_missing'])
def test_unknown_mass_masks_total_never_invented_zero(mode):
 r=row(1,A,0);missing=[]
 if mode=='missing_count':r['counts']['pass_attempts']=None
 else:missing=[dict(native_game_id=r['game_id'],team='BUF',offense_snaps=1)]
 x=build_source_budget_ledger([r],positive_missing=missing)['team_game_rows'][0]['channels']['pass_attempts'];assert x['exact_source_total']is None and x['known_source_sum']==0
@pytest.mark.parametrize('mode',['duplicate','native','negative','side'])
def test_source_guards(mode):
 r=row(1,A,0);rs=[r]
 if mode=='duplicate':rs.append(dict(r))
 if mode=='native':rs.append(dict(r,source_id=2))
 if mode=='negative':r['counts']['targets']=-1
 if mode=='side':r['team']='NYJ'
 with pytest.raises(ValueError):build_source_budget_ledger(rs)
def test_no_scored_filter_is_not_complete_target_actor_selection():
 x=build_source_budget_ledger([row(1,A,3)])['team_game_rows'][0]['channels']['pass_attempts'];assert x['known_scored_sum']==0 and x['known_excluded_canonical_sum']==3


def test_unscoped_positive_mass_masks_compatible_channel_not_observed_zero():
 r=row(1,A,3);threat=dict(game_id=r['game_id'],possible_teams=['BUF','MIA'],counts=dict(pass_attempts=1,rush_attempts=0,targets=None))
 x=build_source_budget_ledger([r],unscoped_threats=[threat])['team_game_rows'][0]['channels']
 assert x['pass_attempts']['exact_source_total']is None and x['pass_attempts']['known_source_sum']==3
 assert x['targets']['exact_source_total']is None and x['rush_attempts']['exact_source_total']==0
