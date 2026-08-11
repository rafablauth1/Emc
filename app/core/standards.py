from dataclasses import dataclass


@dataclass(frozen=True)
class BurstLevel:
    level: int
    voltage: int


@dataclass(frozen=True)
class SurgeLevel:
    level: int
    voltage: int


@dataclass(frozen=True)
class DipsLevel:
    level: int
    percent_un: int
    duration_ms: float
    cycles: float


# Valores extraídos do manual EM TEST UCS 500Nx (V5.16), seções 9.1.2, 10.1.2 e 11.2.2 —
# são os níveis padrão definidos nas próprias normas IEC 61000-4-4/4-5/4-11, não são
# comandos proprietários do fabricante.

BURST_LEVELS = [
    BurstLevel(1, 500),
    BurstLevel(2, 1000),
    BurstLevel(3, 2000),
    BurstLevel(4, 4000),
]
BURST_SPIKE_FREQUENCIES_HZ = (5000, 100000)
BURST_DURATION_MS_BY_FREQ = {5000: 15.0, 100000: 0.75}
BURST_REPETITION_MS = 300
BURST_COUPLINGS = ("COM", "ALL", "CCC")  # COM = IEC Ed.2 (2004), ALL = IEC Ed.1 (1995)
BURST_POLARITIES = ("+", "-")

SURGE_LEVELS = [
    SurgeLevel(1, 500),
    SurgeLevel(2, 1000),
    SurgeLevel(3, 2000),
    SurgeLevel(4, 4000),
]
SURGE_VOLTAGE_RISE_US = 1.2
SURGE_VOLTAGE_DURATION_US = 50
SURGE_CURRENT_RISE_US = 8
SURGE_CURRENT_DURATION_US = 20
SURGE_PHASE_ANGLES_DEG = (0, 90, 180, 270)
SURGE_COUPLINGS = ("L-N", "L-PE", "N-PE", "L+N-PE")
SURGE_POLARITIES = ("+", "-", "ALT")

DIPS_LEVELS = [
    DipsLevel(1, 0, 10.0, 0.5),
    DipsLevel(2, 0, 20.0, 1),
    DipsLevel(3, 40, 200.0, 10),
    DipsLevel(4, 70, 500.0, 25),
    DipsLevel(5, 80, 5000.0, 250),
]
DIPS_SHORT_INTERRUPTION_MS = 5000.0
DIPS_PHASE_ANGLES_DEG = (0, 90, 180, 270)
