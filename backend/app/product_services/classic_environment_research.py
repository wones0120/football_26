"""Read-only research note. Never imported by production selection services."""
import json
from pathlib import Path

NOTES_PATH = Path(__file__).resolve().parents[3] / 'docs/product/classic_game_environment_research.json'


def get_research_notes():
    return json.loads(NOTES_PATH.read_text(encoding='utf-8'))
