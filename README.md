# PackedMC
A Minecraft Manager for Instances and Mods, using Python 3.14

## System
It is a PyQT6 based GUI on which you can create your own instances and Download mods.  
You can import the profiles from the normal Minecraft Launcher into PackedMC, but you have to set the mods menu.  
After configuring an Instance (supports Vanilla and Fabric) and setting all the mods (added via the Mods Page) you can play it.  
First PackedMC checks whether the Minecraft Launcher is already opened and if so asks the user to close it.  
Meanwhile it downloads the newest updates for the mods.  
Then, a profile is created for the normal Minecraft launcher (if it doesn't already exist) with the Minecraft installation for the instance.  
All mods are copied to the respective folder, the options are copied if wanted and the profile is using the selected game directory.  
  
The Mods page should support Modpacks (at least from Modrinth) and the Instances page should download the wanted version for Fabric automatically. 
