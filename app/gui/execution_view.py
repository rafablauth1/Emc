from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
    BURST_SPIKE_FREQUENCIES_HZ,
    DIPS_LEVELS,
    DIPS_PHASE_ANGLES_DEG,
    DIPS_SHORT_INTERRUPTION_MS,
    SURGE_COUPLINGS,
    SURGE_DEFAULT_INTERVAL_S,
    SURGE_DEFAULT_PULSE_COUNT,
    SURGE_LEVELS,
    SURGE_METER_PHASE_COMBINATIONS,
)
from app.core.test_session import TestSessionWorker, set_session_result
from app.gui.routine_editor import RoutineEditorDialog, describe_point
from app.instruments.factory import build_driver_for_standard

DEFAULT_PHASE_COMBINATIONS = ["L1-N"]


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
            self.burst_points = self._default_burst_points()
            self._refresh_points_summary("4-4")
        elif standard_code == "4-5":
            self.surge_points = self._default_surge_points()
            self._refresh_points_summary("4-5")
            _set_checked_values(self.surge_phase_combo_list, DEFAULT_PHASE_COMBINATIONS)
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

    # ---- utilitários genéricos de tabela (usados pelo roteiro de dips) ----

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

    # ---- roteiro (sequência de pontos) de burst/surge — editado em sub-tela dedicada ----

    def _refresh_points_summary(self, standard_code: str) -> None:
        if standard_code == "4-4":
            list_widget, points = self.burst_summary_list, self.burst_points
        else:
            list_widget, points = self.surge_summary_list, self.surge_points
        list_widget.clear()
        for i, point in enumerate(points):
            list_widget.addItem(f"{i + 1}. {describe_point(standard_code, point)}")

    def _open_routine_editor(self, standard_code: str) -> None:
        points = self.burst_points if standard_code == "4-4" else self.surge_points
        dialog = RoutineEditorDialog(standard_code, points, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if standard_code == "4-4":
                self.burst_points = dialog.get_points()
            else:
                self.surge_points = dialog.get_points()
            self._refresh_points_summary(standard_code)

    def _default_burst_points(self) -> list[dict]:
        return [
            {
                "voltage": BURST_LEVELS[0].voltage,
                "frequency_hz": BURST_SPIKE_FREQUENCIES_HZ[0],
                "coupling": "COM",
                "polarity": "+",
                "duration_s": BURST_DEFAULT_DURATION_S,
            }
        ]

    def _default_surge_points(self) -> list[dict]:
        return [
            {
                "voltage": SURGE_LEVELS[0].voltage,
                "coupling": SURGE_COUPLINGS[0],
                "polarity": "+",
                "phase_angle": 0,
                "pulse_count": SURGE_DEFAULT_PULSE_COUNT,
                "interval_s": SURGE_DEFAULT_INTERVAL_S,
            }
        ]

    # ---- páginas de parâmetros por norma ----

    def _build_burst_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Roteiro de burst (IEC 61000-4-4) — sequência de pontos, executados na ordem abaixo.\n"
                "Clique em \"Editar roteiro...\" para montar a sequência (sempre dá para adicionar o "
                "polo + e o polo − juntos, de uma vez)."
            )
        )
        self.burst_summary_list = QListWidget()
        self.burst_summary_list.setMinimumHeight(160)
        layout.addWidget(self.burst_summary_list, 1)

        edit_row = QHBoxLayout()
        edit_btn = QPushButton("Editar roteiro...")
        edit_btn.clicked.connect(lambda: self._open_routine_editor("4-4"))
        edit_row.addWidget(edit_btn)
        layout.addLayout(edit_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-4")
        layout.addLayout(template_form)

        self.burst_points = self._default_burst_points()
        self._refresh_points_summary("4-4")
        return page

    def _build_surge_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Combinações de fase a testar (medidor bi/trifásico) — marque as que se aplicam "
                "ao seu medidor. O mesmo roteiro roda uma vez por combinação marcada; o ensaio "
                "pausa entre uma e outra e avisa no log para trocar o setup."
            )
        )
        self.surge_phase_combo_list = _checkable_list(list(SURGE_METER_PHASE_COMBINATIONS))
        self.surge_phase_combo_list.setMaximumHeight(140)
        _set_checked_values(self.surge_phase_combo_list, DEFAULT_PHASE_COMBINATIONS)
        layout.addWidget(self.surge_phase_combo_list)

        layout.addWidget(
            QLabel(
                "Roteiro de surge (IEC 61000-4-5) — sequência de pontos, executados na ordem abaixo.\n"
                "Clique em \"Editar roteiro...\" para montar a sequência (sempre dá para adicionar o "
                "polo + e o polo − juntos, de uma vez, ou a grade completa de ângulos × polos)."
            )
        )
        self.surge_summary_list = QListWidget()
        self.surge_summary_list.setMinimumHeight(160)
        layout.addWidget(self.surge_summary_list, 1)

        edit_row = QHBoxLayout()
        edit_btn = QPushButton("Editar roteiro...")
        edit_btn.clicked.connect(lambda: self._open_routine_editor("4-5"))
        edit_row.addWidget(edit_btn)
        layout.addLayout(edit_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-5")
        layout.addLayout(template_form)

        self.surge_points = self._default_surge_points()
        self._refresh_points_summary("4-5")
        return page

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
            if not self.burst_points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de burst antes de continuar.")
            params = {"points": self.burst_points}
            voltages = {p["voltage"] for p in self.burst_points}
            voltage_desc = f"{self.burst_points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = f"Roteiro com {len(self.burst_points)} ponto(s), {voltage_desc}"
            return params, label

        if standard_code == "4-5":
            if not self.surge_points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de surge antes de continuar.")
            combinations = [
                combo
                for combo in SURGE_METER_PHASE_COMBINATIONS
                if combo in _checked_values(self.surge_phase_combo_list)
            ]
            if not combinations:
                raise ValueError("Marque ao menos uma combinação de fase (ex: L1-N) antes de continuar.")
            params = {"points": self.surge_points, "phase_combinations": combinations}
            voltages = {p["voltage"] for p in self.surge_points}
            voltage_desc = f"{self.surge_points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = (
                f"Roteiro com {len(self.surge_points)} ponto(s), {voltage_desc}, "
                f"{len(combinations)} combinação(ões) de fase ({', '.join(combinations)})"
            )
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
            self.burst_points = burst_params_to_points(params)
            self._refresh_points_summary("4-4")

        elif standard_code == "4-5":
            self.surge_points = surge_params_to_points(params)
            self._refresh_points_summary("4-5")
            combinations = params.get("phase_combinations")
            if not combinations:
                # compatibilidade com o formato anterior (meter_elements: int, sem escolha de fase)
                meter_elements = params.get("meter_elements", 1)
                combinations = list(SURGE_METER_PHASE_COMBINATIONS[:meter_elements]) or DEFAULT_PHASE_COMBINATIONS
            _set_checked_values(self.surge_phase_combo_list, combinations)

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
        self.worker.paused.connect(self._on_paused)
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

    def _on_paused(self, message: str) -> None:
        self.log_view.appendPlainText(f"*** PAUSA: {message} ***")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Pausa no ensaio")
        box.setText(message)
        continue_btn = box.addButton("Continuar ensaio", QMessageBox.ButtonRole.AcceptRole)
        abort_btn = box.addButton("Abortar ensaio", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(continue_btn)
        box.exec()
        if self.worker is None:
            return
        if box.clickedButton() == abort_btn:
            self.worker.request_stop()
        else:
            self.worker.resume()

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
