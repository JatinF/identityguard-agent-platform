"""SQLite checkpoint for LangGraph.

Closing the connection and opening it again is the process-restart path used
by the recovery test. PostgreSQL remains the system of record for approvals
and account state when DATABASE_URL is configured. The graph checkpoint in
this demo is the SQLite saver, which survives a process exit on a local disk.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def open_checkpointer(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(connection)
    if hasattr(saver, "setup"):
        saver.setup()
    return saver, connection
