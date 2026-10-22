import pytest
from backend.app.product_services.relative_role_transport import allocate


def role(id, pos, targets, carries=0, **extra):
    return dict(id=id, position=pos, targets=targets, carries=carries, **extra)


def test_conserves_full_budget_and_does_not_transfer_unsupported_expansion():
    current = [role('te', 'TE', 2, excluded=True), role('wr', 'WR', 8), role('zero', 'TE', 0)]
    source = [role('s_te', 'TE', 10), role('s_wr', 'WR', 10), role('s_zero', 'TE', 0)]
    out = allocate(current, source, {'s_te': 13, 's_wr': 7, 's_zero': 4, 'other': 1}, 'targets')
    assert sum(out['counts'].values()) + out['residual'] == pytest.approx(25)
    assert out['counts']['zero'] == 0
    assert out['residual'] > 0
    assert 0 < out['counts']['te'] < 13
    # Model opportunity is retained even when a user excludes the player.
    assert out == allocate([{k: v for k, v in r.items() if k != 'excluded'} for r in current], source,
                          {'s_te': 13, 's_wr': 7, 's_zero': 4, 'other': 1}, 'targets')


def test_retains_large_shock_when_supported_not_arbitrary_cap():
    rows = [role('te', 'TE', 2), role('wr', 'WR', 8)]
    out = allocate(rows, rows, {'te': 13, 'wr': 7}, 'targets')
    assert out['counts']['te'] == pytest.approx(13)
    assert out['counts']['wr'] == pytest.approx(7)


def test_unknown_duplicate_and_real_zero_are_distinct():
    rows = [role('te', 'TE', 2)]
    with pytest.raises(ValueError, match='Unknown'):
        allocate([role('te', 'TE', None)], rows, {'te': 1}, 'targets')
    with pytest.raises(ValueError, match='Duplicate'):
        allocate(rows + rows, rows, {'te': 1}, 'targets')
    out = allocate(rows, rows, {'te': 0}, 'targets')
    assert out['status'] == 'observed_zero_budget'
    assert out['counts']['te'] == out['residual'] == 0
