import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from app.instruments.agilent_53131a import Agilent53131ACounter


class CounterWorker(QThread):
    """Roda a leitura contínua do contador Agilent 53131A em thread separada,
    pra não travar a tela durante os gates longos (podem levar minutos).

    Dois modos: 'manual' configura o instrumento pelo app a cada leitura
    (:CONFigure:TOTalize:TIMed); 'recall' carrega um registro salvo no
    instrumento (*RCL N) uma vez no início e depois só dispara/lê (INIT +
    FETCh?), sem sobrescrever a configuração recuperada."""

    reading = Signal(str, float)  # timestamp ISO, valor lido
    error = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        counter: Agilent53131ACounter,
        gate_time_s: float,
        interval_s: float,
        mode: str = "manual",
        recall_register: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.counter = counter
        self.gate_time_s = gate_time_s
        self.interval_s = interval_s
        self.mode = mode
        self.recall_register = recall_register
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            self.counter.connect()
            if self.mode == "recall" and self.recall_register is not None:
                self.counter.recall(self.recall_register)
        except Exception as exc:
            self.error.emit(str(exc))
            self.stopped.emit()
            return

        try:
            while not self._stop_requested:
                try:
                    if self.mode == "recall":
                        value = self.counter.read_current(self.gate_time_s)
                    else:
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


class RecallWorker(QThread):
    """Conecta no contador, carrega um registro de Recall salvo (*RCL N) e
    desconecta — em thread separada pra não travar a tela."""

    result = Signal(bool, str)

    def __init__(self, counter: Agilent53131ACounter, register: int, parent=None):
        super().__init__(parent)
        self.counter = counter
        self.register = register

    def run(self) -> None:
        try:
            self.counter.connect()
            self.counter.recall(self.register)
            self.result.emit(True, f"Recall {self.register} carregado.")
        except Exception as exc:
            self.result.emit(False, str(exc))
        finally:
            self.counter.disconnect()
