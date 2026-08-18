import time
from typing import Callable, Optional

from app.core.command_overrides import load_overrides
from app.instruments import chroma_commands as cmd
from app.instruments.base import InstrumentDriver, TestResult

PULSE_GUARD_MS = 200.0  # margem entre o fim do pulso e o fim do período (o período deve ser > duração)
POLL_INTERVAL_S = 0.1
POLL_TIMEOUT_S = 15.0


class Chroma615xxDriver(InstrumentDriver):
    """Chroma 61501/61502/61503/61504 — Dips/Interrupções (IEC 61000-4-11).

    Usa o modo PULSE do equipamento (manual de programação, seção 8.6.2.8):
    a tensão nominal fica ligada em regime normal e cada evento de dip ou
    interrupção é programado como um pulso único de tensão reduzida.
    """

    def _cmd(self, name: str, **kwargs) -> str:
        """Monta a string de comando, usando o valor salvo na aba Comandos se
        o operador tiver sobrescrito algum, senão cai no padrão (confirmado
        no manual oficial) de app/instruments/chroma_commands.py."""
        overrides = load_overrides("chroma")
        template = overrides.get(name) or getattr(cmd, name)
        return template.format(**kwargs) if kwargs else template

    def connect(self) -> None:
        super().connect()
        self._transport.write(self._cmd("CLEAR_STATUS"))

    def run_test(
        self,
        standard_code: str,
        params: dict,
        on_progress: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        wait_for_operator: Optional[Callable[[str], bool]] = None,
    ) -> TestResult:
        if standard_code != "4-11":
            raise ValueError(f"Chroma615xxDriver não suporta a norma {standard_code}")

        nominal_voltage = params["nominal_voltage"]
        frequency_hz = params.get("frequency_hz", 50)
        voltage_range = params.get("voltage_range", "AUTO")
        default_phase_angles = params.get("phase_angles", [0, 90, 180, 270])
        events = params["events"]
        # cada evento: {percent_un, duration_ms} | {interruption: True, duration_ms}
        # opcionais por evento: count (repetições, padrão 1), phase_angles (padrão = default_phase_angles),
        # interval_ms (tempo entre repetições do mesmo evento, padrão 0)

        self._transport.write(self._cmd("OUTPUT_STATE", state="OFF"))
        self._transport.write(self._cmd("VOLTAGE_RANGE", range=voltage_range))
        self._transport.write(self._cmd("SET_VOLTAGE_AC", voltage=nominal_voltage))
        self._transport.write(self._cmd("SET_FREQUENCY", frequency_hz=frequency_hz))
        self._transport.write(self._cmd("OUTPUT_STATE", state="ON"))
        self._emit(on_progress, f"Chroma pronto — Un={nominal_voltage}V, {frequency_hz}Hz")

        applied = 0
        for event in events:
            is_interruption = bool(event.get("interruption"))
            dip_voltage = 0.0 if is_interruption else nominal_voltage * event["percent_un"] / 100
            duration_ms = event["duration_ms"]
            period_ms = duration_ms + PULSE_GUARD_MS
            duty_pct = round(duration_ms / period_ms * 100, 1)
            phase_angles = event.get("phase_angles") or default_phase_angles
            count = event.get("count", 1)
            interval_ms = event.get("interval_ms", 0)
            label = "Interrupção" if is_interruption else f"Dip {event['percent_un']}% Un"

            for angle in phase_angles:
                for rep in range(count):
                    if should_stop and should_stop():
                        self._transport.write(self._cmd("TRIGGER_STATE", state="OFF"))
                        self._transport.write(self._cmd("OUTPUT_STATE", state="OFF"))
                        self._emit(on_progress, "Ensaio interrompido pelo operador")
                        return TestResult(passed=False, applied_events=applied)

                    self._transport.write(self._cmd("SET_PULSE_VOLTAGE_AC", voltage=dip_voltage))
                    self._transport.write(self._cmd("SET_PULSE_PERIOD_MS", period_ms=period_ms))
                    self._transport.write(self._cmd("SET_PULSE_DUTY_PCT", duty_pct=duty_pct))
                    self._transport.write(self._cmd("SET_PULSE_START_PHASE", phase_deg=angle))
                    self._transport.write(self._cmd("SET_PULSE_COUNT", count=1))
                    self._transport.write(self._cmd("OUTPUT_MODE", mode="PULSE"))
                    self._transport.write(self._cmd("TRIGGER_STATE", state="ON"))

                    self._wait_pulse_complete()

                    self._transport.write(self._cmd("TRIGGER_STATE", state="OFF"))
                    self._transport.write(self._cmd("OUTPUT_MODE", mode="FIXED"))

                    applied += 1
                    self._emit(
                        on_progress,
                        f"{label}, {duration_ms:.1f}ms — {angle}° (repetição {rep + 1}/{count})",
                    )
                    if interval_ms and rep < count - 1:
                        time.sleep(interval_ms / 1000)

        self._transport.write(self._cmd("OUTPUT_STATE", state="OFF"))
        return TestResult(passed=True, applied_events=applied)

    def _wait_pulse_complete(self) -> None:
        elapsed = 0.0
        while elapsed < POLL_TIMEOUT_S:
            state = self._transport.query(self._cmd("TRIGGER_STATE_QUERY")).strip().upper()
            if state != "RUNNING":
                return
            time.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

    def _emit(self, on_progress, message: str) -> None:
        if on_progress:
            on_progress(message)
