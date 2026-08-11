import json
from datetime import datetime, timezone
from typing import Optional

from app.core.db import db_cursor


def save_template(standard_code: str, name: str, level_label: str, params: dict) -> int:
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO templates (standard_code, name, level_label, params_json, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                standard_code,
                name,
                level_label,
                json.dumps(params),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def list_templates(standard_code: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM templates WHERE standard_code = ? ORDER BY name",
            (standard_code,),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["params"] = json.loads(row["params_json"])
    return rows


def get_template(template_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
        row = cur.fetchone()
    if row is None:
        return None
    data = dict(row)
    data["params"] = json.loads(data["params_json"])
    return data


def delete_template(template_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM templates WHERE id = ?", (template_id,))
