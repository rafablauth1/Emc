from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.instruments.transport import Transport


@dataclass
class TestResult:
    passed: bool
    applied_events: int
    log: list = field(default_factory=list)


class InstrumentDriver(ABC):
    def __init__(self, transport: Transport):
        self._transport = transport

    def connect(self) -> None:
        self._transport.connect()

    def disconnect(self) -> None:
        self._transport.close()

    def idn(self) -> str:
        return self._transport.query("*IDN?")

    @abstractmethod
    def run_test(
        self,
        standard_code: str,
        params: dict,
        on_progress: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> TestResult:
        """Executa um ensaio e retorna o resultado. on_progress recebe mensagens de log.
        should_stop é consultado periodicamente para permitir cancelamento."""
        ...
