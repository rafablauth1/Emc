"""Semeia templates oficiais de roteiro de ensaio extraídos de normas do INMETRO.
Chamado (de forma idempotente) toda vez que o banco é inicializado."""

from app.core import templates

_CYCLE_MS_60HZ = 1000 / 60

NIT_SEGEL_044_NAME = "NIT-SEGEL-044 (medidores de energia elétrica)"


def seed_default_templates() -> None:
    _seed_burst()
    _seed_surge()
    _seed_dips()


def _seed_if_missing(standard_code: str, name: str, level_label: str, params: dict) -> None:
    existing = templates.list_templates(standard_code)
    if any(t["name"] == name for t in existing):
        return
    templates.save_template(standard_code, name, level_label, params)


def _seed_burst() -> None:
    # NIT-SEGEL-044 §9.3.2.1: circuito de tensão 4 kV, 60 s por polaridade, 5kHz (taxa padrão EFT).
    # Circuitos auxiliares >40V usam 2kV e <40V usam 1kV — ajustar manualmente nesses casos.
    _seed_if_missing(
        "4-4",
        NIT_SEGEL_044_NAME,
        "§9.3 — circuito de tensão 4 kV (aux. >40V: 2kV; aux. <40V: 1kV — ajustar manualmente)",
        {
            "voltage": 4000,
            "frequency_hz": 5000,
            "coupling": "COM",
            "polarities": ["+", "-"],
            "duration_s": 60,
        },
    )


def _seed_surge() -> None:
    # NIT-SEGEL-044 §9.2.3.3 (instrumento com neutro e PE): nível de severidade especificado é o
    # nível 4 — 2kV entre linhas (Zfonte=2ohm) e 4kV entre linha e terra (Zfonte=12ohm). Todos os
    # níveis inferiores (0,5/1/2 kV) também devem ser ensaiados conforme item 8 da IEC 61000-4-5 —
    # usar os presets de nível na tela para os níveis intermediários.
    _seed_if_missing(
        "4-5",
        f"{NIT_SEGEL_044_NAME} — L-N 2kV (nível 4)",
        "§9.2.3.3.a — entre linhas, 2kV, Zfonte=2Ω",
        {
            "voltage": 2000,
            "coupling": "L-N",
            "polarities": ["+", "-"],
            "phase_angles": [0, 90, 180, 270],
        },
    )
    _seed_if_missing(
        "4-5",
        f"{NIT_SEGEL_044_NAME} — L-PE 4kV (nível 4)",
        "§9.2.3.3.c — linha e terra, 4kV, Zfonte=12Ω",
        {
            "voltage": 4000,
            "coupling": "L-PE",
            "polarities": ["+", "-"],
            "phase_angles": [0, 90, 180, 270],
        },
    )


def _seed_dips() -> None:
    # NIT-SEGEL-044 Tabela 1 (item 9.6.3.2) — os 9 eventos oficiais para medidores de energia.
    # Durações convertidas de ciclos para ms considerando rede de 60Hz (padrão Brasil).
    # "Redução de tensão" da Tabela 1 é o quanto a tensão CAI; aqui convertido para percent_un,
    # que é a tensão REMANESCENTE (100 - redução) — convenção usada no resto do app.
    c = _CYCLE_MS_60HZ
    events = [
        {
            "interruption": True,
            "duration_ms": round(6 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(3 * c, 1),
        },
        {
            "interruption": True,
            "duration_ms": round(60 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(3 * c, 1),
        },
        {
            "interruption": True,
            "duration_ms": round(1 * c, 1),
            "count": 1,
            "phase_angles": [0],
        },
        {
            "percent_un": 5,
            "duration_ms": round(300 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(600 * c, 1),
        },
        {
            "percent_un": 40,
            "duration_ms": round(6 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(600 * c, 1),
        },
        {
            "percent_un": 40,
            "duration_ms": round(60 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(600 * c, 1),
        },
        {
            "percent_un": 70,
            "duration_ms": round(0.5 * c, 1),
            "count": 3,
            "phase_angles": [0, 180],
            "interval_ms": round(600 * c, 1),
        },
        {
            "percent_un": 70,
            "duration_ms": round(1 * c, 1),
            "count": 3,
            "phase_angles": [0],
            "interval_ms": round(600 * c, 1),
        },
        {
            "percent_un": 50,
            "duration_ms": round(3600 * c, 1),
            "count": 1,
            "phase_angles": [0],
        },
    ]
    _seed_if_missing(
        "4-11",
        NIT_SEGEL_044_NAME,
        "Tabela 1 completa (9 eventos, rede 60Hz) — só ajustar a tensão nominal (Un)",
        {
            "nominal_voltage": 220,
            "frequency_hz": 60,
            "phase_angles": [0],
            "events": events,
        },
    )
