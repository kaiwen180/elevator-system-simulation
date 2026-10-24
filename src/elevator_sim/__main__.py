"""Lets `python -m elevator_sim` run the command line."""

import sys

from .app.cli import main

sys.exit(main())
