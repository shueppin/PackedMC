import sys

from PyQt6.QtWidgets import QApplication

from interface.interface import MainWindow


app = QApplication(sys.argv)
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
