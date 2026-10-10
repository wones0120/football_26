"""Read-only historical observations for the research UI; never solver inputs."""
import json
from pathlib import Path


NOTES_PATH = Path(__file__).resolve().parents[3] / "docs/product/showdown_research_notes.json"


def get_showdown_research_notes() -> dict:
    return json.loads(NOTES_PATH.read_text(encoding="utf-8"))
