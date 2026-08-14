import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from app.instruments.agilent_53131a import Agilent53131ACounter


class CounterWorker(QThread):
    """Roda a leitura contínua do contador Agilent 53131A em thread separada,
    pra não travar a tela durante os gates longos (podem levar minutos)."""

    reading = Signal(str, float)  # timestamp ISO, valor lido
    error = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        counter: Agilent53131ACounter,
        gate_time_s: float,
        interval_s: float,
        parent=None,
    ):
        super().__init__(parent)
        self.counter = counter
        self.gate_time_s = gate_time_s
        self.interval_s = interval_s
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            self.counter.connect()
        except Exception as exc:
            self.error.emit(str(exc))
            self.stopped.emit()
            return

        try:
            while not self._stop_requested:
                try:
                    value = self.counter.read_totalize(self.gate_time_s)
                except Exception as exc:
                    self.error.emit(str(exc))
                    break
                if self._stop_requested:
                    break
                timestamp = datetime.now().isoformat(timespec="seconds")
                self.reading.emit(timestamp, value)

                waited = 0.0
                while waited < self.interval_s and not self._stop_requested:
                    time.sleep(0.1)
                    waited += 0.1
        finally:
            self.counter.disconnect()
            self.stopped.emit()
