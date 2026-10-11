from sqlalchemy import create_engine, text
import pytest
from backend.app.injury_scope import injury_slate_sql, injury_subset_membership_sql, injury_source_slates


@pytest.mark.parametrize('slate,expected', [('SUNDAY_EARLY',['early','unresolved']), ('sunday_late',['late']),
                                           ('SUNDAY_NIGHT',[])])
def test_main_injuries_are_selected_by_canonical_identity_team_and_cutoff(slate, expected):
    engine = create_engine('sqlite://')
    with engine.begin() as c:
        c.execute(text("ATTACH DATABASE ':memory:' AS public"))
        c.execute(text('CREATE TABLE public.curated_salary (season int, week int, slate text, source_system text, player_master_id text, team text)'))
        c.execute(text("INSERT INTO public.curated_salary VALUES (2026,5,'SUNDAY_EARLY','draftkings','early-id','BUF'),(2026,5,'SUNDAY_LATE','draftkings','late-id','SEA')"))
        c.execute(text('CREATE TABLE injuries (season int, week int, slate text, player_master_id text, team text, label text, observed_at text)'))
        for pid, team, label, week, at in [('early-id','BUF','early',5,'2026-10-09'),('late-id','SEA','late',5,'2026-10-09'),
            ('different-id','BUF','wrong-player',5,'2026-10-09'),('early-id','SEA','wrong-team',5,'2026-10-09'),
            ('early-id','BUF','future',5,'2026-10-11'),('early-id','BUF','wrong-week',4,'2026-10-09'),
            (None,'BUF','unresolved',5,'2026-10-09')]:
            c.execute(text("INSERT INTO injuries VALUES (2026,:week,'SUNDAY_MAIN',:pid,:team,:label,:at)"),dict(week=week,pid=pid,team=team,label=label,at=at))
        rows=c.execute(text(f'''SELECT i.label,i.slate,i.observed_at FROM injuries i
            WHERE i.season=:season AND i.week=:week AND {injury_slate_sql('i.slate')}
              AND {injury_subset_membership_sql('i.player_master_id','i.team')} AND i.observed_at<=:cutoff
            ORDER BY i.label'''),dict(season=2026,week=5,slate=slate,cutoff='2026-10-10')).all()
        assert [r.label for r in rows] == expected
        assert all(r.slate == 'SUNDAY_MAIN' and r.observed_at == '2026-10-09' for r in rows)


def test_injury_inheritance_is_one_way_and_not_shared_with_captain():
    assert injury_source_slates('sunday_early') == ('SUNDAY_EARLY','SUNDAY_MAIN')
    assert injury_source_slates('SUNDAY_LATE') == ('SUNDAY_LATE','SUNDAY_MAIN')
    for slate in ('SUNDAY_MAIN','SUNDAY_NIGHT','MONDAY_NIGHT','THURSDAY_NIGHT'):
        assert injury_source_slates(slate) == (slate,)


def test_injury_file_discovery_uses_main_filename_for_subsets(tmp_path, monkeypatch):
    from pathlib import Path
    from backend.app.product_services.slate import SlateDataService
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    file=tmp_path/'FanDuel_injuries_2026_5_SUNDAY_MAIN.csv'
    file.write_text('fixture')
    service=object.__new__(SlateDataService)
    for slate in ('SUNDAY_EARLY','SUNDAY_LATE','SUNDAY_MAIN'):
        assert service._find_injury_file(2026,5,slate) == file
    assert service._find_injury_file(2026,5,'SUNDAY_NIGHT') is None


@pytest.mark.parametrize('slate', ['SUNDAY_EARLY', 'SUNDAY_LATE'])
def test_subsets_reuse_original_main_role_facts_without_refreshing_clocks(monkeypatch, slate):
    from datetime import datetime, UTC, timedelta
    from backend.app.product_services import showdown_player_context as module
    now = datetime(2026, 10, 10, 23, tzinfo=UTC)
    salary = dict(player_id='player', team='LAC', position='TE')
    role = dict(player_id='player', team='LAC', position='TE', kind='role',
        role='expected_backup', source='nflreadpy_depth_charts', source_ids=['original'],
        observed_at=(now-timedelta(hours=18)).isoformat(), received_at=(now-timedelta(hours=12)).isoformat())
    excluded = [dict(role, player_id='other'), dict(role, team='SEA'), dict(role, position='QB'),
        dict(role, observed_at=(now+timedelta(hours=1)).isoformat()),
        dict(role, received_at=(now+timedelta(hours=1)).isoformat())]
    def load(connection, **kwargs):
        assert kwargs == dict(season=2026, week=5, slate='SUNDAY_MAIN', cutoff=now, include_source_history=True)
        return [dict(evidence_json=dict(canonical_context_contract=module.CONTEXT_CONTRACT,
                     source_facts=[role, role, *excluded]))]
    monkeypatch.setattr('backend.app.product_services.pregame_context.load_current_pregame_context', load)
    facts = module.shared_sunday_source_facts(None, season=2026, week=5, slate=slate, cutoff=now, salaries=[salary])
    assert facts == [role]
    roster = dict(role, kind='roster_status', role=None, status='ACT', observed_at=now.isoformat(), received_at=now.isoformat())
    context = module.compose_player_contexts([salary], facts+[roster], cutoff=now, max_age_hours=24)[0]
    assert context['evidence_json']['canonical_role'] == 'expected_backup'
    assert context['evidence_json']['role_observed_at'] == role['observed_at']
    stale = module.compose_player_contexts([salary], facts+[roster], cutoff=now+timedelta(hours=7), max_age_hours=24)[0]
    assert stale['evidence_json']['canonical_role'] is None
    for other in ['SUNDAY_MAIN', 'SUNDAY_NIGHT']:
        assert module.shared_sunday_source_facts(None, season=2026, week=5, slate=other, cutoff=now, salaries=[salary]) == []
