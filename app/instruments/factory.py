from app.core.runtime_settings import settings
from app.instruments.chroma_615xx import Chroma615xxDriver
from app.instruments.transport import SimulatedTransport, VisaTransport, gpib_resource
from app.instruments.ucs500n import UCS500NDriver


def build_ucs500n_driver() -> UCS500NDriver:
    if settings.simulation_mode:
        transport = SimulatedTransport("UCS500N")
    else:
        transport = VisaTransport("UCS500N", gpib_resource(settings.gpib_addresses["ucs500n"]))
    return UCS500NDriver(transport)


def build_chroma_driver() -> Chroma615xxDriver:
    if settings.simulation_mode:
        transport = SimulatedTransport("Chroma61501")
    else:
        transport = VisaTransport("Chroma61501", gpib_resource(settings.gpib_addresses["chroma"]))
    return Chroma615xxDriver(transport)


def build_driver_for_standard(standard_code: str):
    if standard_code in ("4-4", "4-5"):
        return build_ucs500n_driver()
    if standard_code == "4-11":
        return build_chroma_driver()
    raise ValueError(f"Nenhum driver de automação disponível para a norma {standard_code}")
