import json
from pathlib import Path
from urllib.request import Request,urlopen
p=Path(__file__).resolve().parent
packet=json.loads((p/'v3/packet.json').read_text())
req=Request('http://localhost:8000/api/optimizer/analyst-packets',data=json.dumps({'packet':packet}).encode(),headers={'Content-Type':'application/json'},method='POST')
with urlopen(req,timeout=20) as r:receipt=json.load(r)
(p/'v3/import_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
