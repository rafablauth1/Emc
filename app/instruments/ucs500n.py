import time
from typing import Callable, Optional

from app.instruments import ucs500n_commands as cmd
from app.instruments.base import InstrumentDriver, TestResult

STEP_DELAY_S = 0.3


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
        voltage = params["voltage"]
        frequency_hz = params.get("frequency_hz", 5000)
        coupling = params.get("coupling", "COM")
        polarities = params.get("polarities", ["+", "-"])

        self._transport.write(cmd.SELECT_BURST_MENU)
        self._transport.write(cmd.SET_BURST_VOLTAGE.format(voltage=voltage))
        self._transport.write(cmd.SET_BURST_FREQUENCY.format(frequency_hz=frequency_hz))
        self._transport.write(cmd.SET_BURST_COUPLING.format(coupling=coupling))
        self._emit(on_progress, f"Burst {voltage}V, {frequency_hz}Hz, coupling {coupling}")

        applied = 0
        for polarity in polarities:
            if should_stop and should_stop():
                self._emit(on_progress, "Ensaio interrompido pelo operador")
                return TestResult(passed=False, applied_events=applied)
            self._transport.write(cmd.SET_BURST_POLARITY.format(polarity=polarity))
            self._transport.query(cmd.TRIGGER_SINGLE_EVENT)
            applied += 1
            self._emit(on_progress, f"Burst aplicado — polaridade {polarity}")
            time.sleep(STEP_DELAY_S)

        self._transport.write(cmd.STOP_TEST)
        return TestResult(passed=True, applied_events=applied)

    def _run_surge(self, params, on_progress, should_stop) -> TestResult:
        voltage = params["voltage"]
        coupling = params.get("coupling", "L-N")
        polarities = params.get("polarities", ["+", "-"])
        phase_angles = params.get("phase_angles", [0, 90, 180, 270])

        self._transport.write(cmd.SELECT_SURGE_MENU)
        self._transport.write(cmd.SET_SURGE_VOLTAGE.format(voltage=voltage))
        self._transport.write(cmd.SET_SURGE_COUPLING.format(coupling=coupling))
        self._emit(on_progress, f"Surge {voltage}V, coupling {coupling}")

        applied = 0
        for polarity in polarities:
            for angle in phase_angles:
                if should_stop and should_stop():
                    self._emit(on_progress, "Ensaio interrompido pelo operador")
                    return TestResult(passed=False, applied_events=applied)
                self._transport.write(cmd.SET_SURGE_POLARITY.format(polarity=polarity))
                self._transport.write(cmd.SET_SURGE_PHASE_ANGLE.format(angle_deg=angle))
                self._transport.query(cmd.TRIGGER_SINGLE_EVENT)
                applied += 1
                self._emit(on_progress, f"Surge aplicado — {polarity}, {angle}°")
                time.sleep(STEP_DELAY_S)

        self._transport.write(cmd.STOP_TEST)
        return TestResult(passed=True, applied_events=applied)
