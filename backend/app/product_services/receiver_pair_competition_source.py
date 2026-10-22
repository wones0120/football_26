"""Read-only verified managed parents for receiver-pair observed decomposition."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json
from .factual_designation import clock
from .coverage_receiver_performance import VERSION as SOURCE_VERSION


def load_reviewed_pair_native(native_ref,attached_ref,*,cutoff,directory=None,max_bytes=32*1024*1024):
    boundary=clock(cutoff)
    if boundary is None or boundary>datetime.now(UTC):raise ValueError('Actual nonfuture read cutoff required')
    folder=Path(directory or 'artifacts/coverage_receiver_performance').resolve()
    def read(ref):
        p=Path(ref['path']);raw=p.read_bytes()
        if p.resolve().parent!=folder or p.stem!=ref['sha256']or len(raw)!=ref['bytes']or len(raw)>max_bytes or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Exact managed reviewed parent SHA/bytes required')
        value=json.loads(raw)
        if value.get('version')!=SOURCE_VERSION or value.get('pregame_serving_eligible')is not False:raise ValueError('Exact nonserving source version required')
        prov=value['provenance'];publication=clock(prov.get('actual_publication_at',prov.get('actual_derived_at')))
        if publication is None or publication>boundary:raise ValueError('Parent publication must precede actual cutoff')
        if not prov.get('producer_code_hashes'):raise ValueError('Frozen producer bindings required')
        for filename,sha in prov['producer_code_hashes'].items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=sha:raise ValueError('Reviewed parent producer changed')
        return value
    native=read(native_ref);attached=read(attached_ref)
    if attached['provenance']['source_native_ref']!=native_ref:raise ValueError('Attached identity parent differs from native source')
    identities=attached['native_identity_receipts']
    if not set(native['native_identity_universe'])<=set(identities):raise ValueError('Frozen global identity scope incomplete')
    alias_cutoff=clock(attached['provenance']['actual_alias_cutoff_at'])
    if alias_cutoff is None or alias_cutoff>boundary:raise ValueError('Frozen alias cutoff required')
    for n,proof in identities.items():
        for a in proof['original_alias_evidence']:
            if clock(a.get('created_at'))is None or clock(a['created_at'])>alias_cutoff:raise ValueError('Frozen alias clock differs')
    return dict(native=native,identities=identities,provenance=dict(native_ref=native_ref,attached_ref=attached_ref,source_native_provenance=native['provenance'],attached_provenance=attached['provenance'],actual_read_at=boundary.isoformat(),identity_scope='Inherited complete global receipts and all-period withholding; no alias query or reattachment',availability='Historical postseason/revised2026capture; original historical pregame availability unknown'))
