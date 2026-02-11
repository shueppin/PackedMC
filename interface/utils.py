from enum import Enum
import os
import json

from PyQt6.QtCore import QObject, QEvent, QSize, QPropertyAnimation, QParallelAnimationGroup, QPoint, QEasingCurve
from PyQt6.QtWidgets import QMainWindow, QWidget, QRadioButton, QCheckBox, QPushButton, QStackedWidget, QTableWidget, QHeaderView


class StoredDict(dict):
    def __init__(self, filepath: str, *args, **kwargs):
        # Initialize the base dictionary
        super().__init__(*args, **kwargs)

        # Store the filepath
        self.filepath = filepath

        # Load existing data if the file exists
        if os.path.exists(filepath):
            self.load()

        self.save()

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(dict(self), f, indent=4)
        except IOError as e:
            print(f"Error saving dictionary: {e}")

    def load(self):
        try:
            with open(self.filepath, "r") as f:
                loaded_data = json.load(f)
                # Clear existing items and update with loaded data
                self.clear()
                self.update(loaded_data)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading dictionary: {e}")


'''
PyQt Animation
'''

class ScrollDirection(Enum):
    HORIZONTAL = 'Horizontal'
    VERTICAL = 'Vertical'


def animate_transition(main_window: QMainWindow, stacked_widget: QStackedWidget, new_index: int, animation_duration=300, animation_direction: ScrollDirection=ScrollDirection.VERTICAL) -> bool:
    """
    Function to animate the transition between pages of a stacked widget

    :param main_window: The Main Window
    :param stacked_widget: The stacked widget which contains the pages
    :param new_index: The index of the new page
    :param animation_duration: The animation duration in ms
    :param animation_direction: The direction of the animation (horizontal or vertical)
    :return: Returns True if it is still animating from before, otherwise returns False
    """
    # Test if the variable "is_animating" exists (so that we get no error) and set it to True, so that no animation of this stacked_widget can be started.
    if hasattr(stacked_widget, 'is_animating'):
        if stacked_widget.is_animating:
            return True
        else:
            stacked_widget.is_animating = True
    else:
        stacked_widget.is_animating = True

    # Get the current index and check if it is valid.
    current_index = stacked_widget.currentIndex()

    if current_index == new_index or not 0 <= current_index <= stacked_widget.count():
        stacked_widget.is_animating = False
        return False

    # Set the animation direction and distance
    if animation_direction == ScrollDirection.HORIZONTAL:
        if current_index > new_index:
            offset = QPoint(stacked_widget.width(), 0)
        else:
            offset = QPoint(-stacked_widget.width(), 0)

    else:
        # Vertical
        if current_index > new_index:
            offset = QPoint(0, stacked_widget.height())
        else:
            offset = QPoint(0, -stacked_widget.height())

    # Get the pages
    current_page = stacked_widget.currentWidget()
    new_page = stacked_widget.widget(new_index)

    # Modify the new page
    new_page.setGeometry(stacked_widget.geometry())
    new_page.move(new_page.pos() - offset)
    new_page.show()
    # new_page.raise_()

    # Define both animations
    animation_current_page = QPropertyAnimation(current_page, b"pos")
    animation_current_page.setDuration(animation_duration)
    animation_current_page.setEasingCurve(QEasingCurve.Type.InOutCubic)
    animation_current_page.setStartValue(current_page.pos())
    animation_current_page.setEndValue(current_page.pos() + offset)

    animation_new_page = QPropertyAnimation(new_page, b"pos")
    animation_new_page.setDuration(animation_duration)
    animation_new_page.setEasingCurve(QEasingCurve.Type.InOutCubic)
    animation_new_page.setStartValue(current_page.pos() - offset)
    animation_new_page.setEndValue(current_page.pos())

    # Define and start the animation group
    animation_group = QParallelAnimationGroup(main_window, finished=lambda: _animation_done(stacked_widget, new_index))

    animation_group.addAnimation(animation_current_page)
    animation_group.addAnimation(animation_new_page)

    animation_group.start()
    return False


# Cleanup function for when the animation is done
def _animation_done(stacked_widget: QStackedWidget, new_index):
    stacked_widget.setCurrentIndex(new_index)
    stacked_widget.is_animating = False