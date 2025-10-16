"""Main entry point for duperscooper GUI application."""

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .windows.main_window import MainWindow


def main():
    """Start the duperscooper GUI application."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Duperscooper")
    app.setApplicationDisplayName("Duperscooper")
    app.setOrganizationName("duperscooper")
    app.setApplicationVersion("0.1.0")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Handle Ctrl+C gracefully
    # Qt event loop blocks signals, so we need to periodically allow
    # Python to process them. This timer lets Python handle KeyboardInterrupt.
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # No-op, just lets Python process signals
    timer.start(500)

    # Install signal handler for clean exit
    def signal_handler(sig, frame):
        """Handle Ctrl+C by closing the application cleanly."""
        print("\nShutting down duperscooper GUI...")
        # Call window.close() to trigger closeEvent confirmation
        window.close()

    signal.signal(signal.SIGINT, signal_handler)

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
