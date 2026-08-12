"""Strings de comando GPIB do EM TEST UCS 500N (Burst 4-4 / Surge 4-5).

O manual do operador (UCS 500N5/N7, V5.16) documenta a interface IEEE-488/GPIB
apenas como existente (endereço 1-31, seção 6.7) e descreve a navegação por
menus do painel frontal — não publica o dicionário de comandos ASCII/SCPI
usados pelo software "iec.control". Os comandos abaixo são placeholders;
quando o usuário enviar o manual/dicionário de comandos remoto real do
fabricante (ou o iec.control), preencher as strings aqui. Nenhum outro
arquivo do driver precisa mudar.
"""

# TODO: confirmar com manual/dicionário de comandos remoto real do fabricante
IDN_QUERY = "*IDN?"

# Seleção de módulo/menu (Burst = IEC 61000-4-4, Surge = IEC 61000-4-5/9)
SELECT_BURST_MENU = "TODO:SELECT_BURST"
SELECT_SURGE_MENU = "TODO:SELECT_SURGE"

# "TEST ON" — habilita/desabilita a saída do gerador (arma o interlock de segurança).
# Controlável manualmente pelo operador, independente de rodar um ensaio automatizado.
TEST_ON = "TODO:TEST_ON"
TEST_OFF = "TODO:TEST_OFF"

# Parâmetros de Burst (ver manual seção 9.1.1 / 9.3)
SET_BURST_VOLTAGE = "TODO:BURST_V {voltage}"
SET_BURST_FREQUENCY = "TODO:BURST_F {frequency_hz}"
SET_BURST_COUPLING = "TODO:BURST_CPL {coupling}"
SET_BURST_POLARITY = "TODO:BURST_POL {polarity}"

# Parâmetros de Surge (ver manual seção 10.1.1 / 10.1.2)
SET_SURGE_VOLTAGE = "TODO:SURGE_V {voltage}"
SET_SURGE_PHASE_ANGLE = "TODO:SURGE_A {angle_deg}"
SET_SURGE_COUPLING = "TODO:SURGE_CPL {coupling}"
SET_SURGE_POLARITY = "TODO:SURGE_POL {polarity}"

TRIGGER_SINGLE_EVENT = "TODO:TRIGGER"
STOP_TEST = "TODO:STOP"
QUERY_STATUS = "TODO:STATUS?"
