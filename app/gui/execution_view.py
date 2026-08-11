from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import AUTOMATED_STANDARDS, STANDARDS
from app.core import planner
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


class ExecutionView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: TestSessionWorker | None = None

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

    # ---- páginas de parâmetros por norma ----

    def _build_burst_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.burst_level_combo = QComboBox()
        for level in BURST_LEVELS:
            self.burst_level_combo.addItem(f"Nível {level.level} — {level.voltage} V", level)
        form.addRow("Nível (IEC 61000-4-4):", self.burst_level_combo)

        self.burst_freq_combo = QComboBox()
        for freq in BURST_SPIKE_FREQUENCIES_HZ:
            self.burst_freq_combo.addItem(f"{freq / 1000:.0f} kHz", freq)
        form.addRow("Frequência de repetição:", self.burst_freq_combo)

        self.burst_coupling_combo = QComboBox()
        self.burst_coupling_combo.addItems(["COM", "ALL", "CCC"])
        form.addRow("Acoplamento:", self.burst_coupling_combo)

        self.burst_polarity_list = _checkable_list(["+", "-"])
        form.addRow("Polaridades:", self.burst_polarity_list)
        return page

    def _build_surge_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.surge_level_combo = QComboBox()
        for level in SURGE_LEVELS:
            self.surge_level_combo.addItem(f"Nível {level.level} — {level.voltage} V", level)
        form.addRow("Nível (IEC 61000-4-5):", self.surge_level_combo)

        self.surge_coupling_combo = QComboBox()
        self.surge_coupling_combo.addItems(list(SURGE_COUPLINGS))
        form.addRow("Acoplamento:", self.surge_coupling_combo)

        self.surge_polarity_list = _checkable_list(["+", "-"])
        form.addRow("Polaridades:", self.surge_polarity_list)

        self.surge_phase_list = _checkable_list([str(a) for a in SURGE_PHASE_ANGLES_DEG])
        form.addRow("Ângulos de fase (°):", self.surge_phase_list)
        return page

    def _build_dips_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
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

        self.dips_level_combo = QComboBox()
        for level in DIPS_LEVELS:
            self.dips_level_combo.addItem(
                f"Nível {level.level} — {level.percent_un}% Un, {level.duration_ms:.0f} ms",
                level,
            )
        self.dips_level_combo.addItem(
            f"Interrupção curta — {DIPS_SHORT_INTERRUPTION_MS:.0f} ms", "interruption"
        )
        form.addRow("Evento (IEC 61000-4-11):", self.dips_level_combo)

        self.dips_phase_list = _checkable_list([str(a) for a in DIPS_PHASE_ANGLES_DEG])
        form.addRow("Ângulos de fase (°):", self.dips_phase_list)
        return page

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

    # ---- montagem de parâmetros ----

    def _collect_params(self, standard_code: str) -> tuple[dict, str]:
        if standard_code == "4-4":
            level = self.burst_level_combo.currentData()
            freq = self.burst_freq_combo.currentData()
            params = {
                "voltage": level.voltage,
                "frequency_hz": freq,
                "coupling": self.burst_coupling_combo.currentText(),
                "polarities": _checked_values(self.burst_polarity_list),
            }
            label = f"Nível {level.level} ({level.voltage} V)"
            return params, label

        if standard_code == "4-5":
            level = self.surge_level_combo.currentData()
            params = {
                "voltage": level.voltage,
                "coupling": self.surge_coupling_combo.currentText(),
                "polarities": _checked_values(self.surge_polarity_list),
                "phase_angles": [int(a) for a in _checked_values(self.surge_phase_list)],
            }
            label = f"Nível {level.level} ({level.voltage} V)"
            return params, label

        if standard_code == "4-11":
            selection = self.dips_level_combo.currentData()
            nominal = self.dips_nominal_spin.value()
            if selection == "interruption":
                events = [{"interruption": True, "duration_ms": DIPS_SHORT_INTERRUPTION_MS}]
                label = "Interrupção curta"
            else:
                events = [
                    {"percent_un": selection.percent_un, "duration_ms": selection.duration_ms}
                ]
                label = f"Nível {selection.level} ({selection.percent_un}% Un)"
            params = {
                "nominal_voltage": nominal,
                "frequency_hz": self.dips_freq_spin.value(),
                "phase_angles": [int(a) for a in _checked_values(self.dips_phase_list)],
                "events": events,
            }
            return params, label

        raise ValueError(standard_code)

    # ---- execução ----

    def _start_test(self) -> None:
        project_id = self.project_combo.currentData()
        if project_id is None:
            QMessageBox.warning(self, "Ensaio", "Selecione um projeto antes de iniciar.")
            return
        standard_code = self.standard_combo.currentData()
        params, level_label = self._collect_params(standard_code)
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
