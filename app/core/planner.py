from datetime import datetime, timezone
from typing import Optional

from app.config import STANDARDS
from app.core.db import db_cursor


def create_project(name: str, client: str = "") -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO projects (name, client, created_at) VALUES (?, ?, ?)",
            (name, client, created_at),
        )
        project_id = cur.lastrowid
        for standard_code in STANDARDS:
            cur.execute(
                "INSERT INTO test_items (project_id, standard_code, status) VALUES (?, ?, 'pendente')",
                (project_id, standard_code),
            )
    return project_id


def list_projects() -> list[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM projects ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def get_project(project_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_test_items(project_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_items WHERE project_id = ? ORDER BY standard_code",
            (project_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_scheduled_items() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT test_items.*, projects.name AS project_name
            FROM test_items
            JOIN projects ON projects.id = test_items.project_id
            WHERE test_items.scheduled_date IS NOT NULL
            ORDER BY test_items.scheduled_date
            """
        )
        return [dict(row) for row in cur.fetchall()]


def update_item_status(item_id: int, status: str) -> None:
    with db_cursor() as cur:
        cur.execute("UPDATE test_items SET status = ? WHERE id = ?", (status, item_id))


def update_item_schedule(item_id: int, scheduled_date: Optional[str]) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE test_items SET scheduled_date = ? WHERE id = ?", (scheduled_date, item_id)
        )


def link_item_session(item_id: int, session_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE test_items SET session_id = ?, status = 'concluido' WHERE id = ?",
            (session_id, item_id),
        )


def find_item(project_id: int, standard_code: str) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_items WHERE project_id = ? AND standard_code = ?",
            (project_id, standard_code),
        )
        row = cur.fetchone()
        return dict(row) if row else None
