# Ropey-Cam
Basic simultaneous , local stream to browser, and motion triggered recording for RPi. Based on stitching together examples from the Picamera2 repository.

Why Ropey-Cam?
It's stitched together from examples with minimal Python skills, and it probably has more threads than necessary!

## Usage
Clone or copy / download Ropey-Cam.py to local machine.

Run Ropey-Cam and point a browser at <machine.ip:8000>
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

Added a version that uses the CircularOutput buffer to record video from 5 secs before the trigger motion
(This version is restricted to recording .h264 files so also added an .mp4 conversion followed by
a deletion of the .h264 file)



