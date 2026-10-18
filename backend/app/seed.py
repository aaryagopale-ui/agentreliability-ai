"""Load sample logs into the database. Run from backend/: python -m app.seed"""
import json
from pathlib import Path

from . import database
from .detector import analyze
from .schemas import AgentLog

SAMPLES = Path(__file__).resolve().parents[2] / "sample_logs"


def seed() -> int:
    database.init_db()
    n = 0
    for f in sorted(SAMPLES.glob("*.json")):
        log = AgentLog.model_validate(json.loads(f.read_text()))
        database.save_execution(log.model_dump(), analyze(log))
        n += 1
    return n


if __name__ == "__main__":
    print(f"Seeded {seed()} sample executions.")

