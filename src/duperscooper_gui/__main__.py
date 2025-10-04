"""Main entry point for duperscooper GUI application."""

import sys

from PySide6.QtWidgets import QApplication

from .windows.main_window import MainWindow


def main():
    """Start the duperscooper GUI application."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("duperscooper")
    app.setOrganizationName("duperscooper")
    app.setApplicationVersion("0.1.0")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
