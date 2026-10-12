import sys
import logging
import subprocess
from pathlib import Path
import traceback
from datetime import datetime

# noinspection PyPackageRequirements
from PyQt6.QtGui import QIcon
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QApplication

# This is a fix to allow this project to use relative imports when run via a portable python instance
sys.path.insert(0, str(Path(__file__).resolve().parent))

from interface import MainWindow
from utils.file_paths import UPDATER_FILE_PATH, ICONS_FILE_PATH


# TODO: Change the whole mods file system, to have less duplicate files
# TODO: Allow manual mod file adding: Instead of using a link for the mod, we add a file (via the explorer). Then we specify the version (using checkboxes) and the loader.
# TODO: Add modpack support
# TODO: Add Forge support
# TODO: Add system to allow marking instances as favourite
# TODO: Show which mods have been updated
# TODO: Download and enable mod dependencies after showing a popup


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)


# Error Handling, so pyqt does not silently fail in the background
def excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("Unhandled exception:\n%s", msg)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("crash.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}]\n{msg}\n")


sys.excepthook = excepthook


# Launch updater in background
def launch_background(script_path, args=None):
    script_path = Path(script_path)
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd += list(args)

    subprocess.Popen(  # Take the output to the main console
        cmd,
        start_new_session=True,  # mostly helps on Unix/POSIX
    )


launch_background(UPDATER_FILE_PATH)


app = QApplication(sys.argv)
icon_path = str((ICONS_FILE_PATH / 'logo.png').resolve())
app.setWindowIcon(QIcon(icon_path))
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
