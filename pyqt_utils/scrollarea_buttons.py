from enum import Enum
from typing import Callable

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QRadioButton, QCheckBox, QLayout
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt


'''
Create Radiobuttons or Checkboxes in scroll area
'''


class ScrollAreaButtonType(Enum):
    RADIOBUTTON = 'Radiobutton'
    CHECKBOX = 'Checkbox'


def create_buttons_in_scroll_area(scroll_area_content_widget: QWidget, button_name_list: list | tuple, selected_buttons: str | int | list | tuple, button_on_click_function: Callable[[bool, str], None] | Callable[[QRadioButton, str], None], button_type=ScrollAreaButtonType.RADIOBUTTON):
    """
    This function modifies the content of a scroll area and inserts buttons or a placeholder into it. It also binds the passed function to the click of the button

    :param scroll_area_content_widget: The widget inside the scroll area which contains the content of the scroll area
    :param button_name_list: A list of names for the buttons
    :param selected_buttons: For radiobutton: The name of the selected radiobutton; For checkboxes: A list with the names of the selected buttons
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
            if button_name == selected_buttons:
                button.setChecked(True)
                button_on_click_function(button, button_name)  # Return the button itself, because if there is just one radiobutton you are able to deselect it. When it is returned you can fix this later.

        # Create a checkbox button
        elif button_type == ScrollAreaButtonType.CHECKBOX:
            button = QCheckBox(button_name)

            # If the button is in the list of selected ones then check it and run the function
            if button_name in selected_buttons:
                button.setChecked(True)
                button_on_click_function(True, button_name)  # True resembles the state of the button

        else:  # If the button is not the right type then exit
            return

        # Connect the function to the button click and for the radiobutton pass the button and the name (to be able to fix the state of it) and for the checkbox the state and the name.
        # It's important to pass them as arguments to lambda and not directly to the function, because otherwise it will just use the same variable for all.
        if button_type == ScrollAreaButtonType.RADIOBUTTON:
            # noinspection PyUnresolvedReferences
            button.clicked.connect(lambda state, name=button_name, clicked_button=button: button_on_click_function(clicked_button, name))  # Attention: "clicked.connect()" passes the click state as a first argument.
        elif button_type == ScrollAreaButtonType.CHECKBOX:
            # noinspection PyUnresolvedReferences
            button.clicked.connect(lambda state, name=button_name: button_on_click_function(state, name))  # Attention: "clicked.connect()" passes the click state as a first argument.

        # Add the button to the layout above the spacer
        # noinspection PyUnresolvedReferences
        layout.insertWidget(layout.count() - 1, button)
