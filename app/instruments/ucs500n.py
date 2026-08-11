import time
from typing import Callable, Optional

from app.core.legacy_routines import burst_params_to_points, surge_params_to_points
from app.instruments import ucs500n_commands as cmd
from app.instruments.base import InstrumentDriver, TestResult

STEP_DELAY_S = 0.3
SLEEP_POLL_S = 0.2


def _interruptible_sleep(duration_s: float, should_stop: Optional[Callable[[], bool]]) -> bool:
    """Dorme por duration_s em pequenos passos, checando should_stop. Retorna True se foi
    interrompido no meio do caminho (para o chamador poder abortar o ensaio prontamente)."""
    elapsed = 0.0
    while elapsed < duration_s:
        if should_stop and should_stop():
            return True
        step = min(SLEEP_POLL_S, duration_s - elapsed)
        time.sleep(step)
        elapsed += step
    return False


class UCS500NDriver(InstrumentDriver):
    """EM TEST UCS 500N — Burst (IEC 61000-4-4) e Surge (IEC 61000-4-5)."""

    def run_test(
        self,
        standard_code: str,
        params: dict,
        on_progress: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> TestResult:
        if standard_code == "4-4":
            return self._run_burst(params, on_progress, should_stop)
        if standard_code == "4-5":
            return self._run_surge(params, on_progress, should_stop)
        raise ValueError(f"UCS500NDriver não suporta a norma {standard_code}")

    def _emit(self, on_progress, message: str) -> None:
        if on_progress:
            on_progress(message)

    def _run_burst(self, params, on_progress, should_stop) -> TestResult:
        points = burst_params_to_points(params)
        if not points:
            raise ValueError("Roteiro de burst sem pontos.")

        self._transport.write(cmd.SELECT_BURST_MENU)
        self._emit(on_progress, f"Burst — roteiro com {len(points)} ponto(s)")

        applied = 0
        for index, point in enumerate(points):
            if should_stop and should_stop():
                self._emit(on_progress, "Ensaio interrompido pelo operador")
                return TestResult(passed=False, applied_events=applied)

            voltage = point["voltage"]
            frequency_hz = point.get("frequency_hz", 5000)
            coupling = point.get("coupling", "COM")
            polarity = point.get("polarity", "+")
            duration_s = point.get("duration_s", STEP_DELAY_S)

            self._transport.write(cmd.SET_BURST_VOLTAGE.format(voltage=voltage))
            self._transport.write(cmd.SET_BURST_FREQUENCY.format(frequency_hz=frequency_hz))
            self._transport.write(cmd.SET_BURST_COUPLING.format(coupling=coupling))
            self._transport.write(cmd.SET_BURST_POLARITY.format(polarity=polarity))
            self._transport.query(cmd.TRIGGER_SINGLE_EVENT)
            applied += 1
            self._emit(
                on_progress,
                f"Ponto {index + 1}/{len(points)} — {voltage}V, {frequency_hz}Hz, "
                f"{coupling}, polaridade {polarity} ({duration_s:.1f}s)",
            )
            if _interruptible_sleep(duration_s, should_stop):
                self._transport.write(cmd.STOP_TEST)
                self._emit(on_progress, "Ensaio interrompido pelo operador")
                return TestResult(passed=False, applied_events=applied)

        self._transport.write(cmd.STOP_TEST)
        return TestResult(passed=True, applied_events=applied)

    def _run_surge(self, params, on_progress, should_stop) -> TestResult:
        points = surge_params_to_points(params)
        if not points:
            raise ValueError("Roteiro de surge sem pontos.")

        self._transport.write(cmd.SELECT_SURGE_MENU)
        self._emit(on_progress, f"Surge — roteiro com {len(points)} ponto(s)")

        applied = 0
        for index, point in enumerate(points):
            voltage = point["voltage"]
            coupling = point.get("coupling", "L-N")
            polarity = point.get("polarity", "+")
            angle = point.get("phase_angle", 0)
            pulse_count = point.get("pulse_count", 1)
            interval_s = point.get("interval_s", STEP_DELAY_S)

            self._transport.write(cmd.SET_SURGE_VOLTAGE.format(voltage=voltage))
            self._transport.write(cmd.SET_SURGE_COUPLING.format(coupling=coupling))
            self._transport.write(cmd.SET_SURGE_POLARITY.format(polarity=polarity))
            self._transport.write(cmd.SET_SURGE_PHASE_ANGLE.format(angle_deg=angle))

            for rep in range(pulse_count):
                if should_stop and should_stop():
                    self._emit(on_progress, "Ensaio interrompido pelo operador")
                    return TestResult(passed=False, applied_events=applied)
                self._transport.query(cmd.TRIGGER_SINGLE_EVENT)
                applied += 1
                self._emit(
                    on_progress,
                    f"Ponto {index + 1}/{len(points)} — {voltage}V, {coupling}, "
                    f"{polarity}, {angle}° (pulso {rep + 1}/{pulse_count})",
                )
                if rep < pulse_count - 1:
                    if _interruptible_sleep(interval_s, should_stop):
                        self._emit(on_progress, "Ensaio interrompido pelo operador")
                        return TestResult(passed=False, applied_events=applied)

        self._transport.write(cmd.STOP_TEST)
        return TestResult(passed=True, applied_events=applied)
