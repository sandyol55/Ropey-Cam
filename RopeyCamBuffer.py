#!/usr/bin/python3

# Run this script, then point a web browser at http:<this-ip-address>:8000, or to test on the local machine use 127.0.0.1:8000
# While running, any motion above 'TriggerLevel'will start a timestamped video capture to 
# a local Videos subfolder, along with an optional jpeg monochrome still of the trigger moment.
# Adjust TriggerLevel as required to set sensitivity of trigger
# Buttons on home page can :Start/Stop Manual Recording: :Delete Video Files: :RESET: :Exit: :Reboot the system: or :Toggle motion Detection:  
# Set up to record 3 seconds worth of video prior to the trigger event and 2 seconds after motion drops below the trigger level.


import os
import logging
import socketserver
import numpy as np
from simplejpeg import encode_jpeg_yuv_planes
import cv2
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Condition, Thread
from picamera2 import Picamera2, MappedArray
from picamera2.encoders import H264Encoder
from picamera2.outputs import PyavOutput,CircularOutput2
from datetime import datetime
from PIL import Image
from libcamera import Transform
# from libcamera import controls

# Set HTML 'variables'
Stop_Start ="Manual_Recording_START"
Message1="Live streaming with Motion Detection ACTIVE"
MotionBtn ="Motion_Detect_OFF"
Motoggle=True

#Set Video sizes
w,h=1024,768 #Set default recorded video dimensions
w2,h2=w//2,h//2  #Half size lo-res size for motion detect and streaming

#Initialise variables and Booleans
TriggerLevel=15 # Sensitivity of frame to frame change for motion detection 
trigger=TriggerLevel  
video_count=0
wasbuttonpressed = False
Reboot =False
ShutDown=False
DeleteFiles=False
ManualRecord=False
encoding=False

#Pick a Camera Mode. The Value of  5 here is set for a full-format, binned, 8-bit output from a V2 IMX219 camera. 
cam_mode_select =5 # Pick the most suitable mode for your sensor

# set text colour, position and size for timestamp, (Yellow text, near top of screen, in a large font)
colour = (220, 220, 80)
origin = (180, 50)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 2
thickness = 2
# Set Y and UV colour for REC stamp in streaming Frame
y,u,v = 200,90,220

# Make sure that we're in the right directory and then check for
# and, if necessary create a Videos subdirectory and move into it
full_path=os.path.realpath(__file__)
thisdir = os.path.dirname(full_path)
os.chdir (thisdir)
if not os.path.isdir ("Videos"):
    os.mkdir("Videos")

os.chdir("Videos")    

os.environ["LIBCAMERA_LOG_LEVELS"] = "4"  #reduce libcamera messsages

def apply_timestamp(request):
    timestamp = time.strftime("%Y-%m-%d %X")
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)


def capturebuffer():
    global cb_frame
    global buf2
    while not cb_abort:
        buf2 = picam2.capture_array("lores")
        with cb_condition:
            cb_frame = buf2
            cb_condition.notify_all()
            
#mjpeg encode a frame based on example. Can this be improved upon with better/hardware encoder ??
def mjpeg_encode():
    global mjpeg_frame
    while not mjpeg_abort:
        with cb_condition:
            cb_condition.wait()
            yuv = cb_frame
            if encoding:
                # REC stamp in top right of frame
                cv2.putText(yuv,"REC",(w2-72,40),font,1,(y,0,0),1)
                yuv[388:395,472:]=u
                yuv[484:491,472:]=v
                yuv[388:395,216:256]=u
                yuv[484:491,216:256]=v
                
            # Use simplejpeg instead of opencv to go from yuv to jpeg
            buf = encode_jpeg_yuv_planes(
                yuv[:h2],
                yuv.reshape(h2*3,w2//2)[h2*2:h2*2+h2//2],
                yuv.reshape(h2*3,w2//2)[h2*2+h2//2:],
                quality=70) 
            with mjpeg_condition:
                mjpeg_frame = buf
                mjpeg_condition.notify_all()
                
class StreamingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global Message1,Stop_Start,wasbuttonpressed,MotionBtn,TriggerLevel,video_count,Reboot,ShutDown,DeleteFiles,ManualRecord

        content_length = int(self.headers['Content-Length'])  # Get the size of data
        post_data = self.rfile.read(content_length).decode("utf-8")  # Get the data
        post_data = post_data.split("=")[1]  # Only keep the value

        if post_data == 'Manual_Recording_START':
            Message1="Live streaming with Manual Recording ACTIVE"
            Stop_Start="Manual_Recording_STOP"
            ManualRecord=True
            
        elif post_data == 'Manual_Recording_STOP':
            Message1="Live Streaming with Manual Recording Stopped. Flushing Buffer and then waiting for next action"
            Stop_Start="Manual_Recording_START"
            ManualRecord=False
            
        elif post_data == 'DELETE':
            Message1="Press DELETE again to delete all files - or RESET to cancel"
            if DeleteFiles:
                os.system("rm avi*")
                video_count=0
                DeleteFiles =False
                Message1 = "Video files deleted and counter reset"
            else:
                DeleteFiles=True
            
        elif post_data =='RESET':
            Message1="Reset EXIT, DELETE and REBOOT to initial default conditions i.e. Cancel first press"
            Reboot=False
            DeleteFiles=False
            ShutDown=False
           
        elif post_data == 'REBOOT':
            Message1=" Press REBOOT again if you're sure - or RESET to cancel"
            if Reboot:
                os.system("sudo reboot")
            Reboot = True
            
        elif post_data == 'EXIT':
            Message1=" Press EXIT again if you're sure - or RESET to cancel"
            if ShutDown:
                print("Shutting down")
                time.sleep(1)
                os._exit(0)
            ShutDown = True
            
        elif post_data == 'Motion_Detect_ON':
            Message1="Live streaming with Motion Detection ACTIVE"
            MotionBtn="Motion_Detect_OFF"
            TriggerLevel=trigger
            
        elif post_data == 'Motion_Detect_OFF':
            Message1="Live streaming with Motion Detection INACTIVE"
            MotionBtn="Motion_Detect_ON"
            TriggerLevel=9999999 
        
        print("Control button pressed was {}".format(post_data))
        wasbuttonpressed =True
        self._redirect('/index.html')  # Redirect back to the home url
        
    def _redirect(self, path):
        self.send_response(303)
        self.send_header('Content-type', 'text/html')
        self.send_header('Location', path)
        self.end_headers()
        
    def do_GET(self):
        # global mjpeg_condition
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
                    <img src="stream.mjpg" width="800" height="600" />    
                    <p> {ph1}  </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="{ph2}">
                      <input type="submit" name="submit" value="DELETE">
                      <input type="submit" name="submit" value="RESET">
                      <input type="submit" name="submit" value="EXIT">
                      <input type="submit" name="submit" value="REBOOT">
                      <input type="submit" name="submit" value="{ph3}">
                    </form>
                  </center>
                </body>
              </html>
            """.format(ph1=Message1,ph2=Stop_Start, ph3=MotionBtn)

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
    global video_count, wasbuttonpressed, encoding
    prev = None
    encoding = False
    ltime = 0
    start_time=0
    if  not wasbuttonpressed:# Ignore motion check if button was recently pressed
        while True:
            
            with cb_condition:
                cb_condition.wait()
                cur = cb_frame
                
            cur = cur[:h2,:]
            if prev is not None:
                mse = np.mean(np.square(np.subtract(cur, prev)))
                # Uncomment print to monitor background level of noise difference between frames
                # print(mse)
                if mse >TriggerLevel or ManualRecord: 
                    if not encoding:
                        video_count+=1
                        now = datetime.now()
                        date_time = now.strftime("%Y%m%d_%H%M%S")
                        file_title="avi_{:05d}_{}".format(video_count,date_time)
                        fullfile_title=file_title + ".mp4"
                        # Comment out next two lines if the monochrome image of trigger point isn't required 
                        icon=Image.fromarray(cur)
                        icon.save(file_title+"_im.jpg")
                        
                        circ.open_output(PyavOutput(fullfile_title))
                        encoding = True
                        
                        start_time = time.time()
                        print()
                        print(f'New motion detected with a "change value" of  {mse:.0f}')
                        
                    ltime = time.time()
                else:
                    if (encoding and ((time.time() - ltime) > 7)): # Wait for 2 seconds after motion stops before closing + 3 seconds for the buffer length.
                        circ.close_output()
                        encoding = False
                        print("Saving file",file_title)
                        print(f'which holds { (time.time()-start_time):.0f}  seconds worth of video')
                        print()
                        print("Waiting for next trigger")
                        
                        
            prev = cur
            wasbuttonpressed = False

def stream():
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        mjpeg_abort = True
        mjpeg_thread.join()

# Configure Camera and start it running
picam2 = Picamera2()
mode=picam2.sensor_modes[cam_mode_select]
# Remove Transform control or set hflip and vflip to False if no image inversion required
picam2.configure(picam2.create_video_configuration(sensor={"output_size":mode['size'],'bit_depth':mode['bit_depth']},
                                                   controls={'FrameDurationLimits' :  (33333,33333)},
                                                   transform=Transform(hflip=True,vflip=True),
                                                     main={"size": (w,h)},
                                                       lores={"size": (w2, h2)},buffer_count=6))
                 
                
encoder = H264Encoder(1900000, repeat=True,iperiod=45)
picam2.pre_callback = apply_timestamp

#Circular Buffer enabled and started
circ=CircularOutput2(buffer_duration_ms=3000)
encoder.output=[circ]
picam2.start_recording(encoder,circ)
time.sleep(1)

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
motion_thread.join()
# unnecessary joins?
# mjpeg_thread.join()
# stream_thread.join()
# cb_thread.join()