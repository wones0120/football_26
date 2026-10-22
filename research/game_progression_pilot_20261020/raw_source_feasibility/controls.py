"""Raw-only typed control observations; no transfer, play-end or restart claims."""
from collections import Counter
from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import quarter_seconds
from research.game_progression_pilot_20261020.observation_contract.contract import integer

def additional_controls(raw,processed_ids):
    counts=Counter(integer(r.get('playId'))for r in raw)
    orders=[r.get('orderSequence')for r in raw]
    if any(type(v)not in(int,float)for v in orders)or len(set(orders))!=len(orders):raise ValueError('Unique native order required')
    ordered=sorted(raw,key=lambda r:r['orderSequence']);result=[]
    for index,row in enumerate(ordered):
        pid=integer(row.get('playId'))
        if pid is None or pid in processed_ids:continue
        before=next((r for r in reversed(ordered[:index])if integer(r.get('playId'))in processed_ids),None)
        after=next((r for r in ordered[index+1:]if integer(r.get('playId'))in processed_ids),None)
        clock=quarter_seconds(row.get('clockTime'));neighbors=(before,after)
        same=all(r and r.get('quarter')==row.get('quarter')and quarter_seconds(r.get('clockTime'))is not None for r in neighbors)
        bracket=(same and clock is not None and quarter_seconds(before['clockTime'])>=clock>=quarter_seconds(after['clockTime']))
        typed=(counts[pid]==1 and row.get('playType')=='TIMEOUT'and row.get('playDeleted')is False
            and row.get('playReviewStatus')in(None,'')and clock is not None and row.get('quarter')in(1,2,3,4))
        known=bool(typed and bracket)
        result.append(dict(play_id=pid,order_sequence=row.get('orderSequence'),quarter=row.get('quarter'),
            source_clock=row.get('clockTime'),reported_description=row.get('playDescription'),
            preceding_matched_play_id=before['playId']if before else None,following_matched_play_id=after['playId']if after else None,
            same_quarter_clock_bracket=bool(bracket),status='SOURCE_TYPED_CLOCK_STOP_OBSERVATION'if known else'UNQUALIFIED_RAW_ONLY_RECORD',
            reason='SOURCE_REPORTED_TWO_MINUTE_WARNING'if known and row.get('playDescription')=='Two-Minute Warning'else'UNKNOWN_STOP_CAUSE',
            timeout_team=None,timeout_budget_debit_proven=False,physical_play_end_clock=None,restart_policy=None,
            generated_state_transition_supported=False))
    return result
