# Ropey-Cam
Basic simultaneous, local stream to browser, and motion triggered recording for RPi.  
Based on stitching together examples from the Picamera2 repository.  
https://github.com/raspberrypi/picamera2/tree/main/examples.  
Button controls in browser inspired by:-  
https://www.e-tinkers.com/2018/04/how-to-control-raspberry-pi-gpio-via-http-web-server/  
Thanks to signag for coding suggestions  
https://github.com/signag/raspi-cam-srv

Not a finished/polished item but suitable as a basis for basic remote operation of an RPi Camera.

Why Ropey-Cam?
It's stitched together from examples with minimal Python skills, and with numerous threads.

## Usage
Clone or copy / download Ropey-Cam.py to a machine with an attached camera.
Ensure you have opencv installed as per instructions in the PiCamera2 manual
https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
essentially 

sudo apt install python3-opencv -y

The current versions, (Ropey-Cam and RopeyCamBuffer) are 'hard' configured to use a Mode 5 of a V2 IMX219 camera.  
If you plan to use a different camera find the cam_mode_select variable (line 50) and change it
to an appropriate mode for your camera. Normally best to pick a mode with a high frame rate, but
may also want to choose a full uncropped sensor mode. The choice is yours.

e.g. for a V3 camera mode 0 or perhaps 1 might be a good choice.

The image sizes of 1024x768 for video and 1/2 size 512x384 are also hard configured and many of the timestamp and other parameters are
selected to suit these image sizes, so not too readily changed.

Once loaded and after any chnages have been made to the code then:-

Run Ropey-Cam and from another computer point a browser at <mac.hin.e.ip:8000>
where mac.hin.e.ip is the IP address of the computer running Ropey-Cam.py
You should get a live stream from the camera.

(Or for a local check, on the computer running Ropey-Cam.py point a browser 
at 127.0.0.0:8000)
Or even do both, to get a stream on the local and the remote computers.

In the background R-C is monitoring for motion in the video stream.

If sufficent change from one video frame to the next has occurred
it will start a video recording. The recording will stop when the 
motion has dropped below the set (mse) TriggerLevel.

(Adjust TriggerLevel in the code to change the sensitivity of the trigger level)

When first run Ropey-Cam should create a sub-folder "Videos" where all the triggered videos will be stored.

Note that the stream should continue while video is being recorded and stored.

The web page has some example buttons and a message feedback area to allow some control from the remote browser

## Circular Buffer Version
### Update 2
The browser control buttons have been updated to be more useful.

STOP halts the streaming and video recording and is replaced by START when pressed

DELETE will delete all the recorded video files - needs a second press to confirm

RESET will undo the first press of either the DELETE or REBOOT buttons

Button4 is still a spare

REBOOT wil reboot the Pi and also needs a second press - most useful if the program is set to autorun on boot!

Mot_OFF will disable the motion Triggering, and is replaced by Mot_ON when pressed

### Update 3
Added a version that uses the CircularOutput buffer to record video from 5 secs before the trigger motion
This has been updated to use the relatively new PyavOutput and CicularOutput2 methods to allow direct recording of mp4 files.

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
