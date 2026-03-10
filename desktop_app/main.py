import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor


def apply_dark_theme(app: QApplication):
    """Applies a modern dark Fusion theme to the application."""
    app.setStyle("Fusion")

    # FIX: Use QPalette.ColorRole enum for PySide6 compatibility (avoids deprecation warnings)
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window,          QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.WindowText,      Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base,            QColor(28, 28, 28))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(45, 45, 48))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase,     Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText,     Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text,            Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button,          QColor(55, 55, 60))
    dark_palette.setColor(QPalette.ColorRole.ButtonText,      Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText,      Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link,            QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight,       QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

    app.setPalette(dark_palette)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AudioSepClient")
    app.setOrganizationName("AudioSepOrg")

    apply_dark_theme(app)

    from gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
