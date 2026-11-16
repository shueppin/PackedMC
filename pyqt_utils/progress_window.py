from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar


class ProgressWindow(QWidget):
    """
    A small progress window which is a separate top level window and NOT modal.
    The window that owns it stays fully usable while this window is open. (The owner is only needed so that this window is
    closed together with it, and so that it stays above it.)

    The window has no close button, because the work behind it can not be cancelled. Close it from the code with ``close()``.
    """

    def __init__(self, parent: QWidget | None, title: str, maximum: int, text: str = ''):
        flags = Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowMinimizeButtonHint
        super().__init__(parent, flags)

        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(320, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, max(maximum, 1))
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

    def set_progress(self, value: int, text: str | None = None):
        self.progress_bar.setValue(value)
        if text is not None:
            self.label.setText(text)

    def show_centered_over_parent(self):
        parent = self.parentWidget()
        if parent is not None:
            self.move(parent.geometry().center() - self.rect().center())
        self.show()
