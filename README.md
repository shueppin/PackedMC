# PackedMC
A fully Open Source GUI to manage Minecraft Instances and Mods.  
It is written in Python 3.14 and uses a PyQT6 interface in combination with [qt-material](https://github.com/dunderlab/qt-material).


## Features
- Create Minecraft instances and download mods from [Modrinth](https://modrinth.com/) or [CurseForge](https://www.curseforge.com/).
- Import your Minecraft instances from the standard Minecraft Launcher into PackedMC.  
- Mods are automatically downloaded and updated.
- Native support and automatic downloads for Minecraft Vanilla and Fabric.
- Play using the standard Minecraft Launcher. No additional login required.


## Installation
You can find premade installer files [here](https://github.com/shueppin/PackedMC/releases/tag/Installer).
### Windows
Download the [Installer for Windows](https://github.com/shueppin/PackedMC/releases/download/Installer/PackedMC-Installer.cmd).  
Execute the installer and follow the instructions. It will automatically install the newest Version of PackedMC.  
After the installation has finished you will find PackedMC in your Apps.  
Any updates to PackedMC will be downloaded automatically. The new features will be available after a restart of PackedMC.  

### Direct Installation using Python
Download the whole source code from the [latest release](https://github.com/shueppin/PackedMC/releases/latest) and move it to where you want it to be.  
Install [Python 3.14](https://www.python.org/downloads/latest/python3.14/).  
Install the requirements inside the PackedMC directory: `pip install -r requirements.txt`.  
You can now start PackedMC with `python main.py`.  
Any updates to PackedMC will be downloaded automatically. The new features will be available after a restart of PackedMC.  


## Uninstall PackedMC
If you decide to uninstall PackedMC, follow the instructions for your platform below:  
### Windows
Click the start menu and search for PackedMC.  
Click on "Open file location". This should lead you to something like `C:\Users\[name]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs`.  
Right-Click on PackedMC and choose "Open file path". This leads you to the files of PackedMC, default is `C:\Users\[name]\AppData\Local\Programs\PackedMC\python`.  
Go outside the `python` directory and outside the `PackedMC` directory, and then delete this. Then also delete the first file at `...\Microsoft\Windows\Start Menu\Programs` and you are done.
