## General notes to help modify the application for specific uses.

### Compatibility with Raspberry Pi models and cameras.
With the exception of the original single core CPU boards, i.e.the Raspberry Pi Model A/B and the Pi Zero, all models from Zero 2W through Pi 2 to Pi 5 have sufficient resources to run Ropey-Cam (R-C).

As R-C is based on Picamera2/libcamera it should be compatible with all Raspberry Pi camera modules V1, V2, V3, HQ and GS, any third party versions of these, and any colour camera modules that have supported drivers in the Raspberry Pi kernel eg IMX290 IMX462. 

## Description of configuration entry inputs
When first run R-C will read in the configuration file ropey.ini and apply the values to the relevant application constants and variables. These values can be updated using the input fields, either with individual entries or in any combination followed a press of the Submit button. 

#### Video sizes and FrameRates
The default configuration is 1280x720 @ 20fps for the recorded video, and 640x360 (at the same framerate) for the stream to the browser and is conservative and 'should just work' on any supported combination of Pi + Camera module.

Full HD 1920x1080 at higher framerates 25 or 30 fps for the recorded video is possible with Pi 3 and above.

 
![Extract of screenshot showing configuration input section](config_entry_panel.png)
#### Configuration

The VIDEO WIDTH field will accept values from 1024 to 1920 in steps of 32 pixels, to match the optimal alignments supported by the hardware.

The STREAM WIDTH will accept values from 512 to 1280 in steps of 128 pixels to match the Pi5 hardware alignments. (Earlier models supported steps of 64 pixels).

The ASPECT RATIO can be either 1.333 or 1.777 (4:3 or 16:9), and is used to calculate the relevant HEIGHT for each stream.

The framerate FPS can be set between 10 and 30 fps in steps of 5.

The MODE selects one of the fundamental operating modes of the camera;
those shown when queried with  `rpicam-hello --list-cameras`

Typically MODE 0 will give a cropped and binned low resolution mode.
MODE 1 will give a full-frame 2x2 binned mode (except HQ where it gives full-width 16:9 mode and mode 2 is needed for full frame). Other higher modes may be useful in limited circumstances.

The Hflip and Vflip switches can be used to vertically or horizontally mirror the video frame or invert it if used together. 
### trigger_level
After testing the application in the intended environment and finding the optimum trigger_level with the Inc/Dec controls it may be easier to input the value directly, particularly if large changes are needed.

### Consecutive frames of 'motion'
To help ensure the triggering is caused by 'true motion' the current default setting of AFTER # FRAMES is to wait for 5 consecutive frames with a 'Frame Difference' above the trigger_level, before activating recording.
 

### Length of Circular Buffer and Post-roll 
The current default of buffer_seconds is set to 3 seconds, and while longer values are possible, longer values will increase the memory requirements. The post-roll is also set to 3 seconds and can be increased to capture more of the post-motion imagery.

    
## Configuration storage
Any configuration changes made are stored after being submitted but are not applied 'on-the-fly' and only take effect on the next startup.


## Disk storage management

To help avoid the storage disk/card being filled with video files the max_disk_usage is checked after each video file is stored and if the ratio of used/total space exceeds the max the oldest files will be deleted. 

## Timestamps
The recorded video files have a date and time stamp embedded in the frame data. The time includes a millisecond record and is useful for checking for dropped frames.  By single-stepping through the recorded files the millisecond counter should advance by ~ 1000 / FRAMES_PER_SECOND each frame. A jump between frames of more than this would indicated dropped frames in the encoded video file.  Playing back the files using mpv media player, rather than the default vlc, can be useful with it's more flexible forward/backward single stepping and easier access to the video properties information.  (Press I for comprehensive on-screen properties data.)

