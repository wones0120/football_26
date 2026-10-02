"""Explicit CBC selection for diagnostic Classic optimizer runs."""

from __future__ import annotations

import shutil

import pulp


def resolve_cbc_backend(requested: str) -> str:
    """Resolve an explicit backend, or detect a native CBC executable."""
    if requested not in {"bundled", "native", "auto"}:
        raise ValueError("classic_solver_backend must be bundled, native, or auto")
    if requested == "auto":
        return "native" if shutil.which("cbc") else "bundled"
    if requested == "native" and not shutil.which("cbc"):
        raise ValueError("Native CBC was requested but no cbc executable is on PATH")
    return requested


def make_cbc_solver(backend: str = "bundled") -> pulp.LpSolver:
    """Never substitute the bundled binary for an explicitly selected native one."""
    if backend == "bundled":
        return pulp.PULP_CBC_CMD(msg=False)
    if backend == "native":
        path = shutil.which("cbc")
        if not path:
            raise ValueError("Native CBC was requested but no cbc executable is on PATH")
        return pulp.COIN_CMD(path=path, msg=False)
    raise ValueError(f"Unsupported resolved CBC backend: {backend}")
