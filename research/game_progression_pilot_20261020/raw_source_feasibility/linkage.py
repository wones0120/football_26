"""Native-key comparison only; table clocks do not imply event-end clocks."""
from collections import Counter
from research.game_progression_pilot_20261020.observation_contract.contract import integer

def table_records(table):
    if table.get('__r_container__')!='DataFrame':raise ValueError('Explicit decoded source table required')
    columns=table['columns']
    if len(columns)!=len(set(columns))or any(len(r)!=len(columns)for r in table['data']):raise ValueError('Unique aligned source columns required')
    return [dict(zip(columns,r))for r in table['data']]

def quarter_seconds(value):
    if not isinstance(value,str):return None
    parts=value.split(':')
    if len(parts)!=2 or not all(p.isdigit()for p in parts):return None
    minutes,seconds=map(int,parts)
    return 60*minutes+seconds if 0<=seconds<60 and 0<=60*minutes+seconds<=900 else None

def compare(raw,processed):
    rc=Counter(integer(r.get('playId'))for r in raw);pc=Counter(integer(r.get('play_id'))for r in processed)
    rby={integer(r.get('playId')):r for r in raw if integer(r.get('playId'))is not None and rc[integer(r.get('playId'))]==1}
    pby={integer(r.get('play_id')):r for r in processed if integer(r.get('play_id'))is not None and pc[integer(r.get('play_id'))]==1}
    matched=[];differences=[]
    for key in sorted(rby.keys()&pby.keys()):
        a,b=rby[key],pby[key];matched.append(key)
        checks={'order':a.get('orderSequence')==b.get('order_sequence'),
            'quarter':a.get('quarter')==b.get('qtr'),
            'start_clock':quarter_seconds(a.get('clockTime'))is not None and quarter_seconds(a.get('clockTime'))==b.get('quarter_seconds_remaining'),
            'native_type':a.get('playType')==b.get('play_type_nfl'),
            'deleted':a.get('playDeleted')in(True,False)and b.get('play_deleted')in(0,1)and int(a['playDeleted'])==b['play_deleted']}
        if not all(checks.values()):differences.append(dict(play_id=key,fields=[k for k,v in checks.items()if not v]))
    return dict(raw_rows=len(raw),processed_rows=len(processed),matched_ids=matched,
        raw_only_ids=sorted(rby.keys()-pby.keys()),processed_only_ids=sorted(pby.keys()-rby.keys()),
        raw_ambiguous_or_missing_id_rows=sum(n for k,n in rc.items()if k is None or n!=1),
        processed_ambiguous_or_missing_id_rows=sum(n for k,n in pc.items()if k is None or n!=1),differences=differences)
