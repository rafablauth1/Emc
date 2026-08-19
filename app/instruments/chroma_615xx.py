import time
from typing import Callable, Optional

from app.core.command_overrides import load_overrides
from app.instruments import chroma_commands as cmd
from app.instruments.base import InstrumentDriver, TestResult

SETUP_SETTLE_S = 2.0  # espera após ligar a saída, antes do primeiro evento (igual ao script de referência)


class Chroma615xxDriver(InstrumentDriver):
    """Chroma 61501/61502/61503/61504 — Dips/Interrupções (IEC 61000-4-11).

    Troca a tensão direto (VOLT:AC) e espera em software (time.sleep) a
    duração do evento em ciclos, depois volta pra nominal. NÃO usa modo
    PULSE nem LIST (OUTP:MODE + TRIG): os dois estão documentados no manual
    oficial, mas em dois testes reais separados nunca chegaram a mudar a
    saída nem mostrar RUNNING — só a escrita direta de VOLT realmente
    funciona nesse equipamento, confirmado no script de campo
    Teste_IEC61000-4-11.py (Pedro Henrique De Ros/EMC) pra 8 dos 9 grupos de
    evento da norma.
    """

    def _cmd(self, name: str, **kwargs) -> str:
        """Monta a string de comando, usando o valor salvo na aba Comandos se
        o operador tiver sobrescrito algum, senão cai no padrão de
        app/instruments/chroma_commands.py."""
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
        frequency_hz = params.get("frequency_hz", 60)
        default_phase_angles = params.get("phase_angles", [0])
        events = params["events"]
        # cada evento: {percent_un, cycles} | {interruption: True, cycles} — duração em
        # ciclos, como as normas definem (IEC 61000-4-11 / NIT-SEGEL-044). Opcionais por
        # evento: count (repetições desse evento, padrão 1), interval_cycles (pausa em
        # nominal entre repetições, padrão 0), phase_angles (padrão = default_phase_angles
        # — sem efeito prático aqui, a troca de tensão não é sincronizada com a forma de
        # onda; mantido só pra rotular o log e pra compatibilidade com o roteiro salvo).

        total_lines = len(events)
        total_pulses = sum(
            event.get("count", 1) * len(event.get("phase_angles") or default_phase_angles)
            for event in events
        )

        # Trava a faixa de tensão (LOW até 150V, HIGH acima) em vez de deixar em AUTO —
        # em AUTO o equipamento troca de faixa sozinho via relé a cada mudança de tensão,
        # o que dá um estalo audível (confirmado no manual, "click sound... when output
        # relay is activated") — em alguns Chroma (61504) isso acontece a cada dip, no
        # 61501 não. Fixar a faixa evita essa troca automática.
        voltage_range = "LOW" if nominal_voltage <= 150 else "HIGH"
        self._transport.write(self._cmd("VOLTAGE_RANGE", range=voltage_range))
        self._transport.write(self._cmd("SET_VOLTAGE_AC", voltage=nominal_voltage))
        self._transport.write(self._cmd("SET_FREQUENCY", frequency_hz=frequency_hz))
        self._transport.write(self._cmd("OUTPUT_STATE", state="ON"))
        time.sleep(SETUP_SETTLE_S)
        self._emit(
            on_progress,
            f"Chroma pronto — Un={nominal_voltage}V, {frequency_hz}Hz — "
            f"{total_lines} linha(s) do roteiro, {total_pulses} pulso(s) no total",
        )

        applied = 0
        for line_num, event in enumerate(events, start=1):
            is_interruption = bool(event.get("interruption"))
            dip_voltage = 0.0 if is_interruption else nominal_voltage * event["percent_un"] / 100
            cycles = event["cycles"]
            duration_s = cycles / frequency_hz
            count = event.get("count", 1)
            interval_s = event.get("interval_cycles", 0) / frequency_hz
            phase_angles = event.get("phase_angles") or default_phase_angles
            label = "Interrupção" if is_interruption else f"Dip {event['percent_un']}% Un"

            self._emit(
                on_progress,
                f"[Linha {line_num}/{total_lines}] {label}, {cycles:g} ciclo(s), "
                f"{count} repetição(ões), ângulo(s) {phase_angles}",
            )

            for angle in phase_angles:
                for rep in range(count):
                    if should_stop and should_stop():
                        self._transport.write(self._cmd("SET_VOLTAGE_AC", voltage=nominal_voltage))
                        self._transport.write(self._cmd("OUTPUT_STATE", state="OFF"))
                        self._emit(on_progress, "Ensaio interrompido pelo operador")
                        return TestResult(passed=False, applied_events=applied)

                    applied += 1
                    self._emit(
                        on_progress,
                        f"  [Linha {line_num}/{total_lines} · pulso {applied}/{total_pulses}] "
                        f"aplicando {label} ({angle}°, repetição {rep + 1}/{count})...",
                    )
                    self._transport.write(self._cmd("SET_VOLTAGE_AC", voltage=dip_voltage))
                    time.sleep(duration_s)
                    self._transport.write(self._cmd("SET_VOLTAGE_AC", voltage=nominal_voltage))
                    self._emit(
                        on_progress,
                        f"  [Linha {line_num}/{total_lines} · pulso {applied}/{total_pulses}] "
                        f"concluído, de volta a {nominal_voltage}V",
                    )

                    if interval_s and rep < count - 1:
                        time.sleep(interval_s)

        self._transport.write(self._cmd("OUTPUT_STATE", state="OFF"))
        self._emit(on_progress, f"Ensaio concluído — {applied}/{total_pulses} pulso(s) aplicado(s)")
        return TestResult(passed=True, applied_events=applied)

    def _emit(self, on_progress, message: str) -> None:
        if on_progress:
            on_progress(message)
