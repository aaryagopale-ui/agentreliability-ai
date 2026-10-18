"""Create a project API key.   Run from backend/:  python -m app.create_key [project-name]

The key is shown ONCE. Only its hash is stored, so it cannot be shown again.
"""
import sys

from . import database, test_store, trace_store


def create_key(name: str = "local-dev") -> str:
    database.init_db()
    test_store.init_tables()
    trace_store.init_tables()
    _, key = trace_store.create_project(name)
    return key


if __name__ == "__main__":
    project = sys.argv[1] if len(sys.argv) > 1 else "local-dev"
    key = create_key(project)
    print(f"Project '{project}' created. Your API key (shown once, copy it now):\n")
    print(f"  {key}\n")
    print("Use it in the terminal where you run your agent:")
    print("  export AGENTRELIABILITY_API_KEY='<paste the key>'")
    print("Never commit this key to GitHub.")

