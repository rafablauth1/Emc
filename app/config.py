from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "app.db"

# Sem NI-VISA/hardware neste PC de desenvolvimento: modo simulado por padrão.
# Trocar para False no PC do laboratório, com NI-VISA instalado e os
# instrumentos conectados via GPIB.
SIMULATION_MODE = True

DEFAULT_GPIB_ADDRESSES = {
    "ucs500n": 6,
    "chroma": 1,
}

DEFAULT_SERIAL_PORTS = {
    "ucs500n": "COM3",
    "chroma": "COM4",
}

STANDARDS = {
    "4-2": "Descarga Eletrostática (ESD)",
    "4-3": "Campo Eletromagnético Irradiado (RS)",
    "4-4": "Transitórios Elétricos Rápidos em Salvas (Burst/EFT)",
    "4-5": "Surtos (Surge)",
    "4-6": "Perturbações Conduzidas Induzidas por Campos RF (CS)",
    "4-11": "Quedas de Tensão, Interrupções Curtas e Variações de Tensão (Dips)",
    "4-19": "Distúrbios Conduzidos de Corrente Contínua",
}

# Normas cobertas por automação de equipamento nesta primeira versão.
AUTOMATED_STANDARDS = ("4-4", "4-5", "4-11")

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
