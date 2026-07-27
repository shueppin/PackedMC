import sys
import logging
import subprocess
from pathlib import Path

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QApplication

# This is a fix to allow this project to use relative imports when run via a portable python instance
sys.path.insert(0, str(Path(__file__).resolve().parent))

from interface import MainWindow


# TODO: Maybe change the whole mods file system, to have less duplicate files
# TODO: Add tags to the mods. They can be set in the mod edit view using CheckButtons. You can sort for them with a dropdown menu inside the dynamic widget.
# TODO: Allow manual mod file adding: Instead of using a link for the mod, we add a file (via the explorer). Then we specify the version (using checkboxes) and the loader.

# TODO: Eventually add modpack support
# TODO: Eventually add Forge support


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)


def launch_background(script_path, args=None):
    script_path = Path(script_path)
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd += list(args)

    subprocess.Popen(  # Take the output to the main console
        cmd,
        start_new_session=True,  # mostly helps on Unix/POSIX
    )


launch_background("updater.py")


app = QApplication(sys.argv)
window = MainWindow(app)
window.show()
window.INSTANCES_PAGE.rebuild_grid()
sys.exit(app.exec())
