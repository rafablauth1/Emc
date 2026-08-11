"""Comandos SCPI reais do Chroma 61501/61502/61503/61504 (Programmable AC Source),
extraídos do manual de programação oficial (P/N A11 000568, versão 1.1, capítulo 8).

Usado para ensaios de Quedas de Tensão / Interrupções (IEC 61000-4-11) através do
modo PULSE do equipamento: a tensão nominal fica em VOLTage:AC, e cada evento de
dip/interrupção é programado como um pulso único (PULSe:*) com a tensão reduzida
durante o duty cycle, disparado via TRIG.
"""

IDN_QUERY = "*IDN?"
RESET = "*RST"
CLEAR_STATUS = "*CLS"

OUTPUT_STATE = "OUTP {state}"  # ON | OFF
OUTPUT_RELAY = "OUTP:RELay {state}"  # ON | OFF
OUTPUT_MODE = "OUTP:MODE {mode}"  # FIXED | PULSE
VOLTAGE_RANGE = "VOLT:RANGe {range}"  # LOW | HIGH | AUTO

SET_VOLTAGE_AC = "VOLT:AC {voltage}"
SET_FREQUENCY = "FREQ {frequency_hz}"

SET_PULSE_VOLTAGE_AC = "PULS:VOLT:AC {voltage}"
SET_PULSE_PERIOD_MS = "PULS:PERiod {period_ms}"
SET_PULSE_DUTY_PCT = "PULS:DCYCle {duty_pct}"
SET_PULSE_START_PHASE = "PULS:SPHase {phase_deg}"
SET_PULSE_COUNT = "PULS:COUNt {count}"

TRIGGER_STATE = "TRIG {state}"  # ON | OFF
TRIGGER_STATE_QUERY = "TRIG:STATE?"

ERROR_QUERY = "SYST:ERRor?"
