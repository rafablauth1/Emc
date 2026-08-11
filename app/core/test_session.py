import json
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QThread, Signal

from app.core.db import db_cursor
from app.instruments.base import InstrumentDriver


class TestSessionWorker(QThread):
    """Roda um ensaio contra um driver de instrumento em thread separada,
    gravando progresso e resultado no banco a cada etapa."""

    progress = Signal(str)
    finished_session = Signal(int)  # session_id

    def __init__(
        self,
        driver: InstrumentDriver,
        project_id: int,
        standard_code: str,
        eut_name: str,
        eut_serial: str,
        operator: str,
        level_label: str,
        params: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.driver = driver
        self.project_id = project_id
        self.standard_code = standard_code
        self.eut_name = eut_name
        self.eut_serial = eut_serial
        self.operator = operator
        self.level_label = level_label
        self.params = params
        self._stop_requested = False
        self.session_id: Optional[int] = None

    def request_stop(self) -> None:
        self._stop_requested = True

    def _should_stop(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        session_id = self._create_session(started_at)
        self.session_id = session_id

        def on_progress(message: str) -> None:
            self._log_event(session_id, message)
            self.progress.emit(message)

        result = None
        try:
            self.driver.connect()
            result = self.driver.run_test(
                self.standard_code, self.params, on_progress, self._should_stop
            )
        except Exception as exc:
            on_progress(f"ERRO: {exc}")
        finally:
            try:
                self.driver.disconnect()
            except Exception:
                pass

        finished_at = datetime.now(timezone.utc).isoformat()
        if result is None:
            outcome_note = "Ensaio abortado por erro de comunicação com o instrumento."
        elif not result.passed:
            outcome_note = "Ensaio interrompido pelo operador."
        else:
            outcome_note = ""
        self._finish_session(session_id, finished_at, outcome_note)
        self.finished_session.emit(session_id)

    def _create_session(self, started_at: str) -> int:
        with db_cursor() as cur:
            cur.execute(
                """INSERT INTO test_sessions
                (project_id, standard_code, eut_name, eut_serial, operator, level_label,
                 params_json, started_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')""",
                (
                    self.project_id,
                    self.standard_code,
                    self.eut_name,
                    self.eut_serial,
                    self.operator,
                    self.level_label,
                    json.dumps(self.params),
                    started_at,
                ),
            )
            return cur.lastrowid

    def _log_event(self, session_id: int, message: str) -> None:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO test_events (session_id, timestamp, message) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), message),
            )

    def _finish_session(self, session_id: int, finished_at: str, notes: str) -> None:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE test_sessions SET finished_at = ?, notes = ? WHERE id = ?",
                (finished_at, notes, session_id),
            )


def set_session_result(session_id: int, result: str, notes: str = "") -> None:
    """result: 'aprovado' | 'reprovado'. Chamado pelo operador após inspecionar o EUT."""
    with db_cursor() as cur:
        if notes:
            cur.execute(
                "UPDATE test_sessions SET result = ?, notes = ? WHERE id = ?",
                (result, notes, session_id),
            )
        else:
            cur.execute(
                "UPDATE test_sessions SET result = ? WHERE id = ?", (result, session_id)
            )


def get_session(session_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM test_sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_sessions_for_project(project_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_sessions WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_completed_sessions() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT test_sessions.*, projects.name AS project_name
            FROM test_sessions
            JOIN projects ON projects.id = test_sessions.project_id
            WHERE test_sessions.finished_at IS NOT NULL
            ORDER BY test_sessions.started_at DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def list_events(session_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_events WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [dict(row) for row in cur.fetchall()]
