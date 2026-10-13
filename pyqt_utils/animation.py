import logging
from enum import Enum

# noinspection PyPackageRequirements
from PyQt6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QPoint, QEasingCurve
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMainWindow, QStackedWidget


logger = logging.getLogger(__name__)


'''
PyQt Animation
'''


class AnimationScrollDirection(Enum):
    HORIZONTAL = 'Horizontal'
    VERTICAL = 'Vertical'


def animate_transition(main_window: QMainWindow, stacked_widget: QStackedWidget, new_index: int, animation_duration=300, animation_direction: AnimationScrollDirection = AnimationScrollDirection.VERTICAL) -> bool:
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
    if animation_direction == AnimationScrollDirection.HORIZONTAL:
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
