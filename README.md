# PackedMC
A fully Open Source GUI to manage Minecraft Instances and Mods.  
It is written in Python 3.14 and uses a PyQT6 interface in combination with [qt-material](https://github.com/dunderlab/qt-material).
When pressing "Play" inside PackedMC, it will start the official Minecraft Launcher and select a profile, so you can just press "play" inside the Launcher and start the correct version with the selected mods if available.


## Features
- Create Minecraft instances and download mods from [Modrinth](https://modrinth.com/) or [CurseForge](https://www.curseforge.com/).
- Directly search for Modrinth mods inside PackedMC.
- Import your Minecraft instances from the standard Minecraft Launcher into PackedMC.  
- Mods are automatically downloaded and updated.
- Native support and automatic downloads for Minecraft Vanilla and Fabric.
- Play using the standard Minecraft Launcher. No additional login required.
- Automatic updates of PackedMC.


## Installation
You can find premade installer files [here](https://github.com/shueppin/PackedMC/releases/tag/Installer).  
PackedMC requires the standard (official) Minecraft Launcher to be able to play.
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


## Troubleshooting
If the launcher crashes for any reason, the error message can be found in the PackedMC directory in `crash.log`.  
Feel free to open an issue with the error or even a pull request with the fix.


## Uninstall PackedMC
If you decide to uninstall PackedMC, follow the instructions for your platform below:  
### Windows
Open PackedMC and go to the Settings tab.  
Click on "Open PackedMC Directory" to open it in the explorer. Default is `C:\Users\[name]\AppData\Local\Programs\PackedMC`.  
You can delete this whole directory. ATTENTION: Your mods and instances will be lost too.  
Then go to `C:\Users\[name]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs`, where `[name]` is your Windows user. There you can delete the PackedMC link.
