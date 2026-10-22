"""Select defense metrics while retaining batch-global identity evidence."""
from copy import deepcopy
from backend.app.product_services.evaluation_record import digest


def select_contact_scope(result,teams):
    selected={k:deepcopy(v)for k,v in result.items()if k not in ('game_rows','profiles','semantic_sha256','provenance')}
    selected['game_rows']=[deepcopy(g)for g in result['game_rows']if g['defense']in teams]
    selected['profiles']=[deepcopy(p)for p in result['profiles']if p['defense']in teams]
    # An incident's stored team is the opposing offense; its latest occurrence
    # may be another game. Keep all global proof/case keys instead of falsely
    # treating the selected defense as the unresolved rusher's own team.
    selected['identity_scope']='Batch-global native proofs and review requests retained; only defense metric rows/profiles are selected'
    selected['selected_semantic_sha256']=digest(selected)
    return selected
