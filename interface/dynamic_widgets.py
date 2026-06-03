import logging
from enum import Enum
from typing import Callable
import os

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QGridLayout, QScrollArea, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
# noinspection PyPackageRequirements
from PyQt6.QtGui import QPixmap
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt


logger = logging.getLogger(__name__)


class FieldType(Enum):
    INSTANCES = "Instances"
    MODS_EDITABLE = "Mods Editable"  # For the mods page
    MODS_DISPLAYED = "Mods Displayed"  # For the instances page, to just display. When clicked they execute "display_function".


class InstanceFieldFunctions:
    def __init__(self, play_function: Callable[[str], None], edit_function: Callable[[str], None], create_new_function: Callable[[], None], import_profiles_function: Callable[[], None]):
        """ Object to keep track of the functions to execute. Every function gets the instance name as the first argument. """
        self.play_function = play_function
        self.edit_function = edit_function
        self.create_new_function = create_new_function
        self.import_profiles_function = import_profiles_function


class ModFieldFunctions:
    def __init__(self, edit_function: Callable[[str], None], create_new_function: Callable[[], None], display_function: Callable[[str, bool], None]):
        self.edit_function = edit_function
        self.create_new_function = create_new_function
        self.display_function = display_function


class _CreateNewElementButton(QPushButton):
    def __init__(self, creation_function: Callable[[], None], displayed_text: str, width=200, height=100):
        super().__init__()

        self.setFixedSize(width, height)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setText(displayed_text)
        self.setProperty('class', 'create_new_element_button')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.clicked.connect(lambda: creation_function())


class _InstanceField(QFrame):
    def __init__(self, instance_name: str, instance_field_functions: InstanceFieldFunctions, width=200, height=100):
        super().__init__()
        self.setFixedSize(width, height)

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        name_label = QLabel(instance_name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setProperty('class', 'bigger_text')
        layout.addWidget(name_label)

        button_layout = QHBoxLayout()
        play_button = QPushButton("Play")
        play_button.setProperty('class', 'play_button')
        play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # noinspection PyUnresolvedReferences
        play_button.clicked.connect(lambda: instance_field_functions.play_function(instance_name))
        edit_button = QPushButton("Edit")
        edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # noinspection PyUnresolvedReferences
        edit_button.clicked.connect(lambda: instance_field_functions.edit_function(instance_name))
        button_layout.addWidget(play_button)
        button_layout.addWidget(edit_button)

        layout.addStretch()
        layout.addLayout(button_layout)
        self.setLayout(layout)


class _ModField(QFrame):
    def __init__(self, mod_name: str, mod_icon_path: str, mod_field_functions: ModFieldFunctions, only_displayed=False, is_selected=False, width=200, height=100):
        super().__init__()
        self.mod_name = mod_name
        self.mod_field_functions = mod_field_functions
        self.only_displayed = only_displayed
        self.is_selected = is_selected

        self.setFixedSize(width, height)

        # Enable hover + cursor
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if mod_icon_path:
            if os.path.exists(mod_icon_path):
                # Icon
                icon_label = QLabel()
                pixmap = QPixmap(mod_icon_path).scaled(round(0.6*height), round(0.8*width), Qt.AspectRatioMode.KeepAspectRatio)
                icon_label.setPixmap(pixmap)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(icon_label)
            else:
                logger.warning("Could not find mod icon at: " + mod_icon_path)

        # Name
        label = QLabel(mod_name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty('class', 'bigger_text')
        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        self.setLayout(layout)

        self._set_correct_properties()

    def _set_correct_properties(self):
        # Set the properties and reapply the style
        if self.is_selected:
            self.setProperty('class', 'clickable_frame_selected')
        else:
            self.setProperty('class', 'clickable_frame_unselected')
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # If it is only displayed, it means it should be selectable, thus toggle the actual state and execute the display function. Otherwise, execute the edit function.
            if self.only_displayed:
                self.is_selected = not self.is_selected
                self._set_correct_properties()
                self.mod_field_functions.display_function(self.mod_name, self.is_selected)
            else:
                self.mod_field_functions.edit_function(self.mod_name)
        super().mousePressEvent(event)


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

        # Check if the functions match the field type
        if field_type == FieldType.INSTANCES:
            if not isinstance(available_functions, InstanceFieldFunctions):
                logger.error(f'Field type "{field_type.name}" expected InstanceFieldFunctions, not {type(available_functions)}')
        elif field_type == FieldType.MODS_DISPLAYED or field_type == FieldType.MODS_EDITABLE:
            if not isinstance(available_functions, ModFieldFunctions):
                logger.error(f'Field type "{field_type.name}" expected InstanceFieldFunctions, not {type(available_functions)}')
        else:
            logger.error(f'Field type "{field_type}" is not supported.')

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

    def set_values(self, values: list[str | tuple[str, str] | tuple[str, str, bool]]):
        """
        Refresh the table using new values. The values need to match the field_type of the Grid.
        Instance Fields need the name, Editable Mod Fields need the name and icon, and Displayed Mod Fields need the name, icon and whether they are selected or not.

        :param values: A list containing arbitrarily many: "instance name" or "(mod name, mod icon file path)" or "(mod name, mod icon file path, is_selected)"
        """
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
            create_new_instance_button = _CreateNewElementButton(self.available_functions.create_new_function, 'Create new\ninstance', self.card_width, self.card_height)
            self.fields.append(create_new_instance_button)
            import_profiles_button = _CreateNewElementButton(self.available_functions.import_profiles_function, 'Import profiles\nfrom Launcher', self.card_width, self.card_height)
            self.fields.append(import_profiles_button)

        elif self.field_type == FieldType.MODS_DISPLAYED:
            for i in range(len(values)):
                try:
                    name, mod_icon_path, is_selected = values[i]
                    field = _ModField(name, mod_icon_path, self.available_functions, only_displayed=True, is_selected=is_selected, width=self.card_width, height=self.card_height)
                    self.fields.append(field)
                except ValueError:
                    logger.warning(f'{FieldType.MODS_DISPLAYED.name} expects values like "(name, icon_path, is_selected)", but got {values[i]} instead')

        elif self.field_type == FieldType.MODS_EDITABLE:
            for i in range(len(values)):
                try:
                    name, mod_icon_path = values[i]
                    field = _ModField(name, mod_icon_path, self.available_functions, width=self.card_width, height=self.card_height)
                    self.fields.append(field)
                except ValueError:
                    logger.warning(f'{FieldType.MODS_EDITABLE.name} expects values like "(name, icon_path)", but got {values[i]} instead')
            create_new_mod_button = _CreateNewElementButton(self.available_functions.create_new_function, 'Create new\nmod', self.card_width, self.card_height)
            self.fields.append(create_new_mod_button)

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
