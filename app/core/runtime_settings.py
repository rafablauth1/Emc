from dataclasses import dataclass, field

from app.config import (
    DEFAULT_GPIB_ADDRESSES,
    DEFAULT_GPIB_BOARDS,
    DEFAULT_SERIAL_PORTS,
    SIMULATION_MODE,
)


@dataclass
class RuntimeSettings:
    simulation_mode: bool = SIMULATION_MODE
    gpib_addresses: dict = field(default_factory=lambda: dict(DEFAULT_GPIB_ADDRESSES))
    gpib_boards: dict = field(default_factory=lambda: dict(DEFAULT_GPIB_BOARDS))
    serial_ports: dict = field(default_factory=lambda: dict(DEFAULT_SERIAL_PORTS))
    buzzer_enabled: bool = True


settings = RuntimeSettings()
