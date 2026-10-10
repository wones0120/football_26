"""Development-service import fingerprint, captured once per process."""
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path

from . import (single_lineup, canonical_projection_inputs, kicker_roles, player_roles, classic_small_field,
               classic_portfolio_policy, classic_prospective, pregame_context, optimizer,
               classic_large_gpp_readiness, showdown_portfolio_selection,
               showdown_candidate_comparison, showdown_game_scenarios, showdown_scenario_value, slate_preparation, showdown_readiness)

LOADED = {"pid": os.getpid(), "loaded_at": datetime.now(UTC).isoformat(),
          "modules": {Path(m.__file__).name: sha256(Path(m.__file__).read_bytes()).hexdigest()
                      for m in (single_lineup, canonical_projection_inputs, kicker_roles, player_roles, classic_small_field,
                                classic_portfolio_policy, classic_prospective, pregame_context, optimizer,
                                classic_large_gpp_readiness, showdown_portfolio_selection,
                                showdown_candidate_comparison, showdown_game_scenarios, showdown_scenario_value,
                                slate_preparation, showdown_readiness)}}
