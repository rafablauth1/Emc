from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import AUTOMATED_STANDARDS, STANDARDS
from app.core import energy_registry, planner
from app.core.planner import COMM_LINE_ELIGIBLE_STANDARDS, ORIGEM_DISPLAY, ORIGEM_SOFTWARE

STATUS_OPTIONS = ["pendente", "andamento", "concluido"]
STATUS_LABELS = {"pendente": "Pendente", "andamento": "Em andamento", "concluido": "Concluído"}

HEADER_FIELD_LABELS = [
    ("fabricante", "Fabricante:"),
    ("modelo", "Modelo:"),
    ("numero", "Nº:"),
    ("serie", "Série:"),
    ("tensao_nominal", "Tensão Nom. (V):"),
    ("corrente_nominal", "Corrente Nom. (A):"),
    ("protocolo", "Protocolo:"),
    ("data_entrada", "Data de Entrada:"),
    ("previsao_saida", "Previsão de Saída:"),
]


class _CodeSelectionDialog(QDialog):
    """Escolher, dentre o catálogo de códigos de grandeza, quais esse medidor
    específico tem (ex.: os que aparecem no display) — usado depois em Registro
    de Energia pra gerar as linhas de leitura automaticamente."""

    def __init__(self, parent=None, selected: list[int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Códigos aplicáveis a este medidor")
        self.resize(480, 520)
        selected_set = set(selected or [])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Marque os códigos que esse medidor tem/mostra:"))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["", "Código", "Legenda"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        for entry in energy_registry.list_codes():
            row = self.table.rowCount()
            self.table.insertRow(row)
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.CheckState.Checked if entry["codigo"] in selected_set else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, check_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(entry["codigo"])))
            self.table.setItem(row, 2, QTableWidgetItem(entry["legenda"]))

        btn_row = QHBoxLayout()
        all_btn = QPushButton("Marcar todos")
        all_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        btn_row.addWidget(all_btn)
        none_btn = QPushButton("Desmarcar todos")
        none_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        btn_row.addWidget(none_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, state: Qt.CheckState) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def selected_codes(self) -> list[int]:
        codes = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked:
                codes.append(int(self.table.item(row, 1).text()))
        return codes


class _CadastroDialog(QDialog):
    """Cadastro completo do projeto/equipamento: identificação, cliente e quais
    ensaios se aplicam (com opção de linha de comunicação separada para os que
    fizerem sentido). Serve tanto pra criar um projeto novo quanto editar um já
    existente (passe project + existing_items)."""

    def __init__(self, parent=None, project: dict | None = None, existing_items: list[dict] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Editar cadastro" if project else "Novo projeto")
        self.resize(460, 560)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(project["name"] if project else "")
        form.addRow("Nome do projeto:", self.name_edit)
        self.client_edit = QLineEdit(project["client"] if project else "")
        form.addRow("Cliente:", self.client_edit)
        self.header_edits: dict[str, QLineEdit] = {}
        for field, label in HEADER_FIELD_LABELS:
            edit = QLineEdit((project or {}).get(field, "") or "")
            form.addRow(label, edit)
            self.header_edits[field] = edit

        self.origem_combo = QComboBox()
        self.origem_combo.addItem("Display (leitura manual no mostrador)", ORIGEM_DISPLAY)
        self.origem_combo.addItem("Software (leitura via comunicação)", ORIGEM_SOFTWARE)
        origem_atual = (project or {}).get("origem_dados") or ORIGEM_DISPLAY
        index = self.origem_combo.findData(origem_atual)
        if index >= 0:
            self.origem_combo.setCurrentIndex(index)
        form.addRow("Dados via:", self.origem_combo)
        layout.addLayout(form)

        self._applicable_codes = planner.get_applicable_codes(project["id"]) if project else []
        codes_row = QHBoxLayout()
        self.codes_summary_label = QLabel()
        self._refresh_codes_summary()
        codes_row.addWidget(self.codes_summary_label, 1)
        codes_btn = QPushButton("Códigos aplicáveis...")
        codes_btn.clicked.connect(self._select_codes)
        codes_row.addWidget(codes_btn)
        layout.addLayout(codes_row)

        existing_keys = {(item["standard_code"], item["porta"]) for item in (existing_items or [])}
        is_new = project is None

        layout.addWidget(QLabel("Ensaios que se aplicam a este projeto:"))
        self.checkboxes: dict[str, QCheckBox] = {}
        self.comm_checkboxes: dict[str, QCheckBox] = {}
        for code, description in STANDARDS.items():
            row = QHBoxLayout()
            checkbox = QCheckBox(f"{code} — {description}")
            checkbox.setChecked(is_new or (code, "alimentação") in existing_keys)
            row.addWidget(checkbox)
            self.checkboxes[code] = checkbox
            if code in COMM_LINE_ELIGIBLE_STANDARDS:
                comm_checkbox = QCheckBox("também na linha de comunicação")
                comm_checkbox.setChecked((code, "comunicação") in existing_keys)
                row.addWidget(comm_checkbox)
                self.comm_checkboxes[code] = comm_checkbox
            row.addStretch(1)
            layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_codes_summary(self) -> None:
        n = len(self._applicable_codes)
        self.codes_summary_label.setText(
            f"{n} código(s) aplicável(is) selecionado(s)." if n else "Nenhum código selecionado ainda."
        )

    def _select_codes(self) -> None:
        dialog = _CodeSelectionDialog(self, selected=self._applicable_codes)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._applicable_codes = dialog.selected_codes()
            self._refresh_codes_summary()

    def header_values(self) -> dict:
        values = {field: edit.text().strip() for field, edit in self.header_edits.items()}
        values["origem_dados"] = self.origem_combo.currentData()
        return values

    def applicable_codes(self) -> list[int]:
        return list(self._applicable_codes)

    def selected_standards(self) -> list[str]:
        return [code for code, checkbox in self.checkboxes.items() if checkbox.isChecked()]

    def selected_comm_line_standards(self) -> list[str]:
        return [code for code, checkbox in self.comm_checkboxes.items() if checkbox.isChecked()]


class PlannerView(QWidget):
    run_test_requested = Signal(int, str)  # project_id, standard_code

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_id: int | None = None

        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Projeto:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_selected)
        top_bar.addWidget(self.project_combo, 1)
        new_project_btn = QPushButton("Novo projeto")
        new_project_btn.clicked.connect(self._create_project)
        top_bar.addWidget(new_project_btn)
        edit_cadastro_btn = QPushButton("Editar cadastro")
        edit_cadastro_btn.clicked.connect(self._edit_cadastro)
        top_bar.addWidget(edit_cadastro_btn)
        layout.addLayout(top_bar)

        cadastro_box = QGroupBox("Cadastro")
        cadastro_layout = QFormLayout(cadastro_box)
        self.cadastro_labels: dict[str, QLabel] = {}
        for field, label in [("client", "Cliente:")] + HEADER_FIELD_LABELS:
            value_label = QLabel("—")
            cadastro_layout.addRow(label, value_label)
            self.cadastro_labels[field] = value_label
        layout.addWidget(cadastro_box)

        checklist_box = QGroupBox("Checklist de ensaios")
        checklist_layout = QVBoxLayout(checklist_box)
        self.checklist_table = QTableWidget(0, 6)
        self.checklist_table.setHorizontalHeaderLabels(
            ["Norma", "Linha", "Descrição", "Status", "Data agendada", ""]
        )
        self.checklist_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.checklist_table.setAlternatingRowColors(True)
        checklist_layout.addWidget(self.checklist_table)
        layout.addWidget(checklist_box, 2)

        schedule_box = QGroupBox("Cronograma (todos os projetos)")
        schedule_layout = QVBoxLayout(schedule_box)
        self.schedule_table = QTableWidget(0, 5)
        self.schedule_table.setHorizontalHeaderLabels(
            ["Data", "Projeto", "Norma", "Linha", "Status"]
        )
        self.schedule_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.schedule_table.setAlternatingRowColors(True)
        schedule_layout.addWidget(self.schedule_table)
        layout.addWidget(schedule_box, 1)

        self.refresh_projects()
        self.refresh_schedule()

    def refresh_projects(self, select_project_id: int | None = None) -> None:
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = planner.list_projects()
        for project in projects:
            self.project_combo.addItem(project["name"], project["id"])
        self.project_combo.blockSignals(False)
        if select_project_id is not None:
            index = self.project_combo.findData(select_project_id)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
                self._on_project_selected(index)
                return
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._on_project_selected(0)
        else:
            self.current_project_id = None
            self._load_cadastro_summary()
            self._load_checklist()

    def _create_project(self) -> None:
        dialog = _CadastroDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text().strip()
        if not name:
            return
        project_id = planner.create_project(
            name,
            dialog.client_edit.text().strip(),
            dialog.selected_standards(),
            dialog.header_values(),
            dialog.selected_comm_line_standards(),
            dialog.applicable_codes(),
        )
        self.refresh_projects(select_project_id=project_id)
        self.refresh_schedule()

    def _edit_cadastro(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Cadastro", "Selecione ou crie um projeto primeiro.")
            return
        project = planner.get_project(self.current_project_id)
        existing_items = planner.list_test_items(self.current_project_id)
        dialog = _CadastroDialog(self, project=project, existing_items=existing_items)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text().strip()
        if not name:
            return
        planner.update_project(
            self.current_project_id,
            name,
            dialog.client_edit.text().strip(),
            dialog.header_values(),
            dialog.applicable_codes(),
        )
        planner.set_project_standards(
            self.current_project_id, dialog.selected_standards(), dialog.selected_comm_line_standards()
        )
        self.refresh_projects(select_project_id=self.current_project_id)
        self.refresh_schedule()

    def _on_project_selected(self, _index: int) -> None:
        project_id = self.project_combo.currentData()
        self.current_project_id = project_id
        self._load_cadastro_summary()
        self._load_checklist()

    def _load_cadastro_summary(self) -> None:
        project = planner.get_project(self.current_project_id) if self.current_project_id else None
        for field, label_widget in self.cadastro_labels.items():
            value = (project or {}).get(field, "") or "—"
            label_widget.setText(value)

    def _load_checklist(self) -> None:
        self.checklist_table.setRowCount(0)
        if self.current_project_id is None:
            return
        items = planner.list_test_items(self.current_project_id)
        # ordena pela ordem natural de STANDARDS (4-2..4-19), não pela ordem alfabética do banco
        order = {code: i for i, code in enumerate(STANDARDS)}
        items.sort(key=lambda item: (order.get(item["standard_code"], 999), item["porta"]))
        self.checklist_table.setRowCount(len(items))
        for row, item in enumerate(items):
            standard_code = item["standard_code"]
            self.checklist_table.setItem(row, 0, QTableWidgetItem(standard_code))
            self.checklist_table.setItem(row, 1, QTableWidgetItem(item["porta"]))
            self.checklist_table.setItem(
                row, 2, QTableWidgetItem(STANDARDS.get(standard_code, ""))
            )

            status_combo = QComboBox()
            for status in STATUS_OPTIONS:
                status_combo.addItem(STATUS_LABELS[status], status)
            status_combo.setCurrentIndex(STATUS_OPTIONS.index(item["status"]))
            status_combo.currentIndexChanged.connect(
                lambda _i, item_id=item["id"], combo=status_combo: self._on_status_changed(
                    item_id, combo
                )
            )
            self.checklist_table.setCellWidget(row, 3, status_combo)

            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setSpecialValueText(" ")
            date_edit.setMinimumDate(QDate(2000, 1, 1))
            if item["scheduled_date"]:
                date_edit.setDate(QDate.fromString(item["scheduled_date"], "yyyy-MM-dd"))
            else:
                date_edit.setDate(date_edit.minimumDate())
            date_edit.dateChanged.connect(
                lambda date, item_id=item["id"]: self._on_date_changed(item_id, date)
            )
            self.checklist_table.setCellWidget(row, 4, date_edit)

            if standard_code in AUTOMATED_STANDARDS:
                run_btn = QPushButton("Executar")
                run_btn.clicked.connect(
                    lambda _checked=False, code=standard_code: self._request_run(code)
                )
                self.checklist_table.setCellWidget(row, 5, run_btn)

    def _request_run(self, standard_code: str) -> None:
        if self.current_project_id is not None:
            self.run_test_requested.emit(self.current_project_id, standard_code)

    def _on_status_changed(self, item_id: int, combo: QComboBox) -> None:
        planner.update_item_status(item_id, combo.currentData())
        self.refresh_schedule()

    def _on_date_changed(self, item_id: int, date: QDate) -> None:
        value = None if date == QDate(2000, 1, 1) else date.toString("yyyy-MM-dd")
        planner.update_item_schedule(item_id, value)
        self.refresh_schedule()

    def refresh_schedule(self) -> None:
        items = planner.list_scheduled_items()
        self.schedule_table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.schedule_table.setItem(row, 0, QTableWidgetItem(item["scheduled_date"]))
            self.schedule_table.setItem(row, 1, QTableWidgetItem(item["project_name"]))
            self.schedule_table.setItem(row, 2, QTableWidgetItem(item["standard_code"]))
            self.schedule_table.setItem(row, 3, QTableWidgetItem(item["porta"]))
            self.schedule_table.setItem(
                row, 4, QTableWidgetItem(STATUS_LABELS.get(item["status"], item["status"]))
            )
