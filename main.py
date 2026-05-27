import sys
import logging

from PyQt6.QtWidgets import QApplication

from interface import MainWindow


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)

app = QApplication(sys.argv)
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
