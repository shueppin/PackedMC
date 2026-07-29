import logging
import re
import validators

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMessageBox
# noinspection PyPackageRequirements
from PyQt6.QtCore import QTimer, QObject, pyqtSignal

from .utils import AnimationScrollDirection

from minecraft_api.mod import get_mod_data, InvalidModBaseUrl, ModNotExisting

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


# Signal Emitter for when the data of a mod was loaded from the API
class _ModDataConnector(QObject):
    updated = pyqtSignal(str, list, list, str, str)  # declared on class

    def emit_updated(self, description: str, loaders: list[str], supported_versions: list[str], mod_name: str, mod_url: str):
        # noinspection PyUnresolvedReferences
        self.updated.emit(description, loaders, supported_versions, mod_name, mod_url)


class ModPageClass:
    def __init__(self, parent: MainWindow):
        self.parent: MainWindow = parent
        self.data = parent.data

        # Create intern variables
        self.selected_mod_name = ''

        self.mod_url_timer = QTimer(parent)  # Use a timer that is restarted on every text input, but the real function is only executed after the time has run out.
        self.mod_url_timer.setSingleShot(True)
        # noinspection PyUnresolvedReferences
        self.mod_url_timer.timeout.connect(self._changed_mod_url)
        self.mod_data_connector = _ModDataConnector()
        # noinspection PyUnresolvedReferences
        self.mod_data_connector.updated.connect(lambda description, loaders, supported_versions, mod_name, mod_url: self.set_mod_values(description, loaders, supported_versions, mod_name, mod_url))

        # Connect the widgets
        parent.MODS_BACK_BUTTON.clicked.connect(lambda: parent.show_page(2, animation_direction=AnimationScrollDirection.HORIZONTAL))
        parent.MOD_NAME.textChanged.connect(self._changed_mod_name)
        parent.MOD_URL.textChanged.connect(lambda: self.mod_url_timer.start(500))
        parent.DELETE_MOD_BUTTON.clicked.connect(self._delete_mod)

    def create_mod(self, mod_name='New Mod', edit_afterwards=True):
        mod_name = self.parent.make_name_unique(mod_name, list(self.data['mods'].keys()))

        # Set the data
        self.data['mods'][mod_name] = {
            'url': '',
            'loaders': [],
            'supported_versions': [],
        }
        self.data.save()

        if edit_afterwards:
            self.edit_mod(mod_name)  # Show it in edit mode

    def edit_mod(self, mod_name: str):
        """ This function is executed to show the edit page and configure the values for the given instance. """
        parent = self.parent

        parent.show_page(3, animation_direction=AnimationScrollDirection.HORIZONTAL)

        # Set the values for the edit page
        self.selected_mod_name = mod_name
        mod_url: str = self.data['mods'][mod_name]['url']

        # Set the name without triggering the changed_instance_data function (which triggers on text change)
        parent.MOD_NAME.blockSignals(True)
        parent.MOD_NAME.setText(mod_name)
        parent.MOD_NAME.setFocus()  # Prevent highlighting
        parent.MOD_NAME.blockSignals(False)

        parent.MOD_URL.blockSignals(True)
        parent.MOD_URL.setText(mod_url)
        parent.MOD_URL.blockSignals(False)

        # Set the fields depending on the URL and also refresh the stored data
        try:
            description, loaders, supported_versions = get_mod_data(mod_url, self.mod_data_connector.emit_updated, (mod_name, mod_url))
            self.set_mod_values(description, loaders, supported_versions, mod_name, mod_url)
        except ModNotExisting:
            self.set_mod_values('', [], [], mod_name, mod_url)
        except InvalidModBaseUrl:
            self.set_mod_values('', [], [], mod_name, mod_url)
        except Exception as e:
            logger.error('Uncaught exception when changing editing mod', exc_info=e)

    def set_mod_values(self, description: str, loaders: list[str], supported_versions: list[str], mod_name: str, mod_url: str):
        """ If the URL of the given mod matches, then store the given values for said mod. Then display them, if it is the selected mod. """
        if mod_name not in self.data['mods']:  # This means the mod was probably renamed. Then take the selected mod and check if it is this URL
            mod_name = self.selected_mod_name

        if self.data['mods'][mod_name]['url'] != mod_url:
            logger.info("Mod URL changed in the meantime. Callback is discarded.")
            return

        self.data['mods'][mod_name]['loaders'] = loaders
        self.data['mods'][mod_name]['supported_versions'] = supported_versions
        self.data.save()

        clean_description = re.sub(r'<img\b[^>]*>', '', description, flags=re.IGNORECASE)  # Remove the images from the HTML, so no need to load them.
        self.parent.MOD_DESCRIPTION.setHtml(clean_description)
        self.parent.MOD_LOADER.setText('\n'.join(loaders))
        self.parent.MOD_VERSIONS.setText('\n'.join(supported_versions))

    def _changed_mod_name(self):
        # Get the old and the new mod name
        old_mod_name = self.selected_mod_name
        new_mod_name = self.parent.MOD_NAME.text().strip()

        # If the clean new name is empty then it means it was cleared, which is allowed since the user can rewrite the whole name.
        if new_mod_name == '':
            new_mod_name = 'Mod Name'

        # First get the data and only then make the name unique, to avoid mistakes when the name already exists, because of itself
        mod_data = self.data['mods'].pop(old_mod_name)

        new_mod_name = self.parent.make_name_unique(new_mod_name, list(self.data['mods'].keys()))

        # Update the mod name and data
        self.data['mods'][new_mod_name] = mod_data
        self.selected_mod_name = new_mod_name

        # Update the mod name in every instance
        for instance_name in self.data['instances']:
            if old_mod_name in self.data['instances'][instance_name]['mods']:
                mod_download_url = self.data['instances'][instance_name]['mods'].pop(old_mod_name)  # Load the old value and use it with the key of the new value
                self.data['instances'][instance_name]['mods'][new_mod_name] = mod_download_url
        self.data.save()

    def _changed_mod_url(self):
        # This function is only executed after a timer has run out, so after there were no keystrokes in 0.5 seconds.
        new_url = self.parent.MOD_URL.text().strip()
        self.data['mods'][self.selected_mod_name]['url'] = new_url
        self.data.save()
        if validators.url(new_url):
            try:
                description, loaders, supported_versions = get_mod_data(new_url, self.mod_data_connector.emit_updated, (self.selected_mod_name, new_url))
                self.set_mod_values(description, loaders, supported_versions, self.selected_mod_name, new_url)
            except ModNotExisting:
                pass
            except InvalidModBaseUrl:
                pass
            except Exception as e:
                logger.error('Uncaught exception when changing mod URL', exc_info=e)
        else:
            pass
        # TODO: Change color of input field when it is an invalid URL

    def _delete_mod(self):
        # Ask to delete it
        reply = QMessageBox.question(self.parent, 'Confirm deletion', f'Do you really want to delete the mod "{self.selected_mod_name}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            del self.data['mods'][self.selected_mod_name]
            # Remove the mod from every instance
            for instance_name in self.data['instances']:
                if self.selected_mod_name in self.data['instances'][instance_name]['mods']:
                    del self.data['instances'][instance_name]['mods'][self.selected_mod_name]
            self.data.save()

            # Go to the mods page
            self.parent.show_page(2, animation_direction=AnimationScrollDirection.HORIZONTAL)