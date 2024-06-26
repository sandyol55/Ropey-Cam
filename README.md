# Ropey-Cam
Basic simultaneous, local stream to browser, and motion triggered recording for RPi.  
Based on stitching together examples from the Picamera2 repository.  
https://github.com/raspberrypi/picamera2/tree/main/examples.  
Button controls in browser inspired by:-  
https://www.e-tinkers.com/2018/04/how-to-control-raspberry-pi-gpio-via-http-web-server/  
Thanks to signag for coding suggestions  
https://github.com/signag/raspi-cam-srv

Why Ropey-Cam?
It's stitched together from examples with minimal Python skills, and it probably has more threads than necessary!

## Usage
Clone or copy / download Ropey-Cam.py to local machine.
Ensure you have opencv installed as per instructions in the PiCamera2 manual
https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf

The current versions are configured to use a V2 IMX219 camera so are set up to use its Mode 5.  
If you plan to use a different camera find the cam_mode_select variable (line 50) and change it
to an appropriate mode for your camera. Normally best to pick a mode with a high frame rate, but
may also want to choose a full uncropped sensor mode. The choice is yours.
e.g. for a V3 camera mode 0 or perhaps 1 might be a good choice.

Run Ropey-Cam and point a browser at <mac.hin.e.ip:8000>
(Or for a local check, on the same machine point a browser 
at 127.0.0.0:8000)  Or even both.

You should get a live stream from the camera.

In the background R-C is monitoring for motion in the video stream.

If sufficent change from one video frame to the next has occurred
it will start a video recording. The recording will stop when the 
motion has dropped below the set (mse) TriggerLevel.

(Adjust TriggerLevel in the code to change the sensitivity of the trigger level)

R-C should create a sub-folder "Videos" where all the triggered videos will be stored.

Note that the stream should continue while video is being recorded and stored.

Now with buttons and a message feedback area to allow some control from the remote browser

## Circular Buffer Version
Added a version that uses the CircularOutput buffer to record video from 5 secs before the trigger motion
(This version is restricted to recording .h264 files so also added an .mp4 conversion followed by
a deletion of the .h264 file)
### Update 2
The browser control buttons have been updated to be more useful.

STOP halts the streaming and video recording and is replaced by START when pressed

DELETE will delete all the recorded video files - needs a second press to confirm

RESET will undo the first press of either the DELETE or REBOOT buttons

Button4 is still a spare

REBOOT wil reboot the Pi and also needs a second press - most useful if the program is set to autorun on boot!

Mot_OFF will disable the motion Triggering, and is replaced by Mot_ON when pressed



