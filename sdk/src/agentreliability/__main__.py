"""Entrypoint for python -m agentreliability."""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())

