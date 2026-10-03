"""Replay a saved production/PARITY or sequential cap-shadow contract offline."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.product_services.classic_strategy_contract import execute_strategy_contract, portfolio_audit

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    contract=json.loads(args.contract.read_text())
    result=execute_strategy_contract(contract)
    audit=portfolio_audit(contract,result.lineups,trace=result.selection_trace)
    audit.update(status=result.status,message=result.message)
    args.output.write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result.status,'games':audit['canonical_primary_games'],'objective':audit['selector_objective_total']}))
