## Instructions to configure a Lite installation
Although a full RPiOS is recommended for all Pi variants, if using a Pi Zero2W or 3A+ you may want to run on a Lite installation, to have a bit more memory 'headroom'.

>Flash a new 64bit Lite image to a card, with SSH configured.

>Insert card into the Pi with a connected camera module.

>Power on and *wait* until the full image installation and reboot sequences are complete.

>SSH in to the Pi and :-

`sudo apt update && sudo apt full-upgrade -y`

`sudo apt install python3-picamera2 --no-install-recommends`

`sudo apt install python3-opencv`

`sudo apt install git`

`git clone https://github.com/sandyol55/Ropey-Cam`

`cd Ropey-Cam`

`./RopeyCamBuffer.py`

Then continue as per the main page documentation to point a browser at the Raspberry Pi. (Wait about 10-15 seconds to allow all the libraries to load and for the camera to be initialised).

At this point you should see the image from the camera in the browser page and messages about the status in the terminal window.

Note that closing the terminal window will signal the program to hang up so the server will no longer be accessible.

To allow the terminal to be closed, while leaving the server running use :-

`nohup ./RopeyCamBuffer.py &`

## Resources

A screenshot from a Pi400 accessing RopeyCamBuffer.py running on a Pi3A+  shows usefully lower memory usage compared to the 'Desktop' version shown in the main page.

![Lite Installation screenshot from a Pi400](lite_screenshot.png)