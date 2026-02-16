from enum import Enum

from PyQt6.QtWidgets import QWidget, QGridLayout, QScrollArea, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt


class FieldType(Enum):
    INSTANCES = "Instances"
    MODS = "Mods"


class InstanceField(QFrame):
    def __init__(self, instance_name: str, width=200, height=100):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(2)
        self.setFixedSize(width, height)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        name_label = QLabel(instance_name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(name_label)

        button_layout = QHBoxLayout()
        play_button = QPushButton("Play")
        play_button.setProperty('class', 'play_button')
        play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        settings_button = QPushButton("Settings")
        settings_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button_layout.addWidget(play_button)
        button_layout.addWidget(settings_button)

        layout.addStretch()
        layout.addLayout(button_layout)
        self.setLayout(layout)


class ScrollableGrid(QWidget):
    def __init__(self, field_type: FieldType, card_width=200, card_height=100):
        """ Create a scrollable grid which changes number of columns oon resize. Either it contains instances or mods (field_type). """
        super().__init__()
        self.field_type = field_type
        self.card_width = card_width
        self.card_height = card_height
        self.fields = []
        self.values = []
        self.current_columns = 0

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

        # Initial layout
        self.grid_layout = QGridLayout()
        self.grid_layout.setHorizontalSpacing(10)
        self.grid_layout.setVerticalSpacing(30)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.content_widget.setLayout(self.grid_layout)
        self.rebuild_grid()

    def actualize_values(self, values: list[str]):
        """ Refresh the table using new values. Either they are instance names or mod icon file paths. """
        self.values = values

        if self.field_type == FieldType.INSTANCES:
            for name in self.values:
                field = InstanceField(name, width=self.card_width, height=self.card_height)
                self.fields.append(field)

        self.rebuild_grid()


    def rebuild_grid(self):
        width = self.scroll_area.viewport().width() - 10
        columns = max(1, width // (self.card_width + 10))

        if columns == self.current_columns:  # If nothing changes then return
            return
        self.current_columns = columns

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for index, field in enumerate(self.fields):
            row = index // columns
            col = index % columns
            self.grid_layout.addWidget(field, row, col)

    def resizeEvent(self, event):  # On resize check whether to rebuild the grid
        super().resizeEvent(event)
        self.rebuild_grid()

