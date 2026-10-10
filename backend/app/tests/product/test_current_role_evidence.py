from scripts.capture_current_slate_roles import Tables, resolve_identity


def test_role_identity_requires_team_and_position_with_canonical_alias():
    aliases = {("NO", "RB", "runner"): {"canonical-rb"}}
    assert resolve_identity(aliases, "NO", "RB", "Runner Jr.") == "canonical-rb"
    assert resolve_identity(aliases, "ATL", "RB", "Runner Jr.") is None
    assert resolve_identity(aliases, "NO", "WR", "Runner Jr.") is None


def test_ambiguous_aliases_and_position_mismatches_remain_unresolved():
    aliases = {("NO", "WR", "shared name"): {"one", "two"}, ("NO", "LS", "snapper"): {"ls"}}
    assert resolve_identity(aliases, "NO", "WR", "Shared Name") is None
    assert resolve_identity(aliases, "NO", "TE", "Snapper") is None


def test_roster_sections_preserve_reserve_and_practice_squad_evidence():
    parser = Tables()
    parser.feed('<h3>Reserve/Injured</h3><table><tr><th>Player</th><th>Pos</th></tr>'
                '<tr><td>Removed Starter</td><td>RB</td></tr></table>'
                '<h3>Practice Squad</h3><table><tr><th>Player</th><th>Pos</th></tr>'
                '<tr><td>Backup Kicker</td><td>K</td></tr></table>')
    assert [t["section"] for t in parser.tables] == ["Reserve/Injured", "Practice Squad"]
    assert parser.tables[1]["rows"][1] == ["Backup Kicker", "K"]
