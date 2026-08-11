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
from app.core.legacy_routines import burst_params_to_points, surge_params_to_points
from app.core.standards import (
    BURST_DEFAULT_DURATION_S,
    BURST_LEVELS,
    BURST_POLARITIES,
    BURST_SPIKE_FREQUENCIES_HZ,
    DIPS_LEVELS,
    DIPS_PHASE_ANGLES_DEG,
    DIPS_SHORT_INTERRUPTION_MS,
    SURGE_COUPLINGS,
    SURGE_DEFAULT_INTERVAL_S,
    SURGE_DEFAULT_PULSE_COUNT,
    SURGE_LEVELS,
    SURGE_POLARITIES,
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
        new_btn = QPushButton("Novo roteiro em branco")
        new_btn.clicked.connect(lambda: self._new_routine(standard_code))
        row.addWidget(new_btn)
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

    def _new_routine(self, standard_code: str) -> None:
        """Limpa o formulário da norma para valores padrão, pronto para montar um roteiro novo do zero."""
        combo = self.template_combos.get(standard_code)
        if combo is not None:
            combo.setCurrentIndex(-1)

        if standard_code == "4-4":
            self.burst_voltage_spin.setValue(BURST_LEVELS[0].voltage)
            self.burst_freq_combo.setCurrentIndex(0)
            self.burst_coupling_combo.setCurrentIndex(0)
            self.burst_polarity_combo.setCurrentIndex(0)
            self.burst_duration_spin.setValue(BURST_DEFAULT_DURATION_S)
            self.burst_points_table.setRowCount(0)
            self._add_burst_point()
        elif standard_code == "4-5":
            self.surge_voltage_spin.setValue(SURGE_LEVELS[0].voltage)
            self.surge_coupling_combo.setCurrentIndex(0)
            self.surge_polarity_combo.setCurrentIndex(0)
            self.surge_angle_spin.setValue(0)
            self.surge_pulse_count_spin.setValue(SURGE_DEFAULT_PULSE_COUNT)
            self.surge_interval_spin.setValue(SURGE_DEFAULT_INTERVAL_S)
            self.surge_points_table.setRowCount(0)
            self._add_surge_point()
        elif standard_code == "4-11":
            self.dips_nominal_spin.setValue(230)
            self.dips_freq_spin.setValue(50)
            _set_checked_values(self.dips_phase_list, [str(a) for a in DIPS_PHASE_ANGLES_DEG])
            self.dips_events_table.setRowCount(0)
            self._add_dips_preset_event()

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

    # ---- utilitários genéricos de tabela (navegar/sequenciar pontos) ----

    def _move_table_row(self, table: QTableWidget, delta: int) -> None:
        row = table.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= table.rowCount():
            return
        for col in range(table.columnCount()):
            item_a = table.takeItem(row, col)
            item_b = table.takeItem(new_row, col)
            table.setItem(row, col, item_b)
            table.setItem(new_row, col, item_a)
        table.setCurrentCell(new_row, 0)

    def _remove_table_row(self, table: QTableWidget) -> None:
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    def _add_sequence_buttons(self, layout: QVBoxLayout, table: QTableWidget, add_callback) -> None:
        row = QHBoxLayout()
        add_btn = QPushButton("Adicionar ponto com os valores acima")
        add_btn.clicked.connect(add_callback)
        remove_btn = QPushButton("Remover ponto selecionado")
        remove_btn.clicked.connect(lambda: self._remove_table_row(table))
        up_btn = QPushButton("▲ Mover para cima")
        up_btn.clicked.connect(lambda: self._move_table_row(table, -1))
        down_btn = QPushButton("▼ Mover para baixo")
        down_btn.clicked.connect(lambda: self._move_table_row(table, 1))
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addWidget(up_btn)
        row.addWidget(down_btn)
        layout.addLayout(row)

    # ---- páginas de parâmetros por norma ----

    def _build_burst_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
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
        form.addRow("Tensão do próximo ponto:", self.burst_voltage_spin)

        self.burst_freq_combo = QComboBox()
        for freq in BURST_SPIKE_FREQUENCIES_HZ:
            self.burst_freq_combo.addItem(f"{freq / 1000:.0f} kHz", freq)
        form.addRow("Frequência de repetição:", self.burst_freq_combo)

        self.burst_coupling_combo = QComboBox()
        self.burst_coupling_combo.addItems(["COM", "ALL", "CCC"])
        form.addRow("Acoplamento:", self.burst_coupling_combo)

        self.burst_polarity_combo = QComboBox()
        self.burst_polarity_combo.addItems(list(BURST_POLARITIES))
        form.addRow("Polaridade:", self.burst_polarity_combo)

        self.burst_duration_spin = QDoubleSpinBox()
        self.burst_duration_spin.setRange(0.1, 600)
        self.burst_duration_spin.setSuffix(" s")
        self.burst_duration_spin.setValue(BURST_DEFAULT_DURATION_S)
        form.addRow("Duração deste ponto:", self.burst_duration_spin)
        layout.addLayout(form)

        layout.addWidget(
            QLabel(
                "Roteiro de burst — sequência de pontos (tensão/freq/acoplamento/polaridade/duração), "
                "executados na ordem da tabela. Use os botões abaixo para adicionar, remover e reordenar."
            )
        )
        self.burst_points_table = QTableWidget(0, 5)
        self.burst_points_table.setHorizontalHeaderLabels(
            ["Tensão (V)", "Frequência (Hz)", "Acoplamento", "Polaridade", "Duração (s)"]
        )
        self.burst_points_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.burst_points_table)
        self._add_sequence_buttons(layout, self.burst_points_table, self._add_burst_point)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-4")
        layout.addLayout(template_form)

        self._add_burst_point()
        return page

    def _add_burst_point(self) -> None:
        self._append_burst_row(
            self.burst_voltage_spin.value(),
            self.burst_freq_combo.currentData(),
            self.burst_coupling_combo.currentText(),
            self.burst_polarity_combo.currentText(),
            self.burst_duration_spin.value(),
        )

    def _append_burst_row(self, voltage, frequency_hz, coupling, polarity, duration_s) -> None:
        row = self.burst_points_table.rowCount()
        self.burst_points_table.insertRow(row)
        self.burst_points_table.setItem(row, 0, QTableWidgetItem(str(voltage)))
        self.burst_points_table.setItem(row, 1, QTableWidgetItem(str(frequency_hz)))
        self.burst_points_table.setItem(row, 2, QTableWidgetItem(str(coupling)))
        self.burst_points_table.setItem(row, 3, QTableWidgetItem(str(polarity)))
        self.burst_points_table.setItem(row, 4, QTableWidgetItem(str(duration_s)))

    def _build_surge_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
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
        form.addRow("Tensão do próximo ponto:", self.surge_voltage_spin)

        self.surge_coupling_combo = QComboBox()
        self.surge_coupling_combo.addItems(list(SURGE_COUPLINGS))
        form.addRow("Acoplamento:", self.surge_coupling_combo)

        self.surge_polarity_combo = QComboBox()
        self.surge_polarity_combo.addItems(list(SURGE_POLARITIES))
        form.addRow("Polaridade:", self.surge_polarity_combo)

        self.surge_angle_spin = QSpinBox()
        self.surge_angle_spin.setRange(0, 359)
        form.addRow("Ângulo de fase (°):", self.surge_angle_spin)

        self.surge_pulse_count_spin = QSpinBox()
        self.surge_pulse_count_spin.setRange(1, 100)
        self.surge_pulse_count_spin.setValue(SURGE_DEFAULT_PULSE_COUNT)
        form.addRow("Pulsos neste ponto:", self.surge_pulse_count_spin)

        self.surge_interval_spin = QDoubleSpinBox()
        self.surge_interval_spin.setRange(0, 600)
        self.surge_interval_spin.setSuffix(" s")
        self.surge_interval_spin.setValue(SURGE_DEFAULT_INTERVAL_S)
        form.addRow("Intervalo entre pulsos deste ponto:", self.surge_interval_spin)
        layout.addLayout(form)

        layout.addWidget(
            QLabel(
                "Roteiro de surge — sequência de pontos (tensão/acoplamento/polaridade/ângulo/pulsos), "
                "executados na ordem da tabela. Use os botões abaixo para adicionar, remover e reordenar."
            )
        )
        self.surge_points_table = QTableWidget(0, 6)
        self.surge_points_table.setHorizontalHeaderLabels(
            ["Tensão (V)", "Acoplamento", "Polaridade", "Ângulo (°)", "Pulsos", "Intervalo (s)"]
        )
        self.surge_points_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.surge_points_table)
        self._add_sequence_buttons(layout, self.surge_points_table, self._add_surge_point)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-5")
        layout.addLayout(template_form)

        self._add_surge_point()
        return page

    def _add_surge_point(self) -> None:
        self._append_surge_row(
            self.surge_voltage_spin.value(),
            self.surge_coupling_combo.currentText(),
            self.surge_polarity_combo.currentText(),
            self.surge_angle_spin.value(),
            self.surge_pulse_count_spin.value(),
            self.surge_interval_spin.value(),
        )

    def _append_surge_row(self, voltage, coupling, polarity, angle, pulse_count, interval_s) -> None:
        row = self.surge_points_table.rowCount()
        self.surge_points_table.insertRow(row)
        self.surge_points_table.setItem(row, 0, QTableWidgetItem(str(voltage)))
        self.surge_points_table.setItem(row, 1, QTableWidgetItem(str(coupling)))
        self.surge_points_table.setItem(row, 2, QTableWidgetItem(str(polarity)))
        self.surge_points_table.setItem(row, 3, QTableWidgetItem(str(angle)))
        self.surge_points_table.setItem(row, 4, QTableWidgetItem(str(pulse_count)))
        self.surge_points_table.setItem(row, 5, QTableWidgetItem(str(interval_s)))

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

        layout.addWidget(
            QLabel(
                "Roteiro de eventos (dips/interrupções) — editável, na ordem de execução.\n"
                "Ângulos em branco usam os ângulos marcados acima; para vários ângulos separe por vírgula (ex: 0,180)."
            )
        )
        self.dips_events_table = QTableWidget(0, 5)
        self.dips_events_table.setHorizontalHeaderLabels(
            ["% Un (0 = interrupção)", "Duração (ms)", "Repetições", "Ângulos (°)", "Intervalo entre repetições (ms)"]
        )
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
        remove_row_btn.clicked.connect(lambda: self._remove_table_row(self.dips_events_table))
        up_btn = QPushButton("▲ Mover para cima")
        up_btn.clicked.connect(lambda: self._move_table_row(self.dips_events_table, -1))
        down_btn = QPushButton("▼ Mover para baixo")
        down_btn.clicked.connect(lambda: self._move_table_row(self.dips_events_table, 1))
        events_btn_row.addWidget(add_row_btn)
        events_btn_row.addWidget(remove_row_btn)
        events_btn_row.addWidget(up_btn)
        events_btn_row.addWidget(down_btn)
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

    def _append_dips_row(
        self,
        percent_un: float,
        duration_ms: float,
        count: int = 1,
        phase_angles: str = "",
        interval_ms: str = "",
    ) -> None:
        row = self.dips_events_table.rowCount()
        self.dips_events_table.insertRow(row)
        self.dips_events_table.setItem(row, 0, QTableWidgetItem(str(percent_un)))
        self.dips_events_table.setItem(row, 1, QTableWidgetItem(str(duration_ms)))
        self.dips_events_table.setItem(row, 2, QTableWidgetItem(str(count)))
        self.dips_events_table.setItem(row, 3, QTableWidgetItem(phase_angles))
        self.dips_events_table.setItem(row, 4, QTableWidgetItem(interval_ms))

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
            points = []
            for row in range(self.burst_points_table.rowCount()):
                v_item = self.burst_points_table.item(row, 0)
                f_item = self.burst_points_table.item(row, 1)
                c_item = self.burst_points_table.item(row, 2)
                p_item = self.burst_points_table.item(row, 3)
                d_item = self.burst_points_table.item(row, 4)
                if v_item is None or not v_item.text().strip():
                    continue
                points.append(
                    {
                        "voltage": float(v_item.text()),
                        "frequency_hz": float(f_item.text()) if f_item and f_item.text().strip() else 5000,
                        "coupling": c_item.text().strip() if c_item and c_item.text().strip() else "COM",
                        "polarity": p_item.text().strip() if p_item and p_item.text().strip() else "+",
                        "duration_s": float(d_item.text()) if d_item and d_item.text().strip() else BURST_DEFAULT_DURATION_S,
                    }
                )
            if not points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de burst antes de continuar.")
            params = {"points": points}
            voltages = {p["voltage"] for p in points}
            voltage_desc = f"{points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = f"Roteiro com {len(points)} ponto(s), {voltage_desc}"
            return params, label

        if standard_code == "4-5":
            points = []
            for row in range(self.surge_points_table.rowCount()):
                v_item = self.surge_points_table.item(row, 0)
                c_item = self.surge_points_table.item(row, 1)
                p_item = self.surge_points_table.item(row, 2)
                a_item = self.surge_points_table.item(row, 3)
                n_item = self.surge_points_table.item(row, 4)
                i_item = self.surge_points_table.item(row, 5)
                if v_item is None or not v_item.text().strip():
                    continue
                points.append(
                    {
                        "voltage": float(v_item.text()),
                        "coupling": c_item.text().strip() if c_item and c_item.text().strip() else "L-N",
                        "polarity": p_item.text().strip() if p_item and p_item.text().strip() else "+",
                        "phase_angle": int(float(a_item.text())) if a_item and a_item.text().strip() else 0,
                        "pulse_count": int(n_item.text()) if n_item and n_item.text().strip() else SURGE_DEFAULT_PULSE_COUNT,
                        "interval_s": float(i_item.text()) if i_item and i_item.text().strip() else SURGE_DEFAULT_INTERVAL_S,
                    }
                )
            if not points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de surge antes de continuar.")
            params = {"points": points}
            voltages = {p["voltage"] for p in points}
            voltage_desc = f"{points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = f"Roteiro com {len(points)} ponto(s), {voltage_desc}"
            return params, label

        if standard_code == "4-11":
            nominal = self.dips_nominal_spin.value()
            events = []
            for row in range(self.dips_events_table.rowCount()):
                percent_item = self.dips_events_table.item(row, 0)
                duration_item = self.dips_events_table.item(row, 1)
                count_item = self.dips_events_table.item(row, 2)
                angles_item = self.dips_events_table.item(row, 3)
                interval_item = self.dips_events_table.item(row, 4)
                if percent_item is None or duration_item is None:
                    continue
                percent_un = float(percent_item.text())
                duration_ms = float(duration_item.text())
                if percent_un <= 0:
                    event = {"interruption": True, "duration_ms": duration_ms}
                else:
                    event = {"percent_un": percent_un, "duration_ms": duration_ms}
                count_text = count_item.text().strip() if count_item else ""
                event["count"] = int(count_text) if count_text else 1
                angles_text = angles_item.text().strip() if angles_item else ""
                if angles_text:
                    event["phase_angles"] = [int(a.strip()) for a in angles_text.split(",") if a.strip()]
                interval_text = interval_item.text().strip() if interval_item else ""
                if interval_text:
                    event["interval_ms"] = float(interval_text)
                events.append(event)
            if not events:
                raise ValueError("Adicione ao menos um evento ao roteiro de dips antes de continuar.")
            default_angles = [int(a) for a in _checked_values(self.dips_phase_list)] or [0]
            params = {
                "nominal_voltage": nominal,
                "frequency_hz": self.dips_freq_spin.value(),
                "phase_angles": default_angles,
                "events": events,
            }
            total_pulses = sum(
                event.get("count", 1) * len(event.get("phase_angles") or default_angles)
                for event in events
            )
            label = f"Roteiro com {len(events)} tipo(s) de evento, {total_pulses} pulso(s), Un={nominal:.0f} V"
            return params, label

        raise ValueError(standard_code)

    def _apply_params(self, standard_code: str, params: dict) -> None:
        if standard_code == "4-4":
            points = burst_params_to_points(params)
            self.burst_points_table.setRowCount(0)
            for point in points:
                self._append_burst_row(
                    point["voltage"],
                    point.get("frequency_hz", 5000),
                    point.get("coupling", "COM"),
                    point.get("polarity", "+"),
                    point.get("duration_s", BURST_DEFAULT_DURATION_S),
                )
            if points:
                last = points[-1]
                self.burst_voltage_spin.setValue(last["voltage"])
                freq_index = self.burst_freq_combo.findData(last.get("frequency_hz", 5000))
                if freq_index >= 0:
                    self.burst_freq_combo.setCurrentIndex(freq_index)
                coupling_index = self.burst_coupling_combo.findText(last.get("coupling", "COM"))
                if coupling_index >= 0:
                    self.burst_coupling_combo.setCurrentIndex(coupling_index)
                polarity_index = self.burst_polarity_combo.findText(last.get("polarity", "+"))
                if polarity_index >= 0:
                    self.burst_polarity_combo.setCurrentIndex(polarity_index)
                self.burst_duration_spin.setValue(last.get("duration_s", BURST_DEFAULT_DURATION_S))

        elif standard_code == "4-5":
            points = surge_params_to_points(params)
            self.surge_points_table.setRowCount(0)
            for point in points:
                self._append_surge_row(
                    point["voltage"],
                    point.get("coupling", "L-N"),
                    point.get("polarity", "+"),
                    point.get("phase_angle", 0),
                    point.get("pulse_count", SURGE_DEFAULT_PULSE_COUNT),
                    point.get("interval_s", SURGE_DEFAULT_INTERVAL_S),
                )
            if points:
                last = points[-1]
                self.surge_voltage_spin.setValue(last["voltage"])
                coupling_index = self.surge_coupling_combo.findText(last.get("coupling", "L-N"))
                if coupling_index >= 0:
                    self.surge_coupling_combo.setCurrentIndex(coupling_index)
                polarity_index = self.surge_polarity_combo.findText(last.get("polarity", "+"))
                if polarity_index >= 0:
                    self.surge_polarity_combo.setCurrentIndex(polarity_index)
                self.surge_angle_spin.setValue(last.get("phase_angle", 0))
                self.surge_pulse_count_spin.setValue(
                    last.get("pulse_count", SURGE_DEFAULT_PULSE_COUNT)
                )
                self.surge_interval_spin.setValue(
                    last.get("interval_s", SURGE_DEFAULT_INTERVAL_S)
                )

        elif standard_code == "4-11":
            self.dips_nominal_spin.setValue(params["nominal_voltage"])
            self.dips_freq_spin.setValue(params["frequency_hz"])
            _set_checked_values(self.dips_phase_list, [str(a) for a in params["phase_angles"]])
            self.dips_events_table.setRowCount(0)
            for event in params["events"]:
                percent_un = 0 if event.get("interruption") else event["percent_un"]
                count = event.get("count", 1)
                angles = ",".join(str(a) for a in event["phase_angles"]) if event.get("phase_angles") else ""
                interval = str(event["interval_ms"]) if event.get("interval_ms") else ""
                self._append_dips_row(percent_un, event["duration_ms"], count, angles, interval)

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
