import logging
from enum import Enum
from typing import Callable
import os

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QGridLayout, QScrollArea, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QComboBox
# noinspection PyPackageRequirements
from PyQt6.QtGui import QPixmap
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt


logger = logging.getLogger(__name__)


class FieldType(Enum):
    INSTANCES = "Instances"
    MODS_EDITABLE = "Mods Editable"  # For the mods page
    MODS_DISPLAYED = "Mods Displayed"  # For the instances page, to just display. When clicked they execute "display_function".


class DynamicInstanceFieldHelper:
    """ Object to keep track of the functions to execute. """
    play_function: Callable[[str], None]
    edit_function: Callable[[str], None]
    create_new_function: Callable[[], None]
    import_profiles_function: Callable[[], None]


class DynamicModFieldHelper:
    """ Object to keep track of the functions to execute and the values that are needed. """
    edit_function: Callable[[str], None]
    create_new_function: Callable[[], None]
    display_function: Callable[[str, bool], None]
    available_tags: list[str]
    tag_check_function: Callable[[str, str], bool]  # Function to check whether the mod should be displayed based on the mod name and the actual selected tag


def _check_if_all_attributes_defined(cls: type[DynamicInstanceFieldHelper | DynamicModFieldHelper]):
    for name in cls.__annotations__:  # Go through all attributes
        if not name.startswith("_") and not hasattr(cls, name):
            logger.error(f"Helper class {cls.__name__} has no attribute '{name}'. Please set this before creating the dynamic widget.")


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
    def __init__(self, instance_name: str, width=200, height=100):
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
        play_button.clicked.connect(lambda: DynamicInstanceFieldHelper.play_function(instance_name))
        edit_button = QPushButton("Edit")
        edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        # noinspection PyUnresolvedReferences
        edit_button.clicked.connect(lambda: DynamicInstanceFieldHelper.edit_function(instance_name))
        button_layout.addWidget(play_button)
        button_layout.addWidget(edit_button)

        layout.addStretch()
        layout.addLayout(button_layout)
        self.setLayout(layout)


class _ModField(QFrame):
    def __init__(self, mod_name: str, mod_icon_path: str, only_displayed=False, is_selected=False, width=200, height=100):
        super().__init__()
        self.mod_name = mod_name
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
                DynamicModFieldHelper.display_function(self.mod_name, self.is_selected)
            else:
                DynamicModFieldHelper.edit_function(self.mod_name)
        super().mousePressEvent(event)


class ScrollableGrid(QWidget):
    def __init__(self, field_type: FieldType, card_width=200, card_height=100):
        """ Create a scrollable grid which changes number of columns on resize. Either it contains instances or mods (field_type). """
        super().__init__()
        self.field_type = field_type
        self.card_width = card_width
        self.card_height = card_height
        self.fields = []
        self.values = []
        self.current_columns = 0
        self.selected_tag = "All tags"

        # Check if the functions match the field type
        if field_type == FieldType.INSTANCES:
            _check_if_all_attributes_defined(DynamicInstanceFieldHelper)
        elif field_type == FieldType.MODS_DISPLAYED or field_type == FieldType.MODS_EDITABLE:
            _check_if_all_attributes_defined(DynamicModFieldHelper)
        else:
            logger.error(f'Field type "{field_type}" is not supported.')

        # Tag selector
        self.tags_combo_box = QComboBox()
        self.tags_combo_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.tags_combo_box.setMinimumWidth(self.tags_combo_box.sizeHint().width() + 30)
        self.tags_combo_box.currentTextChanged.connect(self._selected_tag_changed)

        # Only show tag selector for mods
        if self.field_type in (FieldType.MODS_DISPLAYED, FieldType.MODS_EDITABLE):
            self.tags_combo_box.show()
        else:
            self.tags_combo_box.hide()

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        # Grid
        self.grid_layout = QGridLayout()
        self.set_spacing()
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.content_widget.setLayout(self.grid_layout)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tags_combo_box, alignment=Qt.AlignmentFlag.AlignLeft)
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

        # Initial layout (also rebuilds grid)
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

        # Refresh the tag list
        self.tags_combo_box.blockSignals(True)
        self.tags_combo_box.clear()
        self.tags_combo_box.addItem("All tags")
        self.tags_combo_box.addItems(DynamicModFieldHelper.available_tags)

        index = self.tags_combo_box.findText(self.selected_tag)
        if index >= 0:
            self.tags_combo_box.setCurrentIndex(index)
        else:
            self.selected_tag = 'All tags'  # If the actual tag is not found, use the default one
        self.tags_combo_box.blockSignals(False)

        # Add the new values
        self.values = values

        if self.field_type == FieldType.INSTANCES:
            for name in self.values:
                field = _InstanceField(name, width=self.card_width, height=self.card_height)
                self.fields.append(field)
            create_new_instance_button = _CreateNewElementButton(DynamicInstanceFieldHelper.create_new_function, 'Create new\ninstance', self.card_width, self.card_height)
            self.fields.append(create_new_instance_button)
            import_profiles_button = _CreateNewElementButton(DynamicInstanceFieldHelper.import_profiles_function, 'Import profiles\nfrom Launcher', self.card_width, self.card_height)
            self.fields.append(import_profiles_button)

        elif self.field_type == FieldType.MODS_DISPLAYED:
            for i in range(len(values)):
                try:
                    name, mod_icon_path, is_selected = values[i]
                    if self.selected_tag == 'All tags' or DynamicModFieldHelper.tag_check_function(name, self.selected_tag):
                        field = _ModField(name, mod_icon_path, only_displayed=True, is_selected=is_selected, width=self.card_width, height=self.card_height)
                        self.fields.append(field)
                except ValueError:
                    logger.warning(f'{FieldType.MODS_DISPLAYED.name} expects values like "(name, icon_path, is_selected)", but got {values[i]} instead')
                except Exception as e:
                    print(type(e), e)

        elif self.field_type == FieldType.MODS_EDITABLE:
            for i in range(len(values)):
                try:
                    name, mod_icon_path = values[i]
                    if self.selected_tag == 'All tags' or DynamicModFieldHelper.tag_check_function(name, self.selected_tag):
                        field = _ModField(name, mod_icon_path, width=self.card_width, height=self.card_height)
                        self.fields.append(field)
                except ValueError:
                    logger.warning(f'{FieldType.MODS_EDITABLE.name} expects values like "(name, icon_path)", but got {values[i]} instead')
                except Exception as e:
                    print(type(e), e)
            create_new_mod_button = _CreateNewElementButton(DynamicModFieldHelper.create_new_function, 'Create new\nmod', self.card_width, self.card_height)
            self.fields.append(create_new_mod_button)

        # Rebuild the layout of the fields
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

    def _selected_tag_changed(self, tag: str):
        self.selected_tag = tag
        self.set_values(self.values)  # This is used to display the right fields and rebuild the grid
