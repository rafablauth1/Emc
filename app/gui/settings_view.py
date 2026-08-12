from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.runtime_settings import settings


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.sim_checkbox = QCheckBox("Modo simulado (sem hardware GPIB)")
        self.sim_checkbox.setChecked(settings.simulation_mode)
        self.sim_checkbox.toggled.connect(self._on_sim_toggled)
        layout.addWidget(self.sim_checkbox)
        layout.addWidget(
            QLabel(
                "Neste PC não há NI-VISA/NI-488.2 instalado — mantenha o modo simulado.\n"
                "No PC do laboratório, instale o driver NI-488.2 (ou NI-VISA) do adaptador\n"
                "GPIB-USB-HS e desmarque esta opção para controlar os equipamentos de verdade."
            )
        )

        self.buzzer_checkbox = QCheckBox("Buzzer nas pausas do ensaio (troca de ligação)")
        self.buzzer_checkbox.setChecked(settings.buzzer_enabled)
        self.buzzer_checkbox.toggled.connect(self._on_buzzer_toggled)
        layout.addWidget(self.buzzer_checkbox)
        layout.addWidget(
            QLabel(
                "Quando o ensaio pausa pedindo pra trocar a ligação do medidor, toca um "
                "buzzer além do aviso na tela. Desmarque para deixar só o aviso visual."
            )
        )

        form = QFormLayout()
        self.ucs_addr_spin = QSpinBox()
        self.ucs_addr_spin.setRange(1, 31)
        self.ucs_addr_spin.setValue(settings.gpib_addresses["ucs500n"])
        self.ucs_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("ucs500n", v)
        )
        form.addRow("Endereço GPIB — EM TEST UCS 500N:", self.ucs_addr_spin)

        self.chroma_addr_spin = QSpinBox()
        self.chroma_addr_spin.setRange(1, 30)
        self.chroma_addr_spin.setValue(settings.gpib_addresses["chroma"])
        self.chroma_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("chroma", v)
        )
        form.addRow("Endereço GPIB — Chroma 61501/61504:", self.chroma_addr_spin)
        layout.addLayout(form)

        layout.addStretch()

    def _on_sim_toggled(self, checked: bool) -> None:
        settings.simulation_mode = checked

    def _on_buzzer_toggled(self, checked: bool) -> None:
        settings.buzzer_enabled = checked
