from dataclasses import dataclass, field

from app.config import DEFAULT_GPIB_ADDRESSES, DEFAULT_SERIAL_PORTS, SIMULATION_MODE


@dataclass
class RuntimeSettings:
    simulation_mode: bool = SIMULATION_MODE
    gpib_addresses: dict = field(default_factory=lambda: dict(DEFAULT_GPIB_ADDRESSES))
    serial_ports: dict = field(default_factory=lambda: dict(DEFAULT_SERIAL_PORTS))


settings = RuntimeSettings()
