## General notes to help modify the application for specific uses.

### Video sizes and FrameRates
There are a set of platform specific recommended video resolutions in commented sectons of the code Lines 67-87. These are conservative and users may wish to experiment with pushing the resolutions and framerates to suit  their requirements. It is strongly advised to limit the width values of the STREAM_WIDTH to integer multiples of 128 to maintain compatibilty across all Pi platforms. Similarily the VIDEO_WIDTH should be restricted to integer multiples of 32. 

### Length of Circular Buffer and Post-roll 
The current default of buffer_seconds is set to 3 seconds, and while longer values are possible, longer values will increase the memory requirements. The post-roll is also set to 3 seconds and could be increased to capture more of the post-motion scene.

### Trigger_level
After testing the application in the intended environment and finding the optimum trigger_level it may be useful to set the value in the code.     

### Consecutive frames of 'motion'
To help ensure the triggering is caused by 'true motion' the current default setting of after_frames is to wait for 5 consecutive frames with an mse above the trigger_level before activating recording.

### Disk storage management

To help avoid the storage disk/card being filled with video files the max_disk_usage is checked after each video file is stored and if the ratio of used/total space exceeds the max the oldest files will be deleted. 

### Timestamps
The recorded video files have a date and time stamp embedded in the frame data. The time includes a millisecond record and is useful for checking for dropped frames.  By single-stepping through the recorded files the millisecond counter should advance by ~ 1000 / FRAMES_PER_SECOND each frame. A jump between frames of more than this would indicated dropped frames in the encoded video file.  Playing back the files using mpv media player, rather than the default vlc, can be useful with it's more flexible forward/backward single stepping and easier access to the video properties information.  (Press I for comprehensive on-screen properties data.)

### Motion Detection
The previous versions have used a simple mse frame to frame change detection algorithm, as used in the Picamera2 repository motion example on which Ropey-Cam was based. A more complex algorithm based on [this article](https://medium.com/@itberrios6/introduction-to-motion-detection-part-1-e031b0bb9bb2) is now used and is much more effective at detecting motion (Frame Difference), particularly when the part of the scene in motion is only a small fraction of the overall field of view. 
