from enum import Enum
import os
import json
from typing import Callable

from PyQt6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QPoint, QEasingCurve, Qt
from PyQt6.QtWidgets import QMainWindow, QWidget, QRadioButton, QCheckBox, QStackedWidget, QLayout


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

class AnimationScrollDirection(Enum):
    HORIZONTAL = 'Horizontal'
    VERTICAL = 'Vertical'


def animate_transition(main_window: QMainWindow, stacked_widget: QStackedWidget, new_index: int, animation_duration=300, animation_direction: AnimationScrollDirection=AnimationScrollDirection.VERTICAL) -> bool:
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


'''
Create Radiobuttons or Checkboxes in scroll area
'''

class ScrollAreaButtonType(Enum):
    RADIOBUTTON = 'Radiobutton'
    CHECKBOX = 'Checkbox'


def create_buttons_in_scroll_area(scroll_area_content_widget: QWidget, button_name_list: list | tuple, button_selected_criteria: str | int | list | tuple, button_on_click_function: Callable, button_type=ScrollAreaButtonType.RADIOBUTTON):
    """
    This function modifies the content of a scroll area and inserts buttons or a placeholder into it. It also binds the passed function to the click of the button

    :param scroll_area_content_widget: The widget inside the scroll area which contains the content of the scroll area
    :param button_name_list: A list of names for the buttons
    :param button_selected_criteria: For radiobutton: The name of the selected radiobutton; For checkboxes: A list with the names of the selected buttons
    :param button_on_click_function: The function to get executed on button click and in the beginning when the button is selected
    :param button_type: The type of button to create.
    """
    # This is the layout which contains the elements
    layout: QLayout = scroll_area_content_widget.layout()

    # Remove all existing items in the layout except for the Spacer
    for i in range(layout.count() - 1):
        item = layout.itemAt(0)
        item.widget().deleteLater()
        layout.removeItem(item)

    # This part creates the new content
    # If there are no buttons then create a label to show that there are no buttons and if there are buttons then create each of them according to their type
    if not button_name_list:
        return

    # Create a button for every name in the list
    for button_name in button_name_list:
        # Create a radiobutton
        if button_type == ScrollAreaButtonType.RADIOBUTTON:
            button = QRadioButton(button_name)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            # If the button is the selected one then check it and run the function
            if button_name == button_selected_criteria:
                button.setChecked(True)
                button_on_click_function(button, button_name)  # Return the button itself, because if there is just one radiobutton you are able to deselect it. When it is returned you can fix this later.

        # Create a checkbox button
        elif button_type == ScrollAreaButtonType.CHECKBOX:
            button = QCheckBox(button_name)

            # If the button is in the list of selected ones then check it and run the function
            if button_name in button_selected_criteria:
                button.setChecked(True)
                button_on_click_function(True, button_name)  # True resembles the state of the button

        else:  # If the button is not the right type then exit
            return

        # Connect the function to the button click and for the radiobutton pass the button and the name (to be able to fix the state of it) and for the checkbox the state and the name.
        # It's important to pass them as arguments to lambda and not directly to the function, because otherwise it will just use the same variable for all.
        if button_type == ScrollAreaButtonType.RADIOBUTTON:
            button.clicked.connect(lambda state, name=button_name, clicked_button=button: button_on_click_function(clicked_button, name))  # Attention: "clicked.connect()" passes the click state as a first argument.
        elif button_type == ScrollAreaButtonType.CHECKBOX:
            button.clicked.connect(lambda state, name=button_name: button_on_click_function(state, name))  # Attention: "clicked.connect()" passes the click state as a first argument.

        # Add the button to the layout above the spacer
        layout.insertWidget(layout.count() - 1, button)
