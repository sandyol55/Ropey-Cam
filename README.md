# Ropey-Cam
Basic simultaneous, local stream to browser, and motion triggered recording for RPi.  
Based on stitching together examples from the Picamera2 repository.  
https://github.com/raspberrypi/picamera2/tree/main/examples.  
Button controls in browser inspired by:-  
https://www.e-tinkers.com/2018/04/how-to-control-raspberry-pi-gpio-via-http-web-server/  
Thanks to signag for coding suggestions  
https://github.com/signag/raspi-cam-srv

Not a finished/polished item but suitable as a basis for basic remote operation of an RPi Camera.
Typical uses would be domestic or wildlife surveillance, with a low resolution live view via a browser,
and the facility to capture high resolution recordings for later replay and analysis.

Why Ropey-Cam?
It's stitched together from examples and code snippets, with minimal Python skills, and with numerous threads.

## Usage
On a machine with  RPIOS installed (full not lite - but see later instructions for a lite installation)

Clone or copy / download Ropey-Cam.py (RopeyCamBuffer.py) to a machine with an attached camera.
Ensure you have opencv installed on that machine, as per instructions in the PiCamera2 manual.
https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
essentially 

sudo apt install python3-opencv -y

The current versions, (Ropey-Cam and RopeyCamBuffer) are 'hard' configured to use camera Mode 1,
which gives a full-frame 2x2 binned 10 bit output on both V2 and V3 camera modules.  
If you plan to use a different camera, find the cam_mode_select variable (line 50 in Ropey-Cam.py)
(line 80 in RopeyCamBuffer.py)) and change it to an appropriate mode for your camera.
Normally best to pick a mode with a high frame rate, but
may also want to choose a full uncropped sensor mode. The choice is yours.

The image sizes of 1024x768 for video and 1/2 size 512x384 for streaming are also hard configured,
but suggested alternative values for other sensors or modes are in the comments.

Once loaded and after any changes have been made to the code then:-

Run Ropey-Cam.py (RopeyCamBuffer.py) and from another computer point a browser at <mac.hin.e.ip:8000>
where mac.hin.e.ip is the IP address of the computer running Ropey-Cam.py
You should get a live stream from the camera.

(Or for a local check, on the computer running Ropey-Cam.py point a browser 
at 127.0.0.0:8000)
Or even do both, to get a stream on the local and the remote computers.

In the background R-C is monitoring for motion in the video stream.

If sufficent change from one video frame to the next has occurred
it will start a video recording. The recording will stop when the 
motion has dropped below the set (mse) TriggerLevel.

If the frame to frame noise is so large that the system is permanently triggered and recording then 
use the new Inc_Trigger_Level button to increase the trigger level value and decrease the sensitivity. 
(Then adjust the TriggerLevel in the code to change the initial sensitivity of the trigger level).

When first run Ropey-Cam should create a sub-folder "Videos" where all the triggered videos
and associated monochrome jpeg snapshots of the moment of triggering will be stored.

Note that the stream should continue while video is being recorded and stored.

The web page has buttons and a message feedback area to allow some control from the remote browser.

## Circular Buffer Version

###Update 5
New Features

If the disk usage is above a certain level (80%) then, after each saved event, the oldest file pair in the Videos directory is deleted.
 
The trigger Level for the motion detection is now adjustable via web browser buttons.

If on start-up the system is recording, perhaps due to noise difference between frames, then Increment the Trigger level.

Also new is an in-stream stamp in the top left corner showing the current frame to frame mse result versus the current Trigger Level.

Changes

Many variable names have been updated to reflect 'best practice' so the code should be more readable. 
A number of previously hard coded settings have been made parametric to adjust in line with the selected video frame dimensions.
 
To aid in file review and video replay the system has been tested with a samba server running in the background and been found to be
responsive, even on older platforms e.g Pi3A+.

Install and activate a samba server in line with available online tutorials and access the Videos directory from a remote machine.
On Pi platforms installing the Thunar file manager in the client machine is a convenient way to get thumbnail icons of both the video and snapshot files.
 
Installing mpv media player and making that the default video player, in place of VLC, allows easy access to some of the video metedata (press I).
(Just my preference!)

Also tested is invoking a systemd set-up for automatic restart of the program on system reboot. Again following online tutorials.

Can add the detailed instructions for both of these if likely to help new users.

Both of the above (samba and systemd auto start on reboot) have been tested successfully with Pi3A+ as the camera server.

If a Pi4 or Pi5 is used then considerably higher resolutions and framerates than the defaults in the current code can be supported.

## Lite installation
The main instructions assume RopeyCam is to be run with the full desktop OS installed, as this requires the least additional dependencies to be installed.
A Lite installation  will leave more free memory and only requires an extra few steps to set up.
At time of writing Trixie is the latest RPIOS.
Flash a new Lite 64-bit RPIOS image to a card, with SSH configured.
Place the card in the machine with camera installed and power on.
If doing a headless install WAIT until the full image installation and power up sequence is complete.
SSH in and do an initial
sudo apt update
sudo apt full-upgrade 
If planning to clone from the github:-
sudo apt install git
Sudo apt install python3-picamera2 --no-install-recommends
sudo apt install python3-opencv
Then install RopeyCam either by git cloning or scp from another machine than has a copy.
Then cd into the directory containing RopeyCam
And ./RopeyCamBuffer.py


### Update 4
Further updates to improve the button functionality and logic.
Buttons are now:-

Manual_Recording_START and Manual_Recording_STOP, which can be used to start and stop recordings, independently of the motion trigger.
(Best used after disabling Motion Detection).

DELETE is unchanged from previous version and needs a second press to confirm deletion of all stored video and image files.


RESET is also basically unchanged from previous version and cancels the first press of DELETE REBOOT and EXIT.

REBOOT is also unchanged and, when pressed twice reboots the remote RopeyCam server.

EXIT will, when pressed twice, shutdown the RopeyCam server on the remote machine.

Motion_Detect_OFF and Motion_Detect_ON disable and re-enable the Motion Detection in the remote Camera/Server.

A REC timestamp has been added to the streamed frames to help identify when recording is underway.

The conversion of the YUV420 lo-res image arrays to JPEGs for streaming has been updated to be done within simplejpeg, rather
than a combined OpenCV and simplejpeg operation.
### Update 3
Added a version that uses the CircularOutput buffer to record video from 5 secs before the trigger motion
This has been updated to use the relatively new PyavOutput and CicularOutput2 methods to allow direct recording of mp4 files.
### Update 2
The browser control buttons have been updated to be more useful.

STOP halts the streaming and video recording and is replaced by START when pressed

DELETE will delete all the recorded video files - needs a second press to confirm

RESET will undo the first press of either the DELETE or REBOOT buttons

Button4 is still a spare

REBOOT wil reboot the Pi and also needs a second press - most useful if the program is set to autorun on boot!

Mot_OFF will disable the motion Triggering, and is replaced by Mot_ON when pressed


