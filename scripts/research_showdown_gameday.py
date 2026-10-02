"""Reuse expanded overnight discovery with the unchanged ownership reliability gate."""
from unittest.mock import patch

from scripts import research_showdown_prelock as research


class ReliabilityGatedFrozenService(research.FrozenService):
    def _load_player_pool(self, *args, **kwargs):
        frame = super()._load_player_pool(*args, **kwargs)
        for field in ('ownership', 'captain_ownership', 'flex_ownership'):
            frame['diagnostic_'+field] = frame[field]
            frame[field] = None
        return frame


def main():
    # Complete slot coverage does not repair weak Showdown calibration. Mask
    # before MILP capture as well as before selection, without changing weights.
    with patch.object(research, 'FrozenService', ReliabilityGatedFrozenService):
        research.main()


if __name__ == '__main__':
    main()
