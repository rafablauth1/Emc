from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core import command_overrides
from app.core.comm_test import CommTestWorker
from app.core.counter_session import RecallWorker
from app.core.runtime_settings import settings
from app.instruments import ucs500n_commands as ucs_cmd
from app.instruments.factory import (
    build_agilent_counter_driver,
    build_chroma_driver,
    build_ucs500n_driver,
)

UCS500N_COMMAND_FIELDS = [
    ("SELECT_BURST_MENU", "Selecionar menu Burst"),
    ("SELECT_SURGE_MENU", "Selecionar menu Surge"),
    ("TEST_ON", "TEST ON (ligar saída)"),
    ("TEST_OFF", "TEST OFF (desligar saída)"),
    ("SET_BURST_VOLTAGE", "Burst — tensão (use {voltage})"),
    ("SET_BURST_FREQUENCY", "Burst — frequência (use {frequency_hz})"),
    ("SET_BURST_COUPLING", "Burst — acoplamento (use {coupling})"),
    ("SET_BURST_POLARITY", "Burst — polaridade (use {polarity})"),
    ("SET_SURGE_VOLTAGE", "Surge — tensão (use {voltage})"),
    ("SET_SURGE_PHASE_ANGLE", "Surge — ângulo (use {angle_deg})"),
    ("SET_SURGE_COUPLING", "Surge — acoplamento (use {coupling})"),
    ("SET_SURGE_POLARITY", "Surge — polaridade (use {polarity})"),
    ("TRIGGER_SINGLE_EVENT", "Disparar pulso único"),
    ("STOP_TEST", "Parar ensaio"),
    ("QUERY_STATUS", "Consultar status"),
]


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._comm_test_workers: dict[str, CommTestWorker] = {}
        self._terminal_driver = None
        self._recall_worker: RecallWorker | None = None
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

        self.counter_connection_combo = QComboBox()
        self.counter_connection_combo.addItem("GPIB", "gpib")
        self.counter_connection_combo.addItem("Serial (RS-232)", "serial")
        index = self.counter_connection_combo.findData(settings.counter_connection)
        if index >= 0:
            self.counter_connection_combo.setCurrentIndex(index)
        self.counter_connection_combo.currentIndexChanged.connect(self._on_counter_connection_changed)
        form.addRow("Conexão — Contador Agilent 53131A:", self.counter_connection_combo)

        self.counter_board_spin = QSpinBox()
        self.counter_board_spin.setRange(0, 15)
        self.counter_board_spin.setValue(settings.gpib_boards["agilent_53131a"])
        self.counter_board_spin.valueChanged.connect(
            lambda v: settings.gpib_boards.__setitem__("agilent_53131a", v)
        )
        form.addRow("Placa GPIB — Contador Agilent 53131A:", self.counter_board_spin)
        self._counter_board_label = form.labelForField(self.counter_board_spin)

        self.counter_addr_spin = QSpinBox()
        self.counter_addr_spin.setRange(0, 30)
        self.counter_addr_spin.setValue(settings.gpib_addresses["agilent_53131a"])
        self.counter_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("agilent_53131a", v)
        )
        form.addRow("Endereço GPIB — Contador Agilent 53131A:", self.counter_addr_spin)
        self._counter_addr_label = form.labelForField(self.counter_addr_spin)

        self.counter_serial_spin = QSpinBox()
        self.counter_serial_spin.setRange(1, 99)
        self.counter_serial_spin.setPrefix("COM")
        self.counter_serial_spin.setValue(settings.serial_ports["agilent_53131a"])
        self.counter_serial_spin.valueChanged.connect(
            lambda v: settings.serial_ports.__setitem__("agilent_53131a", v)
        )
        form.addRow("Porta serial — Contador Agilent 53131A:", self.counter_serial_spin)
        self._counter_serial_label = form.labelForField(self.counter_serial_spin)

        layout.addLayout(form)
        self._on_counter_connection_changed(self.counter_connection_combo.currentIndex())

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

        counter_test_row = QHBoxLayout()
        counter_test_btn = QPushButton("Testar comunicação — Contador Agilent 53131A")
        counter_test_btn.clicked.connect(
            lambda: self._test_comm("agilent_53131a", build_agilent_counter_driver)
        )
        self.counter_test_status = QLabel("")
        counter_test_row.addWidget(counter_test_btn)
        counter_test_row.addWidget(self.counter_test_status, 1)
        layout.addLayout(counter_test_row)

        recall_row = QHBoxLayout()
        recall_row.addWidget(QLabel("Recall do contador (Save/Recall > Recall N no painel):"))
        self.recall_register_spin = QSpinBox()
        self.recall_register_spin.setRange(0, 20)
        self.recall_register_spin.setValue(1)
        recall_row.addWidget(self.recall_register_spin)
        recall_btn = QPushButton("Carregar Recall")
        recall_btn.clicked.connect(self._load_recall)
        recall_row.addWidget(recall_btn)
        self.recall_status = QLabel("")
        recall_row.addWidget(self.recall_status, 1)
        layout.addLayout(recall_row)

        layout.addWidget(
            QLabel(
                "Terminal GPIB (comando bruto) — pra descobrir/testar os comandos reais de um "
                "instrumento na mão, digitando direto (ex: enquanto não se tem o dicionário de "
                "comandos do UCS 500N)."
            )
        )
        terminal_top_row = QHBoxLayout()
        self.terminal_instrument_combo = QComboBox()
        self.terminal_instrument_combo.addItem("EM TEST UCS 500N", "ucs500n")
        self.terminal_instrument_combo.addItem("Chroma 61501/61504", "chroma")
        self.terminal_instrument_combo.addItem("Contador Agilent 53131A", "agilent_53131a")
        terminal_top_row.addWidget(self.terminal_instrument_combo)
        self.terminal_connect_btn = QPushButton("Conectar")
        self.terminal_connect_btn.setCheckable(True)
        self.terminal_connect_btn.toggled.connect(self._toggle_terminal_connection)
        terminal_top_row.addWidget(self.terminal_connect_btn)
        terminal_top_row.addStretch(1)
        layout.addLayout(terminal_top_row)

        self.terminal_log = QPlainTextEdit()
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setMaximumHeight(160)
        layout.addWidget(self.terminal_log)

        terminal_input_row = QHBoxLayout()
        self.terminal_command_edit = QLineEdit()
        self.terminal_command_edit.setPlaceholderText(
            "Digite um comando (ex: *IDN?, TEST ON, OUTP ON...) e Enter consulta"
        )
        self.terminal_command_edit.returnPressed.connect(self._terminal_query)
        terminal_input_row.addWidget(self.terminal_command_edit, 1)
        terminal_write_btn = QPushButton("Enviar (write)")
        terminal_write_btn.clicked.connect(self._terminal_write)
        terminal_input_row.addWidget(terminal_write_btn)
        terminal_query_btn = QPushButton("Consultar (query)")
        terminal_query_btn.clicked.connect(self._terminal_query)
        terminal_input_row.addWidget(terminal_query_btn)
        layout.addLayout(terminal_input_row)

        layout.addWidget(
            QLabel(
                "Comandos do UCS 500N (editável) — o dicionário de comandos oficial do "
                "fabricante não é público, então os valores abaixo são tentativas, não "
                "confirmados. Descubra os certos testando no Terminal GPIB acima e cole "
                "aqui embaixo; \"Salvar comandos\" já vale pro próximo TEST ON e pros "
                "próximos ensaios de burst/surge, sem precisar reiniciar o app."
            )
        )
        cmd_form = QFormLayout()
        self.ucs_command_edits: dict[str, QLineEdit] = {}
        overrides = command_overrides.load_overrides()
        for key, label in UCS500N_COMMAND_FIELDS:
            edit = QLineEdit(overrides.get(key, getattr(ucs_cmd, key)))
            cmd_form.addRow(f"{label}:", edit)
            self.ucs_command_edits[key] = edit
        layout.addLayout(cmd_form)

        cmd_btn_row = QHBoxLayout()
        save_cmd_btn = QPushButton("Salvar comandos")
        save_cmd_btn.clicked.connect(self._save_ucs_commands)
        cmd_btn_row.addWidget(save_cmd_btn)
        restore_cmd_btn = QPushButton("Restaurar tentativas padrão")
        restore_cmd_btn.clicked.connect(self._restore_ucs_commands)
        cmd_btn_row.addWidget(restore_cmd_btn)
        self.ucs_command_status = QLabel("")
        cmd_btn_row.addWidget(self.ucs_command_status, 1)
        layout.addLayout(cmd_btn_row)

        layout.addStretch()

    def _on_sim_toggled(self, checked: bool) -> None:
        settings.simulation_mode = checked

    def _on_buzzer_toggled(self, checked: bool) -> None:
        settings.buzzer_enabled = checked

    def _on_counter_connection_changed(self, _index: int) -> None:
        connection = self.counter_connection_combo.currentData()
        settings.counter_connection = connection
        is_serial = connection == "serial"
        self.counter_board_spin.setVisible(not is_serial)
        self._counter_board_label.setVisible(not is_serial)
        self.counter_addr_spin.setVisible(not is_serial)
        self._counter_addr_label.setVisible(not is_serial)
        self.counter_serial_spin.setVisible(is_serial)
        self._counter_serial_label.setVisible(is_serial)

    def _test_comm(self, instrument: str, driver_factory) -> None:
        status_labels = {
            "ucs500n": self.ucs_test_status,
            "chroma": self.chroma_test_status,
            "agilent_53131a": self.counter_test_status,
        }
        status_label = status_labels[instrument]
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

    # ---- recall do contador Agilent 53131A ----

    def _load_recall(self) -> None:
        self.recall_status.setStyleSheet("")
        self.recall_status.setText("Carregando...")
        counter = build_agilent_counter_driver()
        worker = RecallWorker(counter, self.recall_register_spin.value(), self)
        worker.result.connect(self._on_recall_result)
        self._recall_worker = worker
        worker.start()

    def _on_recall_result(self, ok: bool, message: str) -> None:
        self._recall_worker = None
        if ok:
            self.recall_status.setStyleSheet("color: green;")
            self.recall_status.setText(message)
        else:
            self.recall_status.setStyleSheet("color: red;")
            self.recall_status.setText(f"Falhou — {message}")

    # ---- terminal GPIB (comando bruto) ----

    def _terminal_log_line(self, text: str) -> None:
        self.terminal_log.appendPlainText(text)

    def _toggle_terminal_connection(self, checked: bool) -> None:
        if checked:
            instrument = self.terminal_instrument_combo.currentData()
            factories = {
                "ucs500n": build_ucs500n_driver,
                "chroma": build_chroma_driver,
                "agilent_53131a": build_agilent_counter_driver,
            }
            factory = factories[instrument]
            try:
                driver = factory()
                driver.connect()
                self._terminal_driver = driver
                self.terminal_connect_btn.setText("Desconectar")
                self.terminal_instrument_combo.setEnabled(False)
                self._terminal_log_line(
                    f"-- conectado ({self.terminal_instrument_combo.currentText()}) --"
                )
            except Exception as exc:
                self._terminal_log_line(f"-- erro ao conectar: {exc} --")
                self.terminal_connect_btn.blockSignals(True)
                self.terminal_connect_btn.setChecked(False)
                self.terminal_connect_btn.blockSignals(False)
        else:
            if self._terminal_driver is not None:
                try:
                    self._terminal_driver.disconnect()
                except Exception:
                    pass
                self._terminal_driver = None
            self.terminal_connect_btn.setText("Conectar")
            self.terminal_instrument_combo.setEnabled(True)
            self._terminal_log_line("-- desconectado --")

    def _terminal_write(self) -> None:
        command = self.terminal_command_edit.text().strip()
        if not command:
            return
        if self._terminal_driver is None:
            self._terminal_log_line("-- conecte antes de enviar um comando --")
            return
        try:
            self._terminal_driver.write(command)
            self._terminal_log_line(f"> {command}")
        except Exception as exc:
            self._terminal_log_line(f"-- erro: {exc} --")

    def _terminal_query(self) -> None:
        command = self.terminal_command_edit.text().strip()
        if not command:
            return
        if self._terminal_driver is None:
            self._terminal_log_line("-- conecte antes de consultar um comando --")
            return
        try:
            response = self._terminal_driver.query(command)
            self._terminal_log_line(f"> {command}")
            self._terminal_log_line(f"< {response}")
        except Exception as exc:
            self._terminal_log_line(f"-- erro: {exc} --")

    # ---- comandos do UCS 500N (sobrescrita salva em disco) ----

    def _save_ucs_commands(self) -> None:
        overrides = {key: edit.text() for key, edit in self.ucs_command_edits.items()}
        command_overrides.save_overrides(overrides)
        self.ucs_command_status.setStyleSheet("color: green;")
        self.ucs_command_status.setText(
            "Salvo — já vale para o próximo TEST ON e para o próximo ensaio."
        )

    def _restore_ucs_commands(self) -> None:
        for key, edit in self.ucs_command_edits.items():
            edit.setText(getattr(ucs_cmd, key))
        self.ucs_command_status.setStyleSheet("")
        self.ucs_command_status.setText("Restaurado para as tentativas padrão (não salvo ainda).")
