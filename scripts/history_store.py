"""SQLite history store for facade designer runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True)


class RunHistoryStore:
    """Stores each pipeline run and its text/file artifacts."""

    def __init__(self, db_path: Path):
        self.db_path = db_path.expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_prompt TEXT NOT NULL,
                    building_image_path TEXT NOT NULL,
                    inspiration_image_path TEXT,
                    output_dir TEXT NOT NULL,
                    text_model TEXT NOT NULL,
                    image_model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    final_text TEXT,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT,
                    path TEXT,
                    mime_type TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                )
                """
            )

    def start_run(
        self,
        *,
        run_id: str,
        session_id: str,
        user_prompt: str,
        building_image_path: Path,
        inspiration_image_path: Path | None,
        output_dir: Path,
        text_model: str,
        image_model: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, session_id, status, user_prompt, building_image_path,
                    inspiration_image_path, output_dir, text_model, image_model, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    "running",
                    user_prompt,
                    str(building_image_path),
                    str(inspiration_image_path) if inspiration_image_path else "",
                    str(output_dir),
                    text_model,
                    image_model,
                    _utc_now(),
                ),
            )

    def add_artifact(
        self,
        *,
        run_id: str,
        agent_name: str,
        artifact_type: str,
        name: str,
        content: str = "",
        path: str = "",
        mime_type: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    run_id, agent_name, artifact_type, name, content, path,
                    mime_type, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    agent_name,
                    artifact_type,
                    name,
                    content,
                    path,
                    mime_type,
                    _json(metadata or {}),
                    _utc_now(),
                ),
            )

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        final_text: str = "",
        error: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, finished_at = ?, final_text = ?, error = ?
                WHERE run_id = ?
                """,
                (status, _utc_now(), final_text, error, run_id),
            )
