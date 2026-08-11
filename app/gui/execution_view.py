from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import AUTOMATED_STANDARDS, STANDARDS
from app.core import planner, templates
from app.core.standards import (
    BURST_LEVELS,
    BURST_SPIKE_FREQUENCIES_HZ,
    DIPS_LEVELS,
    DIPS_PHASE_ANGLES_DEG,
    DIPS_SHORT_INTERRUPTION_MS,
    SURGE_COUPLINGS,
    SURGE_LEVELS,
    SURGE_PHASE_ANGLES_DEG,
)
from app.core.test_session import TestSessionWorker, set_session_result
from app.instruments.factory import build_driver_for_standard


def _checkable_list(values: list[str]) -> QListWidget:
    widget = QListWidget()
    widget.setMaximumHeight(90)
    for value in values:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        widget.addItem(item)
    return widget


def _checked_values(widget: QListWidget) -> list[str]:
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    ]


def _set_checked_values(widget: QListWidget, values: list[str]) -> None:
    """Marca os itens existentes que estão em `values` e adiciona os que faltarem
    (necessário para restaurar ângulos personalizados salvos em um template)."""
    values_set = set(values)
    existing = set()
    for i in range(widget.count()):
        item = widget.item(i)
        existing.add(item.text())
        item.setCheckState(
            Qt.CheckState.Checked if item.text() in values_set else Qt.CheckState.Unchecked
        )
    for value in values_set - existing:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        widget.addItem(item)


class ExecutionView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: TestSessionWorker | None = None
        self.template_combos: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.project_combo = QComboBox()
        form.addRow("Projeto:", self.project_combo)

        self.standard_combo = QComboBox()
        for code in AUTOMATED_STANDARDS:
            self.standard_combo.addItem(f"{code} — {STANDARDS[code]}", code)
        self.standard_combo.currentIndexChanged.connect(self._on_standard_changed)
        form.addRow("Norma:", self.standard_combo)

        self.eut_name_edit = QLineEdit()
        form.addRow("EUT (nome/modelo):", self.eut_name_edit)
        self.eut_serial_edit = QLineEdit()
        form.addRow("Número de série:", self.eut_serial_edit)
        self.operator_edit = QLineEdit()
        form.addRow("Operador:", self.operator_edit)
        layout.addLayout(form)

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_burst_page())
        self.params_stack.addWidget(self._build_surge_page())
        self.params_stack.addWidget(self._build_dips_page())
        layout.addWidget(self.params_stack)

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("Iniciar ensaio")
        self.start_btn.clicked.connect(self._start_test)
        button_row.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Parar")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_test)
        button_row.addWidget(self.stop_btn)
        layout.addLayout(button_row)

        layout.addWidget(QLabel("Log do ensaio:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.refresh_projects()

    # ---- templates (roteiros salvos) ----

    def _add_template_controls(self, form: QFormLayout, standard_code: str) -> None:
        row = QHBoxLayout()
        combo = QComboBox()
        row.addWidget(combo, 1)
        load_btn = QPushButton("Carregar")
        load_btn.clicked.connect(lambda: self._load_template(standard_code))
        row.addWidget(load_btn)
        save_btn = QPushButton("Salvar como template...")
        save_btn.clicked.connect(lambda: self._save_template(standard_code))
        row.addWidget(save_btn)
        delete_btn = QPushButton("Excluir")
        delete_btn.clicked.connect(lambda: self._delete_template(standard_code))
        row.addWidget(delete_btn)
        form.addRow("Template:", row)
        self.template_combos[standard_code] = combo
        self._refresh_templates(standard_code)

    def _refresh_templates(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        combo.blockSignals(True)
        combo.clear()
        for tpl in templates.list_templates(standard_code):
            combo.addItem(tpl["name"], tpl)
        combo.blockSignals(False)

    def _save_template(self, standard_code: str) -> None:
        try:
            params, level_label = self._collect_params(standard_code)
        except ValueError as exc:
            QMessageBox.warning(self, "Template", str(exc))
            return
        name, ok = QInputDialog.getText(self, "Salvar template", "Nome do roteiro:")
        if not ok or not name.strip():
            return
        templates.save_template(standard_code, name.strip(), level_label, params)
        self._refresh_templates(standard_code)

    def _load_template(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        tpl = combo.currentData()
        if tpl is None:
            QMessageBox.information(self, "Template", "Nenhum template salvo para esta norma.")
            return
        self._apply_params(standard_code, tpl["params"])

    def _delete_template(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        tpl = combo.currentData()
        if tpl is None:
            return
        confirm = QMessageBox.question(
            self, "Excluir template", f"Excluir o template '{tpl['name']}'?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        templates.delete_template(tpl["id"])
        self._refresh_templates(standard_code)

    # ---- páginas de parâmetros por norma ----

    def _build_burst_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        preset_row = QHBoxLayout()
        self.burst_preset_combo = QComboBox()
        for level in BURST_LEVELS:
            self.burst_preset_combo.addItem(f"Nível {level.level} — {level.voltage} V", level.voltage)
        apply_preset_btn = QPushButton("Aplicar")
        apply_preset_btn.clicked.connect(
            lambda: self.burst_voltage_spin.setValue(self.burst_preset_combo.currentData())
        )
        preset_row.addWidget(self.burst_preset_combo, 1)
        preset_row.addWidget(apply_preset_btn)
        form.addRow("Nível padrão (IEC 61000-4-4):", preset_row)

        self.burst_voltage_spin = QDoubleSpinBox()
        self.burst_voltage_spin.setRange(0, 6000)
        self.burst_voltage_spin.setSuffix(" V")
        self.burst_voltage_spin.setValue(BURST_LEVELS[0].voltage)
        form.addRow("Tensão (editável — roteiro manual):", self.burst_voltage_spin)

        self.burst_freq_combo = QComboBox()
        for freq in BURST_SPIKE_FREQUENCIES_HZ:
            self.burst_freq_combo.addItem(f"{freq / 1000:.0f} kHz", freq)
        form.addRow("Frequência de repetição:", self.burst_freq_combo)

        self.burst_coupling_combo = QComboBox()
        self.burst_coupling_combo.addItems(["COM", "ALL", "CCC"])
        form.addRow("Acoplamento:", self.burst_coupling_combo)

        self.burst_polarity_list = _checkable_list(["+", "-"])
        form.addRow("Polaridades:", self.burst_polarity_list)

        self._add_template_controls(form, "4-4")
        return page

    def _build_surge_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        preset_row = QHBoxLayout()
        self.surge_preset_combo = QComboBox()
        for level in SURGE_LEVELS:
            self.surge_preset_combo.addItem(f"Nível {level.level} — {level.voltage} V", level.voltage)
        apply_preset_btn = QPushButton("Aplicar")
        apply_preset_btn.clicked.connect(
            lambda: self.surge_voltage_spin.setValue(self.surge_preset_combo.currentData())
        )
        preset_row.addWidget(self.surge_preset_combo, 1)
        preset_row.addWidget(apply_preset_btn)
        form.addRow("Nível padrão (IEC 61000-4-5):", preset_row)

        self.surge_voltage_spin = QDoubleSpinBox()
        self.surge_voltage_spin.setRange(0, 7000)
        self.surge_voltage_spin.setSuffix(" V")
        self.surge_voltage_spin.setValue(SURGE_LEVELS[0].voltage)
        form.addRow("Tensão (editável — roteiro manual):", self.surge_voltage_spin)

        self.surge_coupling_combo = QComboBox()
        self.surge_coupling_combo.addItems(list(SURGE_COUPLINGS))
        form.addRow("Acoplamento:", self.surge_coupling_combo)

        self.surge_polarity_list = _checkable_list(["+", "-"])
        form.addRow("Polaridades:", self.surge_polarity_list)

        self.surge_phase_list = _checkable_list([str(a) for a in SURGE_PHASE_ANGLES_DEG])
        form.addRow("Ângulos de fase (°):", self.surge_phase_list)

        custom_angle_row = QHBoxLayout()
        self.surge_custom_angle_spin = QSpinBox()
        self.surge_custom_angle_spin.setRange(0, 359)
        add_angle_btn = QPushButton("Adicionar ângulo")
        add_angle_btn.clicked.connect(self._add_custom_surge_angle)
        custom_angle_row.addWidget(self.surge_custom_angle_spin)
        custom_angle_row.addWidget(add_angle_btn)
        form.addRow("Ângulo personalizado:", custom_angle_row)

        self._add_template_controls(form, "4-5")
        return page

    def _add_custom_surge_angle(self) -> None:
        value = str(self.surge_custom_angle_spin.value())
        existing = [
            self.surge_phase_list.item(i).text() for i in range(self.surge_phase_list.count())
        ]
        if value in existing:
            return
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        self.surge_phase_list.addItem(item)

    def _build_dips_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.dips_nominal_spin = QDoubleSpinBox()
        self.dips_nominal_spin.setRange(1, 300)
        self.dips_nominal_spin.setValue(230)
        self.dips_nominal_spin.setSuffix(" V")
        form.addRow("Tensão nominal (Un):", self.dips_nominal_spin)

        self.dips_freq_spin = QDoubleSpinBox()
        self.dips_freq_spin.setRange(15, 1000)
        self.dips_freq_spin.setValue(50)
        self.dips_freq_spin.setSuffix(" Hz")
        form.addRow("Frequência:", self.dips_freq_spin)

        self.dips_phase_list = _checkable_list([str(a) for a in DIPS_PHASE_ANGLES_DEG])
        form.addRow("Ângulos de fase (°):", self.dips_phase_list)
        layout.addLayout(form)

        layout.addWidget(QLabel("Roteiro de eventos (dips/interrupções) — editável, na ordem de execução:"))
        self.dips_events_table = QTableWidget(0, 2)
        self.dips_events_table.setHorizontalHeaderLabels(["% Un (0 = interrupção)", "Duração (ms)"])
        self.dips_events_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.dips_events_table)

        preset_row = QHBoxLayout()
        self.dips_preset_combo = QComboBox()
        for level in DIPS_LEVELS:
            self.dips_preset_combo.addItem(
                f"Nível {level.level} — {level.percent_un}% Un, {level.duration_ms:.0f} ms",
                (level.percent_un, level.duration_ms),
            )
        self.dips_preset_combo.addItem(
            f"Interrupção curta — {DIPS_SHORT_INTERRUPTION_MS:.0f} ms",
            (0, DIPS_SHORT_INTERRUPTION_MS),
        )
        add_preset_btn = QPushButton("Adicionar nível padrão ao roteiro")
        add_preset_btn.clicked.connect(self._add_dips_preset_event)
        preset_row.addWidget(self.dips_preset_combo, 1)
        preset_row.addWidget(add_preset_btn)
        layout.addLayout(preset_row)

        events_btn_row = QHBoxLayout()
        add_row_btn = QPushButton("Adicionar linha em branco")
        add_row_btn.clicked.connect(self._add_dips_blank_event)
        remove_row_btn = QPushButton("Remover linha selecionada")
        remove_row_btn.clicked.connect(self._remove_dips_event)
        events_btn_row.addWidget(add_row_btn)
        events_btn_row.addWidget(remove_row_btn)
        layout.addLayout(events_btn_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-11")
        layout.addLayout(template_form)

        self._add_dips_preset_event()
        return page

    def _add_dips_preset_event(self) -> None:
        percent_un, duration_ms = self.dips_preset_combo.currentData()
        self._append_dips_row(percent_un, duration_ms)

    def _add_dips_blank_event(self) -> None:
        self._append_dips_row(40, 200.0)

    def _append_dips_row(self, percent_un: float, duration_ms: float) -> None:
        row = self.dips_events_table.rowCount()
        self.dips_events_table.insertRow(row)
        self.dips_events_table.setItem(row, 0, QTableWidgetItem(str(percent_un)))
        self.dips_events_table.setItem(row, 1, QTableWidgetItem(str(duration_ms)))

    def _remove_dips_event(self) -> None:
        row = self.dips_events_table.currentRow()
        if row >= 0:
            self.dips_events_table.removeRow(row)

    def _on_standard_changed(self, index: int) -> None:
        self.params_stack.setCurrentIndex(index)

    # ---- projeto ----

    def refresh_projects(self) -> None:
        current = self.project_combo.currentData()
        self.project_combo.clear()
        for project in planner.list_projects():
            self.project_combo.addItem(project["name"], project["id"])
        if current is not None:
            index = self.project_combo.findData(current)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    def preselect(self, project_id: int, standard_code: str) -> None:
        self.refresh_projects()
        p_index = self.project_combo.findData(project_id)
        if p_index >= 0:
            self.project_combo.setCurrentIndex(p_index)
        s_index = self.standard_combo.findData(standard_code)
        if s_index >= 0:
            self.standard_combo.setCurrentIndex(s_index)

    # ---- montagem / restauração de parâmetros ----

    def _collect_params(self, standard_code: str) -> tuple[dict, str]:
        if standard_code == "4-4":
            voltage = self.burst_voltage_spin.value()
            freq = self.burst_freq_combo.currentData()
            params = {
                "voltage": voltage,
                "frequency_hz": freq,
                "coupling": self.burst_coupling_combo.currentText(),
                "polarities": _checked_values(self.burst_polarity_list),
            }
            label = f"{voltage:.0f} V, {freq / 1000:.0f} kHz, {params['coupling']}"
            return params, label

        if standard_code == "4-5":
            voltage = self.surge_voltage_spin.value()
            params = {
                "voltage": voltage,
                "coupling": self.surge_coupling_combo.currentText(),
                "polarities": _checked_values(self.surge_polarity_list),
                "phase_angles": [int(a) for a in _checked_values(self.surge_phase_list)],
            }
            label = f"{voltage:.0f} V, {params['coupling']}"
            return params, label

        if standard_code == "4-11":
            nominal = self.dips_nominal_spin.value()
            events = []
            for row in range(self.dips_events_table.rowCount()):
                percent_item = self.dips_events_table.item(row, 0)
                duration_item = self.dips_events_table.item(row, 1)
                if percent_item is None or duration_item is None:
                    continue
                percent_un = float(percent_item.text())
                duration_ms = float(duration_item.text())
                if percent_un <= 0:
                    events.append({"interruption": True, "duration_ms": duration_ms})
                else:
                    events.append({"percent_un": percent_un, "duration_ms": duration_ms})
            if not events:
                raise ValueError("Adicione ao menos um evento ao roteiro de dips antes de continuar.")
            params = {
                "nominal_voltage": nominal,
                "frequency_hz": self.dips_freq_spin.value(),
                "phase_angles": [int(a) for a in _checked_values(self.dips_phase_list)],
                "events": events,
            }
            label = f"Roteiro com {len(events)} evento(s), Un={nominal:.0f} V"
            return params, label

        raise ValueError(standard_code)

    def _apply_params(self, standard_code: str, params: dict) -> None:
        if standard_code == "4-4":
            self.burst_voltage_spin.setValue(params["voltage"])
            freq_index = self.burst_freq_combo.findData(params["frequency_hz"])
            if freq_index >= 0:
                self.burst_freq_combo.setCurrentIndex(freq_index)
            coupling_index = self.burst_coupling_combo.findText(params["coupling"])
            if coupling_index >= 0:
                self.burst_coupling_combo.setCurrentIndex(coupling_index)
            _set_checked_values(self.burst_polarity_list, params["polarities"])

        elif standard_code == "4-5":
            self.surge_voltage_spin.setValue(params["voltage"])
            coupling_index = self.surge_coupling_combo.findText(params["coupling"])
            if coupling_index >= 0:
                self.surge_coupling_combo.setCurrentIndex(coupling_index)
            _set_checked_values(self.surge_polarity_list, params["polarities"])
            _set_checked_values(
                self.surge_phase_list, [str(a) for a in params["phase_angles"]]
            )

        elif standard_code == "4-11":
            self.dips_nominal_spin.setValue(params["nominal_voltage"])
            self.dips_freq_spin.setValue(params["frequency_hz"])
            _set_checked_values(self.dips_phase_list, [str(a) for a in params["phase_angles"]])
            self.dips_events_table.setRowCount(0)
            for event in params["events"]:
                if event.get("interruption"):
                    self._append_dips_row(0, event["duration_ms"])
                else:
                    self._append_dips_row(event["percent_un"], event["duration_ms"])

    # ---- execução ----

    def _start_test(self) -> None:
        project_id = self.project_combo.currentData()
        if project_id is None:
            QMessageBox.warning(self, "Ensaio", "Selecione um projeto antes de iniciar.")
            return
        standard_code = self.standard_combo.currentData()
        try:
            params, level_label = self._collect_params(standard_code)
        except ValueError as exc:
            QMessageBox.warning(self, "Ensaio", str(exc))
            return
        if not self.eut_name_edit.text().strip():
            QMessageBox.warning(self, "Ensaio", "Informe o EUT antes de iniciar.")
            return

        driver = build_driver_for_standard(standard_code)
        self.worker = TestSessionWorker(
            driver=driver,
            project_id=project_id,
            standard_code=standard_code,
            eut_name=self.eut_name_edit.text().strip(),
            eut_serial=self.eut_serial_edit.text().strip(),
            operator=self.operator_edit.text().strip(),
            level_label=level_label,
            params=params,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_session.connect(self._on_finished)
        self.log_view.clear()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.worker.start()

    def _stop_test(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()

    def _on_progress(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _on_finished(self, session_id: int) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_view.appendPlainText("--- Ensaio finalizado ---")

        result, ok = QInputDialog.getItem(
            self, "Resultado do ensaio", "Resultado:", ["aprovado", "reprovado"], 0, False
        )
        if ok:
            set_session_result(session_id, result)

        project_id = self.project_combo.currentData()
        standard_code = self.standard_combo.currentData()
        item = planner.find_item(project_id, standard_code)
        if item is not None:
            planner.link_item_session(item["id"], session_id)
