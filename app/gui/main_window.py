from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.gui.energy_registry_view import EnergyRegistryView
from app.gui.execution_view import ExecutionView
from app.gui.planner_view import PlannerView
from app.gui.reports_view import ReportsView
from app.gui.settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatizador de Ensaios EMC")
        self.resize(1100, 750)

        self.planner_view = PlannerView()
        self.execution_view = ExecutionView()
        self.energy_registry_view = EnergyRegistryView()
        self.reports_view = ReportsView()
        self.settings_view = SettingsView()

        self.planner_view.run_test_requested.connect(self._go_to_execution)

        tabs = QTabWidget()
        tabs.addTab(self.planner_view, "Planner")
        tabs.addTab(self.execution_view, "Execução")
        tabs.addTab(self.energy_registry_view, "Registro de Energia")
        tabs.addTab(self.reports_view, "Relatórios")
        tabs.addTab(self.settings_view, "Configurações")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs = tabs
        self.setCentralWidget(tabs)

    def _go_to_execution(self, project_id: int, standard_code: str) -> None:
        self.execution_view.preselect(project_id, standard_code)
        self.tabs.setCurrentWidget(self.execution_view)

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.execution_view:
            self.execution_view.refresh_projects()
        elif widget is self.energy_registry_view:
            self.energy_registry_view.refresh_projects()
        elif widget is self.reports_view:
            self.reports_view.refresh()
        elif widget is self.planner_view:
            self.planner_view.refresh_schedule()
