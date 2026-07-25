import sys
import logging

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QApplication

from interface import MainWindow


# TODO: Check for PackedMC updates in a thread
# TODO: Maybe change the whole mods file system, to have less duplicate files
# TODO: Add tags to the mods. They can be set in the mod edit view using CheckButtons. You can sort for them with a dropdown menu inside the dynamic widget.
# TODO: Allow manual mod file adding: Instead of using a link for the mod, we add a file (via the explorer). Then we specify the version (using checkboxes) and the loader.

# TODO: Eventually add modpack support
# TODO: Eventually add Forge support


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)

app = QApplication(sys.argv)
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
