"""Development-service import fingerprint, captured once per process."""
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path

from . import (canonical_projection_inputs, classic_small_field,
               classic_portfolio_policy, classic_prospective, pregame_context, optimizer)

LOADED = {"pid": os.getpid(), "loaded_at": datetime.now(UTC).isoformat(),
          "modules": {Path(m.__file__).name: sha256(Path(m.__file__).read_bytes()).hexdigest()
                      for m in (canonical_projection_inputs, classic_small_field,
                                classic_portfolio_policy, classic_prospective, pregame_context, optimizer)}}
