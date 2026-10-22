from pathlib import Path
import hashlib,json
import pytest
from backend.app.product_services.receiver_pair_competition_source import load_reviewed_pair_native,SOURCE_VERSION


def setup(tmp_path):
    producer=tmp_path/'producer.py';producer.write_text('# frozen producer\n');sha=hashlib.sha256(producer.read_bytes()).hexdigest()
    prov=dict(actual_derived_at='2026-10-20T00:00:00Z',producer_code_hashes={str(producer):sha})
    def save(x):
        raw=json.dumps(x,sort_keys=True).encode();s=hashlib.sha256(raw).hexdigest();p=tmp_path/(s+'.json');p.write_bytes(raw);return dict(path=str(p),sha256=s,bytes=len(raw))
    native=dict(version=SOURCE_VERSION,pregame_serving_eligible=False,provenance=prov,native_identity_universe=['00-0000001'])
    nr=save(native)
    attached=dict(version=SOURCE_VERSION,pregame_serving_eligible=False,provenance={**prov,'source_native_ref':nr,'actual_alias_cutoff_at':'2026-10-20T00:01:00Z'},native_identity_receipts={'00-0000001':dict(status='unique_native_alias',original_alias_evidence=[dict(created_at='2020-01-01T00:00:00Z')])})
    return nr,save(attached),save,native,attached,producer


def test_exact_verified_native_and_full_global_identity_receipts(tmp_path):
    n,a,*_=setup(tmp_path);r=load_reviewed_pair_native(n,a,cutoff='2026-10-20T00:02:00Z',directory=tmp_path)
    assert r['identities']['00-0000001']['status']=='unique_native_alias'
    assert r['provenance']['availability'].startswith('Historical postseason')


def test_parent_bytes_tamper_not_accepted(tmp_path):
    n,a,*_=setup(tmp_path);Path(n['path']).write_text('{}')
    with pytest.raises(ValueError,match='SHA/bytes'):load_reviewed_pair_native(n,a,cutoff='2026-10-20T00:02:00Z',directory=tmp_path)


def test_current_producer_drift_not_accepted(tmp_path):
    n,a,save,native,attached,producer=setup(tmp_path);producer.write_text('# changed')
    with pytest.raises(ValueError,match='producer changed'):load_reviewed_pair_native(n,a,cutoff='2026-10-20T00:02:00Z',directory=tmp_path)


@pytest.mark.parametrize('change',['future_publication','future_alias_cutoff','future_alias','missing_identity','wrong_native','serving'])
def test_source_clocks_scope_and_nonserving_guards(tmp_path,change):
    n,a,save,native,attached,producer=setup(tmp_path)
    if change=='future_publication':attached['provenance']['actual_derived_at']='2027-01-01T00:00:00Z'
    elif change=='future_alias_cutoff':attached['provenance']['actual_alias_cutoff_at']='2027-01-01T00:00:00Z'
    elif change=='future_alias':attached['native_identity_receipts']['00-0000001']['original_alias_evidence'][0]['created_at']='2027-01-01T00:00:00Z'
    elif change=='missing_identity':attached['native_identity_receipts']={}
    elif change=='wrong_native':attached['provenance']['source_native_ref']={}
    else:attached['pregame_serving_eligible']=True
    a=save(attached)
    with pytest.raises(ValueError):load_reviewed_pair_native(n,a,cutoff='2026-10-20T00:02:00Z',directory=tmp_path)
