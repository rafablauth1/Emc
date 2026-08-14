import sys

if sys.platform == "win32":
    # Marca o processo como "per-monitor DPI aware" ANTES de qualquer coisa do
    # Qt ser criada — sem isso, o Windows faz um esticamento automático (bitmap
    # scaling) da janela inteira em telas com escala (125%/150%), deixando tudo
    # borrado/desproporcional, principalmente em tela cheia.
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.core.db import init_db
from app.gui.main_window import MainWindow


def main() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
