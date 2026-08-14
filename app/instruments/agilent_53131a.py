import logging
import random
import time

from app.config import SIMULATION_MODE

logger = logging.getLogger(__name__)


class _SimulatedCounterTransport:
    """Fake instrument pra rodar sem GPIB real conectado."""

    def __init__(self):
        self._base_count = 999_990

    def write(self, command: str) -> None:
        logger.info("[SIM Agilent53131A] -> %s", command)

    def query(self, command: str) -> str:
        self.write(command)
        cmd = command.strip().upper()
        if cmd.startswith("*IDN?"):
            return "Agilent Technologies,53131A,SIM00000,SIM-3.0"
        if cmd.startswith(":FETC"):
            value = self._base_count + random.randint(-5, 5)
            return f"{value:+.5E}"
        return "0"

    def close(self) -> None:
        pass


class Agilent53131ACounter:
    """Driver pro contador de frequência Agilent 53131A via GPIB, usado no
    ensaio de RTC/Timer (mede a contagem total de pulsos do oscilador do
    medidor durante um tempo de gate fixo — :CONFigure:TOTalize:TIMed).

    Sequência de comandos baseada no script validado em campo
    (TIMER_RTC_TESTE.py): configura o gate, dispara com INIT, aguarda o gate
    terminar e só então consulta o resultado. Confirmado em campo (erro SCPI
    -213 "Init ignored") que a leitura final precisa ser :FETCh? — não
    :MEASure:...? — porque esse último dispara outro INIT por dentro.
    """

    def __init__(
        self,
        gpib_address: int = 1,
        gpib_board: int = 1,
        simulate: bool | None = None,
        timeout_ms: int = 10000,
    ):
        self.gpib_address = gpib_address
        self.gpib_board = gpib_board
        self.simulate = SIMULATION_MODE if simulate is None else simulate
        self.timeout_ms = timeout_ms
        self._inst = None

    def connect(self) -> None:
        if self.simulate:
            self._inst = _SimulatedCounterTransport()
            logger.info("[SIM Agilent53131A] conectado")
            return

        import pyvisa

        rm = pyvisa.ResourceManager()
        resource = f"GPIB{self.gpib_board}::{self.gpib_address}::INSTR"
        self._inst = rm.open_resource(resource)
        self._inst.timeout = self.timeout_ms
        logger.info("[Agilent53131A] conectado em %s", resource)

    def disconnect(self) -> None:
        if self._inst is not None:
            try:
                self._inst.close()
            except Exception:
                pass
            self._inst = None

    def idn(self) -> str:
        return self._inst.query("*IDN?").strip()

    def recall(self, register: int) -> None:
        """Carrega o estado salvo no registro indicado do instrumento
        (equivalente a apertar Save/Recall > Recall N no painel frontal)."""
        self._inst.write(f"*RCL {register}")

    def read_totalize(self, gate_time_s: float) -> float:
        """Configura e mede a contagem total de pulsos durante gate_time_s
        segundos: CONFigure + INIT + aguarda o gate + FETCh? (consulta só o
        resultado, sem disparar outro INIT). Modo 'configuração manual' —
        sobrescreve qualquer configuração carregada por Recall.

        Usa FETCh? em vez de :MEASure:TOTalize:TIMed? porque esse último já
        faz seu próprio INIT por dentro (é um comando "configura+dispara+lê"
        combinado) — encadeado depois de um INIT manual, o instrumento recusa
        o segundo INIT com o erro SCPI -213 "Init ignored"."""
        self._inst.write(f":CONFigure:TOTalize:TIMed {gate_time_s}")
        self._inst.write("INIT")
        time.sleep(gate_time_s + 0.2)
        value = self._inst.query(":FETCh?")
        return float(value)

    def try_read_current(self, poll_timeout_ms: int = 2000) -> float | None:
        """Tenta ler o resultado mais recente usando a configuração ATUALMENTE
        ativa no instrumento (a que veio de um Recall, ou a que já estava
        configurada no painel) — sem mandar INIT algum. Usado no modo Recall
        pra 'escutar' o instrumento continuamente: como o registro recuperado
        pode estar disparando sozinho (:INITiate:CONTinuous ON) num ritmo
        desconhecido pelo app, cada tentativa usa um timeout curto — se o
        instrumento ainda não tem um resultado pronto, retorna None (quem
        chamou tenta de novo depois) em vez de estourar um erro de timeout.
        Outros erros reais (barramento, etc.) continuam sendo levantados."""
        if self.simulate:
            return float(self._inst.query(":FETCh?"))

        import pyvisa

        original_timeout = self._inst.timeout
        self._inst.timeout = poll_timeout_ms
        try:
            return float(self._inst.query(":FETCh?"))
        except pyvisa.errors.VisaIOError as exc:
            if exc.error_code == pyvisa.constants.StatusCode.error_timeout:
                return None
            raise
        finally:
            self._inst.timeout = original_timeout
