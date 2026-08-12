from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.comm_test import CommTestWorker
from app.core.runtime_settings import settings
from app.instruments.factory import build_chroma_driver, build_ucs500n_driver


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._comm_test_workers: dict[str, CommTestWorker] = {}
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

        layout.addWidget(QLabel("Teste de comunicação GPIB (connect + *IDN?):"))

        ucs_test_row = QHBoxLayout()
        ucs_test_btn = QPushButton("Testar comunicação — UCS 500N")
        ucs_test_btn.clicked.connect(lambda: self._test_comm("ucs500n", build_ucs500n_driver))
        self.ucs_test_status = QLabel("")
        ucs_test_row.addWidget(ucs_test_btn)
        ucs_test_row.addWidget(self.ucs_test_status, 1)
        layout.addLayout(ucs_test_row)

        chroma_test_row = QHBoxLayout()
        chroma_test_btn = QPushButton("Testar comunicação — Chroma")
        chroma_test_btn.clicked.connect(lambda: self._test_comm("chroma", build_chroma_driver))
        self.chroma_test_status = QLabel("")
        chroma_test_row.addWidget(chroma_test_btn)
        chroma_test_row.addWidget(self.chroma_test_status, 1)
        layout.addLayout(chroma_test_row)

        layout.addStretch()

    def _on_sim_toggled(self, checked: bool) -> None:
        settings.simulation_mode = checked

    def _on_buzzer_toggled(self, checked: bool) -> None:
        settings.buzzer_enabled = checked

    def _test_comm(self, instrument: str, driver_factory) -> None:
        status_label = self.ucs_test_status if instrument == "ucs500n" else self.chroma_test_status
        status_label.setStyleSheet("")
        status_label.setText("Testando...")
        worker = CommTestWorker(driver_factory)
        worker.result.connect(lambda ok, msg: self._on_comm_test_result(status_label, ok, msg))
        self._comm_test_workers[instrument] = worker
        worker.start()

    def _on_comm_test_result(self, status_label: QLabel, ok: bool, message: str) -> None:
        if ok:
            status_label.setStyleSheet("color: green;")
            status_label.setText(f"OK — {message}")
        else:
            status_label.setStyleSheet("color: red;")
            status_label.setText(f"Falhou — {message}")
