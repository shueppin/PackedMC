import sys
import logging

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QApplication

from interface import MainWindow


# TODO: Check for PackedMC updates in a thread
# TODO: Change the whole file system, to have less duplicate mods


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)

app = QApplication(sys.argv)
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
