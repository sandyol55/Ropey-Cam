#!/usr/bin/python3

# Run this script, then point a web browser at http:<this-ip-address>:8000, or to test on the local machine use 127.0.0.1:8000
# While running, any motion above 'TriggerLevel'will start a timestamped video capture to 
# a local Videos subfolder, along with a jpeg monochrome still of the trigger moment.
# Adjust TriggerLevel as required, using the Inc and Dec_Trigger Level buttons, to set the sensitivity of the frame to frame difference trigger.
# Other buttons on home page can :Start/Stop Manual Recording: :DELETE Video Files: :RESET: :SHUTDOWN: :REBOOT the system: or :Toggle motion Detection:  

import os
import logging
import socketserver
from glob import glob
from shutil import disk_usage
from numpy import mean, square,subtract
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

# Set HTML string'variables'
stop_start ="Manual_Recording_START"
message_1="Live streaming with Motion Detection ACTIVE"
motion_button ="Motion_Detect_OFF"

# Set Video sizes. Firstly width and height of the hi-res (recorded video stream), then the lo-res stream (used for motion detection and streaming)
# Uncomment as necessary to set up the required aspect ratio and resolution.

# The sets suggested have been selected to cover most combinations of Pi models and Cameras

#This set is a compromise that can be used in most situations
w,h=1024,768    # Recommended hi-res (recorded) resolution for 4:3 sensor modes
w2,h2=512,384   # Recommended lo-res (streaming) resolution for 4:3 sensor modes 

# w,h=1280,720    # Recommended hi-res (recorded) resolution for 16:9 sensor modes
# w2,h2=512,304   # Recommended lo-res (streaming) resolution for 16:9 sensor modes


# These higher resolution sets are best suited to Pi4 Pi5 and upwards
# w,h=1672,1254  # Recommended hi-res (recorded) resolution for 4:3 sensor modes
# w2,h2=768,576  # Recommended lo-res (streaming) resolution for 4:3 sensor modes 

# w,h=1920,1080   # Recommended hi-res (recorded) resolution for 16:9 sensor modes
# w2,h2=768,432   # Recommended lo-res (streaming) resolution for 16:9 sensor modes

#Initialise variables and Booleans
trigger_level=12 # Sensitivity of frame to frame change for 'motion' detection 
reset_trigger=trigger_level # Copy of value used to reset trigger_level after disabling motion detection.
video_count=0
mse =0
max_disk_usage= 0.8

was_button_pressed = False
should_reboot =False
should_shutdown=False
should_delete_files=False
is_manual_recording=False
is_recording=False

# Set text colour, position and size for timestamp to embed in recorded video stream, (Yellow text, near top of screen, in a large font)
colour = (220, 220, 80)
origin = (40, 50)
font = FONT_HERSHEY_SIMPLEX
scale = 2
thickness = 2

# Set Y and u,v colour for a red block REC stamp in streaming frames
y,u,v = 0,110,250
# Set Y for combined MSE / Trigger level stamp in streaming frames. White stamp so no need for u,v values.
y_mse_stamp = 255

# Pick a Camera Mode. The Value of 1 here would for example:- Select a full frame 2x2 binned 10-bit 4:3 output if using a V2 or16:9 if using a V3 camera.
# Mode 0 will, in most cameras, select a cropped, fast framerate mode. Use 'rpicam-hello --list-cameras' to get supported modes. 
cam_mode_select = 1 # Pick a mode for your sensor that will generate the required native format, field of view and framerate.

# Find the directory we're in and then check for, and if necessary, create a Videos subdirectory.
full_path=os.path.realpath(__file__)
thisdir = os.path.dirname(full_path)
os.chdir (thisdir)
if not os.path.isdir ("Videos"):
    os.mkdir("Videos")

os.environ["LIBCAMERA_LOG_LEVELS"] = "4"  #reduce libcamera messsages

def apply_timestamp(request):
    str_ms=str(time_ns()//1000000-6)
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

#mjpeg encode a frame based on example.
def mjpeg_encode():
    global mjpeg_frame
    while not mjpeg_abort:
        with cb_condition:
            cb_condition.wait()
            yuv = cb_frame
            # embed result of frame to frame mse calculation, versus current trigger level in top left of frame.
            putText(yuv,str(int(mse))+"/"+str(trigger_level),(12,22),font,1,(y_mse_stamp,0,0),2)
            if is_recording:
                # put a red REC stamp in top right of frame
                putText(yuv,"REC",(w2-72,22),font,1,(y,0,0),2)
                yuv[h2:h2+7,w2-40:]=u
                yuv[h2+h2//4:h2+h2//4+7,w2-40:]=v
                yuv[h2:h2+7,w2//2-40:w2//2]=u
                yuv[h2+h2//4:h2+h2//4+7,w2//2-40:w2//2]=v

            # Use simplejpeg instead of opencv to go from yuv to jpeg
            buf = encode_jpeg_yuv_planes(
                yuv[:h2],
                yuv.reshape(h2*3,w2//2)[h2*2:h2*2+h2//2],
                yuv.reshape(h2*3,w2//2)[h2*2+h2//2:],
                quality=80)
            with mjpeg_condition:
                mjpeg_frame = buf
                mjpeg_condition.notify_all()

class StreamingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global message_1,stop_start,was_button_pressed,motion_button,trigger_level,reset_trigger,cb_abort,video_count,should_reboot,should_shutdown,should_delete_files,is_manual_recording

        content_length = int(self.headers['Content-Length'])  # Get the size of data
        post_data = self.rfile.read(content_length).decode("utf-8")  # Get the data
        post_data = post_data.split("=")[1]  # Only keep the value

        if post_data == 'Manual_Recording_START':
            message_1="Live streaming with Manual Recording ACTIVE"
            stop_start="Manual_Recording_STOP"
            is_manual_recording=True

        elif post_data == 'Manual_Recording_STOP':
            message_1="Live Streaming with Manual Recording Stopped. Flushing Buffer and then waiting for next action"
            stop_start="Manual_Recording_START"
            is_manual_recording=False

        elif post_data == 'DELETE':
            message_1="Press DELETE again to delete all files - or RESET to cancel"
            if should_delete_files:
                os.system("rm Videos/avi*")
                video_count=0
                message_1 = "Video files deleted and counter reset"
                should_delete_files = False
            else:
                should_delete_files=True

        elif post_data =='RESET':
            message_1="Reset EXIT, DELETE and REBOOT to initial default conditions i.e. Cancel first press"
            should_reboot=False
            should_delete_files=False
            should_shutdown=False

        elif post_data == 'REBOOT':
            message_1=" Press REBOOT again if you're sure - or RESET to cancel"
            if should_reboot:
                os.system("sudo reboot")
            should_reboot = True

        elif post_data == 'SHUTDOWN':
            message_1=" Press SHUTDOWN again if you're sure - or RESET to cancel"
            if should_shutdown:
                print("Shutting down")
                sleep(1)
                os._exit(0)
            should_shutdown = True

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
                      <input type="submit" name="submit" value="DELETE">
                      <input type="submit" name="submit" value="RESET">
                      <input type="submit" name="submit" value="SHUTDOWN">
                      <input type="submit" name="submit" value="REBOOT">
                      <input type="submit" name="submit" value="{ph5}">
                    </form>
                    <p> </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="Inc_TriggerLevel">
                      <input type="submit" name="submit" value="Dec_TriggerLevel">
                    </form>
                  </center>
                </body>
              </html>
            """.format(ph1=w2,ph2=h2, ph3=message_1, ph4=stop_start,ph5=motion_button)

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
    prev = None
    is_recording = False
    ltime = 0
    start_time=0
    if  not was_button_pressed:# Ignore motion check if button was recently pressed
        while True:

            with cb_condition:
                cb_condition.wait()
                cur = cb_frame

            cur = cur[:h2,:]
            if prev is not None:
                mse = mean(square(subtract(cur, prev)))
                if mse >trigger_level or is_manual_recording:
                    if not is_recording:
                        video_count+=1
                        now = datetime.now()
                        date_time = now.strftime("%Y%m%d_%H%M%S")
                        file_title="Videos/avi_{:05d}_{}".format(video_count,date_time)
                        full_file_title=file_title + ".mp4"
                        icon=Image.fromarray(cur)
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
                        usedspace=used/total
                        if usedspace > max_disk_usage:
                            oldest_snapshot=sorted(glob("Videos/*.jpg"), key=os.path.getctime)[0]
                            oldest_video_file=sorted(glob("Videos/*.mp4"), key=os.path.getctime)[0]
                            os.remove(oldest_snapshot)
                            os.remove(oldest_video_file)



            prev = cur
            was_button_pressed = False

def stream():
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        # mjpeg_abort = True
        # mjpeg_thread.join()
        pass

# Configure Camera and start it running
picam2 = Picamera2()
mode=picam2.sensor_modes[cam_mode_select]
# Set hflip and vflip to True if image inversion is required
picam2.configure(picam2.create_video_configuration(sensor={"output_size":mode['size'],'bit_depth':mode['bit_depth']},
                                                   controls={'FrameDurationLimits' :  (33333,33333)},
                                                   transform=Transform(hflip=False,vflip=False),
                                                     main={"size": (w,h)},
                                                       lores={"size": (w2, h2),'format':"YUV420"},buffer_count=10))

encoder = H264Encoder(3300000, repeat=True,iperiod=45)
picam2.pre_callback = apply_timestamp

#Circular Buffer enabled and started
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
mjpeg_thread = Thread(target=mjpeg_encode, daemon=True)
mjpeg_thread.start()

stream_thread = Thread(target=stream, daemon=True)
stream_thread.start()

motion_thread = Thread(target=motion, daemon=True)
motion_thread.start()

# Need to join an 'infinite' thread to keep main thread alive
motion_thread.join()
