from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import STANDARDS
from app.core import energy_registry, planner

COL_ENSAIO = 0
COL_METROLOGISTA = 1
COL_TENSAO_LABEL = 2
COL_VALOR_V = 3
COL_FOTO = 4
COL_CODIGO = 5
COL_LEGENDA = 6
COL_DATA_INI = 7
COL_REG_INI = 8
COL_DATA_FIM = 9
COL_REG_FIM = 10
COL_OBS = 11

COLUMN_LABELS = [
    "Ensaio", "Metrologista", "Tensão", "Valor (V)", "Foto Realizada",
    "Código", "Legenda", "Data Inicial", "Registro Inicial",
    "Data Final", "Registro Final", "Observações",
]


class EnergyRegistryView(QWidget):
    """Registro de leituras de energia por ensaio/tensão — equivalente à
    planilha 'Registro de Energia' usada no laboratório: acompanha se o
    medidor mantém a leitura correta antes/depois de cada evento EMC."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_id: int | None = None
        self._project_standard_codes: list[str] = list(STANDARDS)
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Projeto:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_selected)
        top_row.addWidget(self.project_combo, 1)
        manage_codes_btn = QPushButton("Gerenciar códigos...")
        manage_codes_btn.clicked.connect(self._open_code_manager)
        top_row.addWidget(manage_codes_btn)
        layout.addLayout(top_row)

        summary_form = QFormLayout()
        self.cliente_label = QLabel("—")
        summary_form.addRow("Cliente:", self.cliente_label)
        self.protocolo_label = QLabel("—")
        summary_form.addRow("Protocolo:", self.protocolo_label)
        layout.addLayout(summary_form)
        layout.addWidget(
            QLabel(
                "Identificação completa do equipamento (fabricante, modelo, série...) fica "
                "no Cadastro, na aba Planner — aqui só cliente/protocolo pra referência."
            )
        )

        layout.addWidget(
            QLabel(
                "Leituras — uma linha por código de grandeza registrado em cada tensão de "
                "cada ensaio. A Legenda é preenchida sozinha ao digitar o Código."
            )
        )
        self.table = QTableWidget(0, len(COLUMN_LABELS))
        self.table.setHorizontalHeaderLabels(COLUMN_LABELS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        add_line_btn = QPushButton("Adicionar linha (mesmo bloco)")
        add_line_btn.clicked.connect(self._add_line_same_block)
        btn_row.addWidget(add_line_btn)
        add_voltage_btn = QPushButton("Nova tensão (mesmo ensaio)")
        add_voltage_btn.clicked.connect(self._add_new_voltage)
        btn_row.addWidget(add_voltage_btn)
        add_blank_btn = QPushButton("Adicionar linha em branco")
        add_blank_btn.clicked.connect(self._add_blank_row)
        btn_row.addWidget(add_blank_btn)
        remove_btn = QPushButton("Remover linha selecionada")
        remove_btn.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(remove_btn)
        up_btn = QPushButton("▲ Mover para cima")
        up_btn.clicked.connect(lambda: self._move_row(-1))
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("▼ Mover para baixo")
        down_btn.clicked.connect(lambda: self._move_row(1))
        btn_row.addWidget(down_btn)
        layout.addLayout(btn_row)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Salvar registro")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        self.save_status = QLabel("")
        save_row.addWidget(self.save_status, 1)
        layout.addLayout(save_row)

        self.refresh_projects()

    # ---- projeto ----

    def refresh_projects(self) -> None:
        current = self.project_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in planner.list_projects():
            self.project_combo.addItem(project["name"], project["id"])
        self.project_combo.blockSignals(False)
        if current is not None:
            index = self.project_combo.findData(current)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
                return
        if self.project_combo.count():
            self.project_combo.setCurrentIndex(0)
            self._on_project_selected(0)

    def _on_project_selected(self, _index: int) -> None:
        self.current_project_id = self.project_combo.currentData()
        self._load()

    # ---- carregar / salvar ----

    def _load(self) -> None:
        self.save_status.setText("")
        if self.current_project_id is None:
            self.cliente_label.setText("—")
            self.protocolo_label.setText("—")
            self.table.setRowCount(0)
            return
        project = planner.get_project(self.current_project_id) or {}
        self.cliente_label.setText(project.get("client") or "—")
        self.protocolo_label.setText(project.get("protocolo") or "—")

        project_codes = {item["standard_code"] for item in planner.list_test_items(self.current_project_id)}
        # ordena pela ordem natural de STANDARDS (4-2..4-19), não pela ordem alfabética do banco
        self._project_standard_codes = [code for code in STANDARDS if code in project_codes] or list(STANDARDS)

        leituras = energy_registry.get_leituras(self.current_project_id)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for leitura in leituras:
            self._append_row(leitura)
        self.table.blockSignals(False)

    def _combo_codes(self, current: str = "") -> list[str]:
        """Ensaios do projeto atual (só os que foram marcados na criação do
        projeto); inclui o código da leitura mesmo que não esteja mais na
        lista do projeto, pra não perder/esconder dado já gravado."""
        codes = list(self._project_standard_codes)
        if current and current not in codes:
            codes.append(current)
        return codes

    def _save(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Registro de energia", "Selecione um projeto antes de salvar.")
            return
        leituras = [self._row_to_dict(row) for row in range(self.table.rowCount())]
        energy_registry.save_leituras(self.current_project_id, leituras)
        self.save_status.setStyleSheet("color: green;")
        self.save_status.setText("Salvo.")

    # ---- linhas da tabela ----

    def _append_row(self, leitura: dict | None = None) -> int:
        leitura = leitura or {}
        row = self.table.rowCount()
        self.table.insertRow(row)

        combo = QComboBox()
        for code in self._combo_codes(leitura.get("standard_code", "")):
            combo.addItem(code, code)
        index = combo.findData(leitura.get("standard_code", ""))
        if index >= 0:
            combo.setCurrentIndex(index)
        self.table.setCellWidget(row, COL_ENSAIO, combo)

        self.table.setItem(row, COL_METROLOGISTA, QTableWidgetItem(leitura.get("metrologista", "")))
        self.table.setItem(row, COL_TENSAO_LABEL, QTableWidgetItem(leitura.get("tensao_label", "")))
        self.table.setItem(row, COL_VALOR_V, QTableWidgetItem(str(leitura.get("valor_v", ""))))

        foto_item = QTableWidgetItem("")
        foto_item.setFlags(foto_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        foto_item.setCheckState(
            Qt.CheckState.Checked if leitura.get("foto_realizada") else Qt.CheckState.Unchecked
        )
        self.table.setItem(row, COL_FOTO, foto_item)

        codigo = leitura.get("codigo", "")
        self.table.setItem(row, COL_CODIGO, QTableWidgetItem(str(codigo) if codigo != "" else ""))
        legenda_item = QTableWidgetItem(leitura.get("legenda", ""))
        legenda_item.setFlags(legenda_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_LEGENDA, legenda_item)

        self.table.setItem(row, COL_DATA_INI, QTableWidgetItem(leitura.get("data_inicial", "")))
        self.table.setItem(row, COL_REG_INI, QTableWidgetItem(leitura.get("registro_inicial", "")))
        self.table.setItem(row, COL_DATA_FIM, QTableWidgetItem(leitura.get("data_final", "")))
        self.table.setItem(row, COL_REG_FIM, QTableWidgetItem(leitura.get("registro_final", "")))
        self.table.setItem(row, COL_OBS, QTableWidgetItem(leitura.get("observacoes", "")))
        return row

    def _row_to_dict(self, row: int) -> dict:
        combo = self.table.cellWidget(row, COL_ENSAIO)
        item = lambda col: self.table.item(row, col)
        text = lambda col: item(col).text() if item(col) else ""
        foto_item = item(COL_FOTO)
        return {
            "standard_code": combo.currentData() if combo else "",
            "metrologista": text(COL_METROLOGISTA),
            "tensao_label": text(COL_TENSAO_LABEL),
            "valor_v": text(COL_VALOR_V),
            "foto_realizada": bool(foto_item and foto_item.checkState() == Qt.CheckState.Checked),
            "codigo": text(COL_CODIGO),
            "legenda": text(COL_LEGENDA),
            "data_inicial": text(COL_DATA_INI),
            "registro_inicial": text(COL_REG_INI),
            "data_final": text(COL_DATA_FIM),
            "registro_final": text(COL_REG_FIM),
            "observacoes": text(COL_OBS),
        }

    def _add_blank_row(self) -> None:
        self._append_row()

    def _add_line_same_block(self) -> None:
        """Nova linha de código dentro do mesmo ensaio/tensão da linha selecionada
        (equivalente à barra verde 'Adicionar Linha de Código' da planilha)."""
        row = self.table.currentRow()
        if row < 0:
            self._append_row()
            return
        base = self._row_to_dict(row)
        self._append_row(
            {
                "standard_code": base["standard_code"],
                "metrologista": base["metrologista"],
                "tensao_label": base["tensao_label"],
                "valor_v": base["valor_v"],
                "foto_realizada": base["foto_realizada"],
            }
        )

    def _add_new_voltage(self) -> None:
        """Novo bloco de tensão dentro do mesmo ensaio da linha selecionada
        (equivalente ao botão '+ Tensão' da planilha)."""
        row = self.table.currentRow()
        if row < 0:
            self._append_row()
            return
        base = self._row_to_dict(row)
        existing_labels = {
            self._row_to_dict(r)["tensao_label"]
            for r in range(self.table.rowCount())
            if self._row_to_dict(r)["standard_code"] == base["standard_code"]
        }
        n = 1
        while f"TENSÃO {n}" in existing_labels:
            n += 1
        self._append_row(
            {
                "standard_code": base["standard_code"],
                "metrologista": base["metrologista"],
                "tensao_label": f"TENSÃO {n}",
            }
        )

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _move_row(self, delta: int) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= self.table.rowCount():
            return
        data = self._row_to_dict(row)
        self.table.blockSignals(True)
        self.table.removeRow(row)
        self.table.insertRow(new_row)
        self.table.blockSignals(False)
        # reconstrói a linha na nova posição (mais simples que mover widgets/itens um a um)
        self.table.blockSignals(True)
        combo = QComboBox()
        for code in self._combo_codes(data["standard_code"]):
            combo.addItem(code, code)
        index = combo.findData(data["standard_code"])
        if index >= 0:
            combo.setCurrentIndex(index)
        self.table.setCellWidget(new_row, COL_ENSAIO, combo)
        self.table.setItem(new_row, COL_METROLOGISTA, QTableWidgetItem(data["metrologista"]))
        self.table.setItem(new_row, COL_TENSAO_LABEL, QTableWidgetItem(data["tensao_label"]))
        self.table.setItem(new_row, COL_VALOR_V, QTableWidgetItem(str(data["valor_v"])))
        foto_item = QTableWidgetItem("")
        foto_item.setFlags(foto_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        foto_item.setCheckState(
            Qt.CheckState.Checked if data["foto_realizada"] else Qt.CheckState.Unchecked
        )
        self.table.setItem(new_row, COL_FOTO, foto_item)
        self.table.setItem(new_row, COL_CODIGO, QTableWidgetItem(str(data["codigo"])))
        legenda_item = QTableWidgetItem(data["legenda"])
        legenda_item.setFlags(legenda_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(new_row, COL_LEGENDA, legenda_item)
        self.table.setItem(new_row, COL_DATA_INI, QTableWidgetItem(data["data_inicial"]))
        self.table.setItem(new_row, COL_REG_INI, QTableWidgetItem(data["registro_inicial"]))
        self.table.setItem(new_row, COL_DATA_FIM, QTableWidgetItem(data["data_final"]))
        self.table.setItem(new_row, COL_REG_FIM, QTableWidgetItem(data["registro_final"]))
        self.table.setItem(new_row, COL_OBS, QTableWidgetItem(data["observacoes"]))
        self.table.blockSignals(False)
        self.table.setCurrentCell(new_row, 0)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column != COL_CODIGO:
            return
        item = self.table.item(row, COL_CODIGO)
        text = item.text().strip() if item else ""
        legenda = ""
        if text.isdigit():
            legenda = energy_registry.get_legend(int(text))
        legenda_item = self.table.item(row, COL_LEGENDA)
        self.table.blockSignals(True)
        if legenda_item is None:
            legenda_item = QTableWidgetItem()
            legenda_item.setFlags(legenda_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, COL_LEGENDA, legenda_item)
        legenda_item.setText(legenda)
        self.table.blockSignals(False)

    # ---- catálogo de códigos ----

    def _open_code_manager(self) -> None:
        dialog = _CodeManagerDialog(self)
        dialog.exec()


class _CodeManagerDialog(QDialog):
    """Ver/editar o catálogo de códigos de grandezas (aba 'Codigos' da planilha)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Catálogo de códigos de grandezas")
        self.resize(520, 500)
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                "Códigos padrão de grandezas usadas por medidores eletrônicos no Brasil. "
                "Nem todo medidor implementa todos — apague os que não existirem no seu."
            )
        )
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Código", "Legenda"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        for entry in energy_registry.list_codes():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(entry["codigo"])))
            self.table.setItem(row, 1, QTableWidgetItem(entry["legenda"]))

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Adicionar código")
        add_btn.clicked.connect(self._add_code)
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("Remover selecionado")
        remove_btn.clicked.connect(self._remove_code)
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_code(self) -> None:
        codigo, ok = QInputDialog.getInt(self, "Novo código", "Código:", 0, 0, 9999)
        if not ok:
            return
        legenda, ok2 = QInputDialog.getText(self, "Novo código", "Legenda:")
        if not ok2 or not legenda.strip():
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(codigo)))
        self.table.setItem(row, 1, QTableWidgetItem(legenda.strip()))

    def _remove_code(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _save_and_close(self) -> None:
        with_conn_codes = []
        for row in range(self.table.rowCount()):
            codigo_item = self.table.item(row, 0)
            legenda_item = self.table.item(row, 1)
            if not codigo_item or not codigo_item.text().strip().isdigit():
                continue
            with_conn_codes.append((int(codigo_item.text().strip()), legenda_item.text().strip() if legenda_item else ""))
        energy_registry.replace_codes(with_conn_codes)
        self.accept()
