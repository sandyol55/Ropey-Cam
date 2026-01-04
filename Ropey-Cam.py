#!/usr/bin/python3

# Run this script, then point a web browser at http:<this-ip-address>:8000, or to test on the local machine use 127.0.0.1:8000
# While running, any motion above 'trigger_level' will start a timestamped video capture to 
# a local Videos subfolder, along with a jpeg monochrome still of the trigger moment.
# Adjust trigger_level as required, using the Inc and Dec_Trigger Level buttons, to set the sensitivity of the frame to frame difference trigger.
# Other buttons on home page can :Start/Stop Manual Recording: :DELETE Video Files: :RESET: :SHUTDOWN: :REBOOT the system: or :Toggle motion Detection:  

import os
import sys
import logging
import socketserver
from glob import glob
from shutil import disk_usage
from numpy import mean, square,subtract, copy
from simplejpeg import encode_jpeg_yuv_planes
from cv2 import putText, FONT_HERSHEY_SIMPLEX
from time import strftime, sleep, time, time_ns
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Condition, Thread
from picamera2 import Picamera2, MappedArray
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput,CircularOutput2
from datetime import datetime
from PIL import Image
from libcamera import Transform

# Set HTML string 'variables'
stop_start ="Manual_Recording_START"
message_1="Live streaming with Motion Detection ACTIVE"
motion_button ="Motion_Detect_OFF"

# Set Video sizes. Firstly width and height of the hi-res (recorded video stream) then the lo-res stream (used for motion detection and streaming)
# Keep WIDTH an integer multiple of 128 for maximum compatibility across platforms. Uncomment as necessary to set up the required aspect ratio and resolution.
# The sets suggested have been selected to cover most combinations of Pi models and Cameras

# This set is a compromise that can be used in most situations. 
# VIDEO_WIDTH,VIDEO_HEIGHT=1024,768 # Recommended hi-res (recorded) resolution for 4:3 sensor modes
# STREAM_WIDTH,STREAM_HEIGHT=512,384 # Recommended lo-res (streaming) resolution for 4:3 sensor modes 

VIDEO_WIDTH,VIDEO_HEIGHT=1280,720  # Recommended hi-res (recorded) resolution for 16:9 sensor modes
STREAM_WIDTH,STREAM_HEIGHT=512,304   # Recommended lo-res (streaming) resolution for 16:9 sensor modes

# These higher resolution sets are best suited to Pi3 and above
# VIDEO_WIDTH,VIDEO_HEIGHT=1672,1254 # Advanced hi-res (recorded) resolution for 4:3 sensor modes
# STREAM_WIDTH,STREAM_HEIGHT=768,576 # Advanced lo-res (streaming) resolution for 4:3 sensor modes 

# VIDEO_WIDTH,VIDEO_HEIGHT=1920,1080  # Advanced hi-res (recorded) resolution for 16:9 sensor modes
# STREAM_WIDTH,STREAM_HEIGHT=768,432   # Advanced lo-res (streaming) resolution for 16:9 sensor modes

# Initialise variables and Booleans
FRAMES_PER_SECOND = 25 # Adjust as required to set Video Framerate. eg 10 or 15fps may help allow lower power Pi models to perform without frame dropping.
trigger_level=10 # Sensitivity of frame to frame change for 'motion' detection 
reset_trigger=trigger_level # Copy of value used to reset trigger_level after disabling motion detection.
video_count=0
mse =0
max_disk_usage= 0.8
was_button_pressed = False
should_reboot =False
should_exit=False
should_delete_files=False
set_manual_recording=False
should_shutdown=False
is_recording=False

# Set text colour, position and size for timestamp, (Yellow text, near top of screen, in a large font)
colour = (220, 220, 80)
origin = (40, 50)
font = FONT_HERSHEY_SIMPLEX
scale = 2
thickness = 2

# Set Y and u,v colour for a red block REC stamp in streaming frames
y,u,v = 0,110,250
# Set Y for combined MSE / Trigger level stamp in streaming frames. White stamp so no need for u,v values.
y_mse_stamp = 255

# Pick a Camera Mode. The Value of 1 here would for example select a full frame 2x2 binned 10-bit 16:9 output if using an HQ or V3 camera.
# A value of 1 with V2 camera will select a full frame 2x2 binned 10bit 4:3 output.
cam_mode_select = 1 # Pick a mode for your sensor that will generate the required native format, field of view and framerate.

# Find the directory we're in and then check for, and if necessary, create a Videos subdirectory.
full_path=os.path.realpath(__file__)
thisdir = os.path.dirname(full_path)
os.chdir (thisdir)
if not os.path.isdir ("Videos"):
    os.mkdir("Videos")

os.environ["LIBCAMERA_LOG_LEVELS"] = "4"  # reduce libcamera messsages

def apply_timestamp(request):
    str_ms=str(time_ns()//1000000-3)
    ms=str_ms[-3:]
    timestamp = strftime("%Y-%m-%d %X.")+ms
    with MappedArray(request, "main") as m:
        putText(m.array, timestamp, origin, font, scale, colour, thickness)

def capturebuffer():
    global cb_frame
    global buf2
    while not cb_abort:
        buf2 = picam2.capture_array("lores")
        with cb_condition:
            cb_frame = buf2
            cb_condition.notify_all()

# Superimpose data on YUV420 frames then encode them as jpegs for sending to browser stream.
def mjpeg_encode():
    global mjpeg_frame
    while not mjpeg_abort:
        with cb_condition:
            cb_condition.wait()
            yuv = copy(cb_frame)
            # embed result of frame to frame mse calculation, versus current trigger level in top left of frame.
            putText(yuv,str(int(10*mse)/10)+"/"+str(trigger_level),(12,22),font,scale//2,(y_mse_stamp,0,0),thickness)
            if is_recording:
                # put a red REC stamp in top right of frame
                putText(yuv,"REC",(STREAM_WIDTH-72,22),font,1,(y,0,0),2)
                yuv[STREAM_HEIGHT:STREAM_HEIGHT+7,STREAM_WIDTH-40:]=u
                yuv[STREAM_HEIGHT+STREAM_HEIGHT//4:STREAM_HEIGHT+STREAM_HEIGHT//4+7,STREAM_WIDTH-40:]=v
                yuv[STREAM_HEIGHT:STREAM_HEIGHT+7,STREAM_WIDTH//2-40:STREAM_WIDTH//2]=u
                yuv[STREAM_HEIGHT+STREAM_HEIGHT//4:STREAM_HEIGHT+STREAM_HEIGHT//4+7,STREAM_WIDTH//2-40:STREAM_WIDTH//2]=v

            # Use simplejpeg instead of opencv to go from yuv to jpeg
            buf = encode_jpeg_yuv_planes(
                yuv[:STREAM_HEIGHT],
                yuv.reshape(STREAM_HEIGHT*3,STREAM_WIDTH//2)[STREAM_HEIGHT*2:STREAM_HEIGHT*2+STREAM_HEIGHT//2],
                yuv.reshape(STREAM_HEIGHT*3,STREAM_WIDTH//2)[STREAM_HEIGHT*2+STREAM_HEIGHT//2:],
                quality=80) 
            with mjpeg_condition:
                mjpeg_frame = buf
                mjpeg_condition.notify_all()

class StreamingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global message_1,stop_start,was_button_pressed,motion_button,trigger_level,reset_trigger,should_delete_files,should_shutdown,should_exit,should_reboot,mjpeg_abort,video_count,set_manual_recording

        content_length = int(self.headers['Content-Length'])  # Get the size of data
        post_data = self.rfile.read(content_length).decode("utf-8")  # Get the data
        post_data = post_data.split("=")[1]  # Only keep the value

        if post_data == 'Manual_Recording_START':
            message_1="Live streaming with Manual Recording ACTIVE"
            stop_start="Manual_Recording_STOP"
            is_manual_recording=True

        elif post_data == 'Manual_Recording_STOP':
            message_1="Live Streaming with Manual Recording Stopped. (Short delay to close recording .. then wait for next action)."
            stop_start="Manual_Recording_START"
            is_manual_recording=False

        elif post_data == 'DELETE_ALL_FILES':
            message_1="Press DELETE_ALL_FILES again to delete all files - or RESET to cancel"
            if should_delete_files:
                os.system("rm Videos/avi*")
                video_count=0
                should_delete_files = False
                message_1 = "Video files deleted and video counter reset"
            else:
                should_delete_files=True

        elif post_data =='RESET':
            message_1="Reset EXIT, DELETE, REBOOT and SHUTDOWN to initial default conditions i.e. Cancel the first press"
            should_reboot=False
            should_delete_files=False
            should_exit=False
            should_shutdown=False

        elif post_data == 'REBOOT':
            message_1=" Press REBOOT again if you're sure - or RESET to cancel. (Short delay while files are saved)."
            if should_reboot:
                set_manual_recording=False
                trigger_level=999 
                print("Closing any active recordings and rebooting shortly")
                sleep(8)
                os.system("sudo reboot now")
            should_reboot = True

        elif post_data == 'SHUTDOWN':
            message_1="Press SHUTDOWN again if you're sure - or RESET to cancel. (Short delay while files are saved)."
            if should_shutdown:
                set_manual_recording=False
                trigger_level=999 
                print("Closing any active recordings and shutting down shortly")
                sleep(8)
                os.system("sudo shutdown now")
            should_shutdown=True

        elif post_data == 'EXIT':
            message_1=" Press EXIT again if you're sure - or RESET to cancel. (Short delay while files are saved)."
            if should_exit:
                set_manual_recording=False
                trigger_level=999 
                print("Exiting shortly")
                sleep(8)
                mjpeg_abort=True
                picam2.close()
                sys.exit(0)
            should_exit = True

        elif post_data == 'Motion_Detect_ON':
            message_1="Live streaming with Motion Detection ACTIVE"
            motion_button="Motion_Detect_OFF"
            trigger_level=reset_trigger

        elif post_data == 'Motion_Detect_OFF':
            message_1="Live streaming with Motion Detection INACTIVE"
            motion_button="Motion_Detect_ON"
            trigger_level=999

        elif post_data == 'Inc_TriggerLevel':
            message_1="Decrease motion sensitivity by increasing trigger level"
            trigger_level += 1
            reset_trigger += 1

        elif post_data == 'Dec_TriggerLevel':
            message_1="Increase motion sensitivity by decreasing trigger level"
            if trigger_level>1:
                trigger_level -= 1
                reset_trigger -= 1

        print("Control button pressed was {}".format(post_data))
        was_button_pressed =True
        self._redirect('/index.html')  # Redirect back to the home url

    def _redirect(self, path):
        self.send_response(303)
        self.send_header('Content-type', 'text/html')
        self.send_header('Location', path)
        self.end_headers()

    def do_GET(self):
        PAGE = """\
            <!DOCTYPE html>
              <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport" content="width=device-width, initial-scale=1.0">
                  <title>Ropey-Cam</title>
                </head>
                <body>
                  <center>
                    <h2>Ropey-Cam   Live Streaming with motion-triggered Recording</h2>
                    <img src="stream.mjpg" width="{ph1}" height="{ph2}" />
                    <p> {ph3}  </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="{ph4}">
                      <input type="submit" name="submit" value="Inc_TriggerLevel">
                      <input type="submit" name="submit" value="Dec_TriggerLevel">
                      <input type="submit" name="submit" value="{ph5}">
                    </form>
                    <p> </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="DELETE_ALL_FILES" style="background-color:lightpink;">
                      <input type="submit" name="submit" value="EXIT">
                      <input type="submit" name="submit" value="RESET" style=background-color:lightgreen>
                      <input type="submit" name="submit" value="REBOOT">
                      <input type="submit" name="submit" value="SHUTDOWN">
                    </form>
                  </center>
                </body>
              </html>
            """.format(ph1=STREAM_WIDTH,ph2=STREAM_HEIGHT, ph3=message_1, ph4=motion_button,ph5=stop_start)

        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with mjpeg_condition:
                        mjpeg_condition.wait()
                        frame = mjpeg_frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()



class StreamingServer(socketserver.ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def motion():
    global video_count, was_button_pressed, is_recording ,mse
    while not motion_abort:
        with cb_condition:
            cb_condition.wait()
            previous_frame = None
            is_recording = False
            if not was_button_pressed: # Ignore motion check if button was recently pressed
                while True:
                    with cb_condition:
                        cb_condition.wait()
                        current_frame = copy(cb_frame)
                    current_frame = current_frame[:STREAM_HEIGHT,:]
                    if previous_frame is not None:
                        mse = mean(square(subtract(current_frame, previous_frame)))
                        if mse >trigger_level or set_manual_recording: 
                            if not is_recording:
                                video_count+=1
                                now = datetime.now()
                                date_time = now.strftime("%Y%m%d_%H%M%S")
                                file_title="Videos/avi_{:05d}_{}".format(video_count,date_time)
                                full_file_title=file_title + ".mp4"
                                icon=Image.fromarray(current_frame)
                                icon.save(file_title+"_im.jpg")

                                circ.open_output(PyavOutput(full_file_title))

                                is_recording = True
                                start_time = time()
                                print()
                                print(f'New recording starting after "trigger value" of  {mse:.1f}')

                            last_motion_time = time()
                        else:
                            if (is_recording and ((time() - last_motion_time) > 6)): # Wait for 3 seconds after motion stops before closing + 3 seconds for the buffer length.
                                is_recording = False
                                circ.close_output()
                                print()
                                print("Closing and saving file",file_title, end=", ")
                                print(f'which holds { (time()-start_time):.1f} seconds worth of video')
                                print()
                                print("Waiting for next trigger or button initiated command.")

                                # If running low on disk space delete oldest file after writing most recent one
                                total, used, _ = disk_usage("Videos")
                                used_space=used/total
                                if used_space > max_disk_usage:
                                    oldest_snapshot=sorted(glob("Videos/*.jpg"), key=os.path.getctime)[0]
                                    oldest_video_file=sorted(glob("Videos/*.mp4"), key=os.path.getctime)[0]
                                    os.remove(oldest_snapshot)
                                    os.remove(oldest_video_file)


                    previous_frame = current_frame
                    was_button_pressed = False

def stream():
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        set_manual_recording=False
        trigger_level=999 
        print("Exiting shortly")
        sleep(8)
        picam2.close()
        mjpeg_abort = True


# Configure Camera and start it running
picam2 = Picamera2()
mode=picam2.sensor_modes[cam_mode_select]
# Set hflip and vflip to True if image inversion is required
picam2.configure(picam2.create_video_configuration(sensor={"output_size":mode['size'],'bit_depth':mode['bit_depth']},
                                                   controls={'FrameRate' : FRAMES_PER_SECOND},
                                                   transform=Transform(hflip=False,vflip=False),
                                                     main={"size": (VIDEO_WIDTH,VIDEO_HEIGHT),'format':"BGR888"},
                                                       lores={"size": (STREAM_WIDTH, STREAM_HEIGHT),'format':"YUV420"},buffer_count=10))


encoder = H264Encoder(3300000, repeat=True,iperiod=45)
picam2.pre_callback = apply_timestamp

# Circular Buffer enabled and started
circ=CircularOutput2(buffer_duration_ms=3000)
encoder.output=[circ]
picam2.start_recording(encoder,circ)
sleep(1)

# Start up the various threads.
cb_abort = False
cb_frame = None
buf2 = None
cb_condition = Condition()
cb_thread = Thread(target=capturebuffer, daemon=True)
cb_thread.start()

mjpeg_abort = False
mjpeg_frame = None
mjpeg_condition = Condition()
mjpeg_thread = Thread(target=mjpeg_encode, daemon=False)
mjpeg_thread.start()

stream_thread = Thread(target=stream, daemon=True)
stream_thread.start()

motion_abort=False
motion_thread = Thread(target=motion, daemon=True)
motion_thread.start()

# Join an 'infinite' thread to keep main thread alive 'til ready to exit by 'aborting' mjpeg thread
mjpeg_thread.join()

