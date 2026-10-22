"""Research-only conditional count means; no fitting, sampling or live consumer."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

CHANNELS = ('pass_attempts', 'rush_attempts', 'targets')
VERSION = 'conditional_player_opportunity_accounting_v1'


def number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Finite nonnegative numeric count/share required')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid number') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Finite nonnegative count/share required')
    return result


def clock(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware input clocks required')
    return result


def allocate(budgets, role_snapshot, *, game_id, team, cutoff):
    """Allocate supplied conditional means, retaining every unassigned unit.

    Shares describe the full team, not the salary pool. Unknown availability
    withholds attribution; it never transfers work to other named players.
    Input chronology is checked, but a timestamp does not prove availability
    before a historical decision. This slice accepts synthetic fixtures only.
    """
    if set(budgets) != set(CHANNELS):
        raise ValueError('Exact team count channels required')
    if (not game_id or not team or role_snapshot['game_id'] != game_id
            or role_snapshot['team'] != team):
        raise ValueError('Role snapshot must match game and team')
    if role_snapshot['evidence_kind'] != 'synthetic_fixture' or not role_snapshot['snapshot_id']:
        raise ValueError('Only explicitly identified synthetic fixtures accepted')
    if clock(role_snapshot['as_of']) > clock(cutoff):
        raise ValueError('Role snapshot after decision cutoff')
    totals = {c: number(budgets[c]) for c in CHANNELS}
    p, t = totals['pass_attempts'], totals['targets']
    if p is not None and t is not None and t > p:
        raise ValueError('Targets cannot exceed official pass attempts')
    rows = []; seen = set(); known_shares = dict.fromkeys(CHANNELS, Decimal(0))
    for actor in role_snapshot['actors']:
        pid = str(UUID(actor['player_master_id']))
        if pid in seen:
            raise ValueError('Duplicate canonical player identity')
        seen.add(pid)
        availability = actor['availability']
        if availability not in {'available', 'unavailable', 'unknown'}:
            raise ValueError('Explicit availability required')
        if set(actor['shares']) != set(CHANNELS):
            raise ValueError('Exact actor share channels required')
        values = {}
        for channel in CHANNELS:
            share = number(actor['shares'][channel])
            if share is not None:
                if share > 1 or (availability == 'unavailable' and share > 0):
                    raise ValueError('Invalid share or work assigned to unavailable player')
                known_shares[channel] += share
            budget = totals[channel]
            values[channel] = (0.0 if budget == 0 or share == 0 else
                float(budget * share) if budget is not None and share is not None
                and availability == 'available' else None)
        rows.append(dict(player_master_id=pid, availability=availability,
                         conditional_mean_counts=values))
    accounting = {}
    for channel in CHANNELS:
        if known_shares[channel] > 1:
            raise ValueError('Full-team shares exceed one; no renormalization')
        budget = totals[channel]
        # Compute from the same decimal inputs rather than rounded output means.
        assigned = sum((number(a['shares'][channel]) * budget
            for a in role_snapshot['actors'] if budget is not None
            and a['availability'] == 'available' and a['shares'][channel] is not None), Decimal(0))
        accounting[channel] = dict(team_budget=None if budget is None else float(budget),
            assigned_known_mean=float(assigned),
            residual_mean=None if budget is None else float(budget - assigned),
            status='UNKNOWN_TEAM_BUDGET' if budget is None else 'CONSERVED_CONDITIONAL_MEAN',
            unknown_actor_count=sum(r['conditional_mean_counts'][channel] is None for r in rows))
    return dict(version=VERSION, scope=dict(game_id=game_id, team=team, cutoff=cutoff),
        snapshot_id=role_snapshot['snapshot_id'], evidence_kind='synthetic_fixture',
        players=rows, accounting=accounting,
        no_target_pass_mean=None if p is None or t is None else float(p-t),
        joint_pass_target_support='UNKNOWN' if p is None or t is None else 'COUNT_BUDGET_COMPATIBLE_ONLY',
        physical_play_count=None, scoring=None, forecast_validated=False, activation=False)
