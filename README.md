# Time Tracker

Time Tracker is a local Linux desktop app for entering and viewing time blocks in a weekly dashboard. The current Phase 1 prototype displays a Qt window with week controls and a scrollable, in-memory grid. Editing and persistence are planned for later phases.

This project is built by agents with a human-in-the-loop approach.

## Development setup

Use Python 3.10–3.15 on Linux. The initial scaffold was prepared with Python 3.14.7. From the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable '.[dev]'
```

`pyproject.toml` pins the direct runtime and test dependencies. The application uses PySide6 for its Qt Widgets UI and Python's built-in `sqlite3` for storage; no separate database package is needed.

## Launch and checks

With the virtual environment active:

```sh
python -m time_tracker
# Equivalent installed command:
time-tracker
python -m pytest
```

Both launch commands open the prototype window. Sample blocks, including a one-minute block and a multi-hour block, are held only in memory and cannot yet be edited or saved. The date headers stay fixed above the scrolling grid. The Phase 1 geometry and scrolling checks run with `python -m pytest`; physical wheel and touchpad behavior will also be checked during final desktop acceptance.

For a headless test run, use `QT_QPA_PLATFORM=offscreen python -m pytest`.

See [time-tracker-design.md](agent_docs/time-tracker-design.md) for product behavior and [time-tracker-implementation.md](agent_docs/time-tracker-implementation.md) for the phased plan.
