"""Injury evidence is shared by Sunday Classic subsets, not duplicated or re-dated."""
from Database.dst import canonical_team_sql

SUNDAY_SUBSETS = ('SUNDAY_EARLY', 'SUNDAY_LATE')


def injury_source_slates(slate):
    selected = slate.strip().upper()
    return (selected, 'SUNDAY_MAIN') if selected in SUNDAY_SUBSETS else (selected,)


def injury_slate_sql(column):
    """Internal SQL expression; column names are supplied only by application code."""
    return (f"(UPPER({column}) = UPPER(:slate) OR "
            f"(UPPER(:slate) IN ('SUNDAY_EARLY', 'SUNDAY_LATE') AND UPPER({column}) = 'SUNDAY_MAIN'))")


def injury_subset_membership_sql(player_column, team_column):
    """Keep inherited evidence within the selected salary players/teams.

    Unresolved rows remain visible when their team belongs to the subset.
    """
    return f"""(UPPER(:slate) NOT IN ('SUNDAY_EARLY', 'SUNDAY_LATE') OR EXISTS (
        SELECT 1 FROM public.curated_salary injury_salary
        WHERE injury_salary.season=:season AND injury_salary.week=:week
          AND UPPER(injury_salary.slate)=UPPER(:slate) AND injury_salary.source_system='draftkings'
          AND ({player_column} IS NULL OR injury_salary.player_master_id={player_column})
          AND {canonical_team_sql('injury_salary.team')}={canonical_team_sql(team_column)}))"""
