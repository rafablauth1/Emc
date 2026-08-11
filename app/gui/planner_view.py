from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDate

from app.config import AUTOMATED_STANDARDS, STANDARDS
from app.core import planner

STATUS_OPTIONS = ["pendente", "andamento", "concluido"]
STATUS_LABELS = {"pendente": "Pendente", "andamento": "Em andamento", "concluido": "Concluído"}


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
        layout.addLayout(top_bar)

        layout.addWidget(QLabel("Checklist de ensaios"))
        self.checklist_table = QTableWidget(0, 5)
        self.checklist_table.setHorizontalHeaderLabels(
            ["Norma", "Descrição", "Status", "Data agendada", ""]
        )
        self.checklist_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.checklist_table, 2)

        layout.addWidget(QLabel("Cronograma (todos os projetos)"))
        self.schedule_table = QTableWidget(0, 4)
        self.schedule_table.setHorizontalHeaderLabels(
            ["Data", "Projeto", "Norma", "Status"]
        )
        self.schedule_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.schedule_table, 1)

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
                return
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._on_project_selected(0)

    def _create_project(self) -> None:
        name, ok = QInputDialog.getText(self, "Novo projeto", "Nome do projeto:")
        if not ok or not name.strip():
            return
        client, _ = QInputDialog.getText(self, "Novo projeto", "Cliente (opcional):")
        project_id = planner.create_project(name.strip(), client.strip())
        self.refresh_projects(select_project_id=project_id)
        self.refresh_schedule()

    def _on_project_selected(self, _index: int) -> None:
        project_id = self.project_combo.currentData()
        self.current_project_id = project_id
        self._load_checklist()

    def _load_checklist(self) -> None:
        self.checklist_table.setRowCount(0)
        if self.current_project_id is None:
            return
        items = planner.list_test_items(self.current_project_id)
        self.checklist_table.setRowCount(len(items))
        for row, item in enumerate(items):
            standard_code = item["standard_code"]
            self.checklist_table.setItem(row, 0, QTableWidgetItem(standard_code))
            self.checklist_table.setItem(
                row, 1, QTableWidgetItem(STANDARDS.get(standard_code, ""))
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
            self.checklist_table.setCellWidget(row, 2, status_combo)

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
            self.checklist_table.setCellWidget(row, 3, date_edit)

            if standard_code in AUTOMATED_STANDARDS:
                run_btn = QPushButton("Executar")
                run_btn.clicked.connect(
                    lambda _checked=False, code=standard_code: self._request_run(code)
                )
                self.checklist_table.setCellWidget(row, 4, run_btn)

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
            self.schedule_table.setItem(
                row, 3, QTableWidgetItem(STATUS_LABELS.get(item["status"], item["status"]))
            )
