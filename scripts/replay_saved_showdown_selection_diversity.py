"""Evaluate an existing freeze without reclassifying with current production code.

The initial guarded runner intentionally fails when the live classifier changes.
This offline path verifies the frozen annotations and original policy-code bytes
instead. It executes the same evaluation function; no ranking/selection changes.
"""
from types import FunctionType

from scripts import audit_showdown_selection_diversity as audit


def verify_saved_replay():
    frozen = audit.read(audit.OUT / "prelock_policy_freeze.json")
    event = audit.read(audit.OUT / "postgame_read_manifest.json")
    if audit.file_hash(audit.OUT / "prelock_policy_freeze.json") != event["freeze_sha256"]:
        raise ValueError("Frozen candidate decisions changed after first outcome read")
    if frozen["selection_code_sha256"] != audit.file_hash(audit.__file__):
        raise ValueError("Original research policy/evaluation code changed")
    if frozen["policy_definitions_hash"] != audit.digest(audit.POLICIES):
        raise ValueError("Policy definitions changed")
    for s in frozen["slates"]:
        for prefix in ("source", "packet", "pair_artifact"):
            path = s.get(prefix + "_path", s.get(prefix))
            if audit.file_hash(audit.ROOT / path) != s[prefix + "_sha256"]:
                raise ValueError(f"Frozen {prefix} artifact changed")
    return frozen


def main():
    verify_saved_replay()
    # Actual resolution is evaluation only. Pin its original implementation too;
    # candidate metrics and classification are already in hashed frozen artifacts.
    before = audit.read(audit.OUT / "production_preservation_before.json")
    path = "backend/app/product_services/optimizer_effectiveness.py"
    if audit.file_hash(audit.ROOT / path) != before[path]:
        raise ValueError("Outcome scoring implementation changed; investigate before rerunning")
    # A separate globals namespace replaces only evidence verification for this
    # evaluation call. Neither the original module nor any selector is mutated.
    evaluate = FunctionType(audit.evaluate.__code__, {**audit.evaluate.__globals__, "verify_freeze":verify_saved_replay})
    evaluate()


if __name__ == "__main__":
    main()
