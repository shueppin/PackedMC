from enum import Enum
from typing import Callable

from PyQt6.QtWidgets import QWidget, QGridLayout, QScrollArea, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QEvent


class FieldType(Enum):
    INSTANCES = "Instances"
    MODS_EDIT = "Mods Edit"  # For the mods page
    MODS_DISPLAY = "Mods Display"  # For the instances page, to just display


class InstanceFieldFunctions:
    def __init__(self, play_function: Callable[[str], None], edit_function: Callable[[str], None], create_new_function: Callable[[], None]):
        """ Object to keep track of the functions to execute. Every function gets the instance name as the first argument. """
        self.play_function = play_function
        self.edit_function = edit_function
        self.create_new_instance_function = create_new_function


class ModFieldFunctions:
    def __init__(self, edit_function: Callable[[str], None], create_new_function: Callable[[str], None], display_function: Callable[[str], None]):
        self.edit_function = edit_function
        self.create_new_function = create_new_function
        self.display_function = display_function


class _CreateNewElementButton(QPushButton):
    def __init__(self, creation_function: Callable[[], None], displayed_text: str, width=200, height=100):
        super().__init__()

        self.setFixedSize(width, height)

        self.setText(displayed_text)
        self.setProperty('class', 'create_new_element_button')

        self.clicked.connect(lambda: creation_function())


class _InstanceField(QFrame):
    def __init__(self, instance_name: str, instance_field_functions: InstanceFieldFunctions, width=200, height=100):
        super().__init__()
        #self.setFrameShape(QFrame.Shape.StyledPanel)
        #self.setLineWidth(2)
        self.setFixedSize(width, height)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        name_label = QLabel(instance_name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setProperty('class', 'instance_label')
        layout.addWidget(name_label)

        button_layout = QHBoxLayout()
        play_button = QPushButton("Play")
        play_button.setProperty('class', 'play_button')
        play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        play_button.clicked.connect(lambda: instance_field_functions.play_function(instance_name))
        edit_button = QPushButton("Edit")
        edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_button.clicked.connect(lambda: instance_field_functions.edit_function(instance_name))
        button_layout.addWidget(play_button)
        button_layout.addWidget(edit_button)

        layout.addStretch()
        layout.addLayout(button_layout)
        self.setLayout(layout)


class _ModField(QFrame):
    # TODO: Modify to show an image under the label. Set the on_click_function to either mod_edit (when on mods page) or mod_select (when in instance edit)
    def __init__(self, mod_name: str, on_press_function: Callable[[str | None], None], width=200, height=100):
        super().__init__()
        self.mod_name = mod_name
        self.on_press_function = on_press_function

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(2)
        self.setFixedSize(width, height)
        self.setProperty('class', 'clickable_frame')

        # Enable hover + cursor
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        label = QLabel(mod_name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        self.setLayout(layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_press_function(self.mod_name)
        super().mousePressEvent(event)

# TODO: Add Mod Field


class ScrollableGrid(QWidget):
    def __init__(self, field_type: FieldType, available_functions: InstanceFieldFunctions | ModFieldFunctions, card_width=200, card_height=100):
        """ Create a scrollable grid which changes number of columns on resize. Either it contains instances or mods (field_type). """
        super().__init__()
        self.field_type = field_type
        self.card_width = card_width
        self.card_height = card_height
        self.fields = []
        self.values = []
        self.current_columns = 0
        self.available_functions = available_functions

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
        self.set_spacing()
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.content_widget.setLayout(self.grid_layout)
        self.rebuild_grid()

    def set_spacing(self, horizontal_spacing=10, vertical_spacing=30):
        self.grid_layout.setHorizontalSpacing(horizontal_spacing)
        self.grid_layout.setVerticalSpacing(vertical_spacing)

    def set_size(self, width=200, height=100):
        self.card_width = width
        self.card_height = height
        self.set_values(self.values)  # Refresh the values, to recreate the fields

    def set_values(self, values: list[str]):
        """ Refresh the table using new values. Either they are instance names or mod icon file paths. """
        # Remove all the fields
        for field in self.fields:
            self.grid_layout.removeWidget(field)
            field.deleteLater()  # Properly destroy the widget

        self.fields.clear()

        # Add the new values
        self.values = values

        if self.field_type == FieldType.INSTANCES:
            for name in self.values:
                field = _InstanceField(name, self.available_functions, width=self.card_width, height=self.card_height)
                self.fields.append(field)
            create_new_instance_button = _CreateNewElementButton(self.available_functions.create_new_instance_function, 'Create new\ninstance', self.card_width, self.card_height)
            self.fields.append(create_new_instance_button)

        # TODO: Create Mod Fields (either for display mode or in edit mode)

        self.rebuild_grid(force=True)

    def rebuild_grid(self, force=False):
        width = self.scroll_area.viewport().width() - 10
        columns = max(1, width // (self.card_width + 10))

        if columns == self.current_columns and not force:  # If nothing changes then return
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

