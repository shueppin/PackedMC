import logging
from enum import Enum
from typing import Callable
import os

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QGridLayout, QScrollArea, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QComboBox, QListWidget, QLineEdit, QListWidgetItem, QApplication
# noinspection PyPackageRequirements
from PyQt6.QtGui import QPixmap
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt, QPoint, QEvent

from modrinth_search import ModrinthSearcher, ModrinthIconLoader, MODRINTH_BASE_MOD_URL


DEFAULT_ALL_TAGS_NAME = 'All tags'
DEFAULT_NO_TAGS_NAME = 'Mods without tag'


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


class ModrinthResultWidget(QWidget):
    def __init__(self, project: dict, parent=None):
        super().__init__(parent)

        self.project = project

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(48, 48)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText("")

        title = project.get("title") or project.get("slug") or "Unknown mod"

        downloads = f"{project.get('downloads', '-1'):_} Downloads".replace("_", "'")  # Display the downloads with ' as separator between thousands
        info = f"{downloads:<35}"  # Ensure the string is at least 35 characters long (pad the rest with spaces)
        info += "Author: " + project.get("author") or "Unknown"

        description = " ".join(project.get("description", "").split())

        if len(description) > 150:
            description = f"{description[:147]}..."

        self.title_label = QLabel(title)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600;")

        self.info_label = QLabel(info)
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.info_label)
        text_layout.addWidget(self.description_label)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(8, 7, 8, 7)
        content_layout.setSpacing(10)
        content_layout.addWidget(self.icon_label)
        content_layout.addLayout(text_layout, 1)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content_layout)
        layout.addWidget(separator)

        self.setLayout(layout)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_icon(self, pixmap):
        if pixmap.isNull():
            return

        # Incase the label has been deleted, then just ignore this
        if self.icon_label is None:
            return

        try:
            self.icon_label.setPixmap(pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except RuntimeError:
            # This is mostly because of the error message "wrapped C/C++ object of type QLabel has been deleted", regarding the pixmap.
            pass


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
        self.selected_tag = DEFAULT_ALL_TAGS_NAME
        self.search_text = ""
        self.modrinth_overlay_shown = False

        # Check if the functions match the field type
        if field_type == FieldType.INSTANCES:
            _check_if_all_attributes_defined(DynamicInstanceFieldHelper)
        elif field_type in (FieldType.MODS_DISPLAYED, FieldType.MODS_EDITABLE):
            _check_if_all_attributes_defined(DynamicModFieldHelper)
        else:
            logger.error(f'Field type "{field_type}" is not supported.')

        # Tag selector
        self.tags_combo_box = QComboBox()
        # noinspection PyUnresolvedReferences
        self.tags_combo_box.currentTextChanged.connect(self._selected_tag_changed)

        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText("Search local / Modrinth mods...")
        # noinspection PyUnresolvedReferences
        self.search_line_edit.textChanged.connect(self._search_text_changed)
        # noinspection PyUnresolvedReferences
        self.search_line_edit.returnPressed.connect(self._search_enter_pressed)
        self.search_line_edit.setClearButtonEnabled(True)

        self.controls_widget = QWidget()
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self.tags_combo_box)
        controls_layout.addWidget(self.search_line_edit, 1)
        self.controls_widget.setLayout(controls_layout)

        if field_type not in (FieldType.MODS_DISPLAYED, FieldType.MODS_EDITABLE):
            self.controls_widget.hide()

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
        main_layout.setContentsMargins(0, 10, 0, 0)
        main_layout.addWidget(self.controls_widget)
        main_layout.addWidget(self.scroll_area)
        self.setLayout(main_layout)

        # Modrinth search overlay
        self.modrinth_overlay = QFrame(self)
        self.modrinth_overlay.setObjectName("ModrinthSearchOverlay")
        self.modrinth_overlay.setFrameShape(QFrame.Shape.StyledPanel)

        overlay_layout = QVBoxLayout()
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        overlay_layout.setSpacing(6)
        self.modrinth_overlay.setLayout(overlay_layout)

        self.modrinth_hint_label = QLabel("Press Enter to search only local mods")
        overlay_layout.addWidget(self.modrinth_hint_label)

        self.modrinth_status_label = QLabel()
        overlay_layout.addWidget(self.modrinth_status_label)

        self.modrinth_results_list = QListWidget()
        # noinspection PyUnresolvedReferences
        self.modrinth_results_list.itemClicked.connect(self._modrinth_result_clicked)
        overlay_layout.addWidget(self.modrinth_results_list, 1)

        self.modrinth_overlay.hide()

        self.modrinth_searcher = ModrinthSearcher(self)
        self.modrinth_searcher.search_started.connect(lambda query: self.modrinth_status_label.setText(f'Searching Modrinth for "{query}"...'))
        self.modrinth_searcher.results_ready.connect(self._modrinth_results_ready)
        self.modrinth_searcher.search_failed.connect(self._modrinth_search_failed)

        self.modrinth_icon_loader = ModrinthIconLoader(self)
        self.modrinth_icon_loader.icon_ready.connect(self._modrinth_icon_ready)
        self.modrinth_icon_targets = {}

        # Event listener to close modrinth overlay
        QApplication.instance().installEventFilter(self)

        # Rebuild grid to have initial layout
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
        self.values = values

        if self.field_type in (FieldType.MODS_DISPLAYED, FieldType.MODS_EDITABLE):
            self._refresh_tag_selector()

        self._refresh_visible_fields()

    def _refresh_tag_selector(self):
        self.tags_combo_box.blockSignals(True)
        self.tags_combo_box.clear()
        self.tags_combo_box.addItem(DEFAULT_ALL_TAGS_NAME)
        self.tags_combo_box.addItem(DEFAULT_NO_TAGS_NAME)
        self.tags_combo_box.addItems(DynamicModFieldHelper.available_tags)
        self.tags_combo_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.tags_combo_box.setMinimumWidth(self.tags_combo_box.sizeHint().width() + 20)

        index = self.tags_combo_box.findText(self.selected_tag)
        if index >= 0:
            self.tags_combo_box.setCurrentIndex(index)
        else:
            self.selected_tag = DEFAULT_ALL_TAGS_NAME  # If the actual tag is not found, use the default one

        self.tags_combo_box.blockSignals(False)

    def _refresh_visible_fields(self):
        # Clear the old fields
        for field in self.fields:
            self.grid_layout.removeWidget(field)
            field.deleteLater()

        self.fields.clear()

        # Add the new fields
        if self.field_type == FieldType.INSTANCES:
            for name in self.values:
                self.fields.append(_InstanceField(name, width=self.card_width, height=self.card_height))

            self.fields.append(_CreateNewElementButton(DynamicInstanceFieldHelper.create_new_function, "Create new\ninstance", self.card_width, self.card_height))
            self.fields.append(_CreateNewElementButton(DynamicInstanceFieldHelper.import_profiles_function, "Import profiles\nfrom Launcher", self.card_width, self.card_height))

        elif self.field_type == FieldType.MODS_DISPLAYED:
            for value in self.values:
                try:
                    name, mod_icon_path, is_selected = value
                    if self._mod_matches_filters(name):
                        self.fields.append(_ModField(name, mod_icon_path, only_displayed=True, is_selected=is_selected, width=self.card_width, height=self.card_height))
                except ValueError:
                    logger.warning(f"{FieldType.MODS_DISPLAYED.name} expects values like '(name, icon_path, is_selected)', but got {value} instead")
                except Exception as e:
                    logger.exception("Failed to create displayed mod field: %s", e)

        elif self.field_type == FieldType.MODS_EDITABLE:
            for value in self.values:
                try:
                    name, mod_icon_path = value
                    if self._mod_matches_filters(name):
                        self.fields.append(_ModField(name, mod_icon_path, width=self.card_width, height=self.card_height))
                except ValueError:
                    logger.warning(f"{FieldType.MODS_EDITABLE.name} expects values like '(name, icon_path)', but got {value} instead")
                except Exception as e:
                    logger.exception("Failed to create editable mod field: %s", e)

            self.fields.append(_CreateNewElementButton(DynamicModFieldHelper.create_new_function, "Create new\nmod", self.card_width, self.card_height))

        # Rebuild the layout of the fields
        self.rebuild_grid(force=True)

    def _mod_matches_filters(self, name: str) -> bool:
        if self.selected_tag != DEFAULT_ALL_TAGS_NAME and not DynamicModFieldHelper.tag_check_function(name, self.selected_tag):
            return False

        query = self.search_text.strip().casefold()
        if not query or query in name.casefold():
            return True

        return False

    def rebuild_grid(self, force=False):
        width = self.scroll_area.viewport().width() - 10
        columns = max(1, width // (self.card_width + 10))

        if columns == self.current_columns and not force:  # If nothing changes then return
            self._update_modrinth_overlay_geometry()
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

        self._update_modrinth_overlay_geometry()

    def resizeEvent(self, event):  # On resize check whether to rebuild the grid
        super().resizeEvent(event)
        self.rebuild_grid()
        self._update_modrinth_overlay_geometry()

    def _selected_tag_changed(self, tag: str):
        self.selected_tag = tag
        self._refresh_visible_fields()

    # Search UI
    def _search_text_changed(self, text: str):
        self.search_text = text
        has_text = bool(text.strip())
        self._refresh_visible_fields()

        if not has_text:
            self.modrinth_searcher.cancel()
            self._hide_modrinth_overlay()
            return

        # Don't do any Modrinth actions when not editing mods
        if self.field_type != FieldType.MODS_EDITABLE:
            return

        self.modrinth_results_list.clear()
        self.modrinth_status_label.setText("Searching Modrinth...")
        self._show_modrinth_overlay()
        self.modrinth_searcher.search(text)

    def _search_enter_pressed(self):
        self.search_line_edit.clearFocus()
        self.modrinth_searcher.cancel()
        self._hide_modrinth_overlay()
        self._refresh_visible_fields()

    # Modrinth overlay UI
    def _modrinth_results_ready(self, results: list):
        if not self.modrinth_overlay_shown:
            return

        self.modrinth_results_list.clear()
        self.modrinth_icon_targets.clear()

        if not results:
            self.modrinth_status_label.setText("No Modrinth mods found.")
            return

        self.modrinth_status_label.setText(f"{len(results)} Modrinth result(s)")

        for project in results:
            item = QListWidgetItem()
            widget = ModrinthResultWidget(project)

            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, project)

            self.modrinth_results_list.addItem(item)
            self.modrinth_results_list.setItemWidget(item, widget)

            icon_url = project.get("icon_url")

            if icon_url:
                self.modrinth_icon_targets.setdefault(icon_url, []).append(widget)
                self.modrinth_icon_loader.load(icon_url)

        self._show_modrinth_overlay()

    def _modrinth_search_failed(self, error: str):
        if not self.modrinth_overlay_shown:
            return

        logger.warning("Modrinth search failed: %s", error)
        self.modrinth_status_label.setText("Could not search Modrinth.")

    def _modrinth_result_clicked(self, item: QListWidgetItem):
        project = item.data(Qt.ItemDataRole.UserRole)

        if not isinstance(project, dict):
            return

        self._hide_modrinth_overlay()

        mod_name = project.get("title") or project.get("slug") or "Unknown"
        url = MODRINTH_BASE_MOD_URL + project.get("slug")
        # noinspection PyArgumentList
        # Ignore the exception that these arguments don't exist. This is because they are from the mod page directly for "create_mod"
        DynamicModFieldHelper.create_new_function(mod_name=mod_name, url=url)

    def _show_modrinth_overlay(self):
        # Don't display the overlay when not editing mods
        if self.field_type != FieldType.MODS_EDITABLE:
            return

        self.modrinth_overlay_shown = True

        self._update_modrinth_overlay_geometry()
        self.modrinth_overlay.show()
        self.modrinth_overlay.raise_()

    def _hide_modrinth_overlay(self):
        self.modrinth_overlay_shown = False
        self.modrinth_overlay.hide()

    def _update_modrinth_overlay_geometry(self):
        if not self.search_line_edit.isVisible():
            return

        position = self.search_line_edit.mapTo(self, QPoint(0, self.search_line_edit.height()))
        width = self.search_line_edit.width()
        height = max(160, int(self.scroll_area.height() * 0.5))

        self.modrinth_overlay.setGeometry(position.x(), position.y(), width, height)
        self.modrinth_overlay.raise_()

    def _modrinth_icon_ready(self, url: str, pixmap):
        for widget in self.modrinth_icon_targets.get(url, []):
            widget.set_icon(pixmap)

    # Event filters to close and reopen Modrinth Overlay
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            # Don't do any Modrinth actions when not editing
            if self.field_type != FieldType.MODS_EDITABLE:
                return super().eventFilter(watched, event)

            if watched is self.search_line_edit:
                if self.search_line_edit.text().strip():
                    self._show_modrinth_overlay()

            elif self.modrinth_overlay.isVisible():
                global_pos = event.globalPosition().toPoint()

                overlay_rect = self.modrinth_overlay.rect()
                overlay_top_left = self.modrinth_overlay.mapToGlobal(QPoint(0, 0))
                overlay_rect.moveTopLeft(overlay_top_left)

                search_rect = self.search_line_edit.rect()
                search_top_left = self.search_line_edit.mapToGlobal(QPoint(0, 0))
                search_rect.moveTopLeft(search_top_left)

                if not overlay_rect.contains(global_pos) and not search_rect.contains(global_pos):
                    self._hide_modrinth_overlay()

        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)
