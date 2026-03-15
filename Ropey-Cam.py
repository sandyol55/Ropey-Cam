#!/usr/bin/python3

"""
This script controls a single camera connected to the host Raspberry Pi.

It serves a web page with a set of camera and application control
buttons, along with an embedded MJPEG live stream from the camera.

While streaming to the browser, (and also when no browser is connected),
it is looking for change between consecutive frames in the stream and,
if sufficent change is detected, will initiate a high-resolution
mp.4 recording containing a pre-motion buffer, the active motion phase
and a short post-motion segment.

The video will be stored in a Videos sub-directory, along with a .jpg
snapshot file of the trigger moment.

To view the web page, point a browser at the Pi's IP address:8000

Or, from a local browser on the Pi, use 127.0.0.1:8000. (Or both.)
"""

import cv2
import os
import sys
import logging
import socketserver
import configparser
from glob import glob
from shutil import disk_usage
from numpy import copy, array, uint8, argsort, all, bitwise_and
from simplejpeg import encode_jpeg_yuv_planes
from time import strftime, sleep, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Condition, Thread
from picamera2 import Picamera2, MappedArray
from picamera2.encoders import H264Encoder, Quality
from picamera2.outputs import PyavOutput,CircularOutput2
from datetime import datetime
from PIL import Image
from io import BytesIO
from libcamera import Transform

# Set HTML string 'variables' for use in the configurable web page
stop_start = "Manual_Recording_START"
message_1 = "Live streaming with Motion Detection ACTIVE"
motion_button = "Motion_Detect_OFF"

# Assign some colour styles and initialise variables for HTML buttons
ACTIVE = "background-color:orange"
PASSIVE = "background-color:lightblue"
DELETE_PASSIVE = "background-color:lightpink"
DELETE_ACTIVE = "background-color:red"
motion_button_colour = ACTIVE
record_button_colour = PASSIVE
exit_button_colour = PASSIVE
reboot_button_colour = PASSIVE
shutdown_button_colour = PASSIVE
delete_button_colour = DELETE_PASSIVE

# Ensure the current working directory is the one containing the script
# and create a Videos sub-directory, if necessary
full_path=os.path.realpath(__file__)
thisdir = os.path.dirname(full_path)
os.chdir (thisdir)
if not os.path.isdir("Videos"):
    os.mkdir("Videos")

# Get configuration constants from .ini file
config_file = 'ropey.ini'
config = configparser.ConfigParser()

# If no file found, print an error message and create a blank file.
if not os.path.exists(config_file):
    print(f"Configuration file {config_file} does not exist.")
    print("Using defaults.")
    config['ropey'] = {}

else:
    try:
        config.read(config_file)
    except configparser.Error as e:
        print(f"Error reading configuration file: {e}")

# Set up the configuration variables/CONSTANTS from the stored data
# Recording (hi-res) and streaming (lo-res) video resolutions
VIDEO_WIDTH = config.getint('ropey','video_width', fallback =1280)
STREAM_WIDTH = config.getint('ropey','stream_width', fallback = 640)
ASPECT_RATIO = config.getfloat('ropey', 'aspect_ratio', fallback = 1.777)

# Calculate heights from width and aspect ratio. HEIGHTs are made even.
VIDEO_HEIGHT = int(2* ((VIDEO_WIDTH/ASPECT_RATIO) // 2))
STREAM_HEIGHT = int(2 * ((STREAM_WIDTH/ASPECT_RATIO) // 2))

# Frame to frame change limit for motion detection
trigger_level = config.getint('ropey','trigger_level', fallback = 400)

# Save a copy of the trigger_level. Use in re-enabling motion detection.
reset_trigger = trigger_level

# Mode parameter that controls key sensor parameters
SENSOR_MODE = config.getint('ropey','sensor_mode', fallback = 1)

# Conservatively 15fps for pre Pi3 models, 25 or 30fps for later models.
FRAMES_PER_SECOND = config.getint('ropey','frames_per_second', fallback = 20)

# Length of time (seconds) inside circular ring buffer
BUFFER_SECONDS = config.getint('ropey','buffer_seconds', fallback =3)

# Number of consecutive frames with motion to trigger recording
AFTER_FRAMES = config.getint('ropey','after_frames', fallback = 5)

# Post-motion additional recording time (seconds)
POST_ROLL = config.getint('ropey','post_roll', fallback = 3)

# Transform controls
HFLIP = config.getboolean('ropey','hflip', fallback = False)
VFLIP = config.getboolean('ropey','vflip', fallback = False)

# Video file counter, to retain consecutive file numbering after restarts
video_count = config.getint('ropey','video_count', fallback = 0)

# Limit before file deletion is activated
MAX_DISK_USAGE = config.getfloat('ropey','max_disk_usage', fallback = 0.8)

# Check if motion mask is specified
apply_motion_mask = config.getboolean('ropey','apply_motion_mask', fallback = False)

# And if it is, load the mask_file_name which should be a .pgm filename
if apply_motion_mask:
    mask_name = config.get('ropey', 'mask_name', fallback = 'default_mask.pgm')
    mask_image = Image.open(mask_name)

    # Convert the pgm image to a Numpy array
    mask_array = array(mask_image)

# Now a camera controls section. Get the values and populate controls {}
controls={}

brightness = config.getfloat('ropey', 'brightness' ,fallback = 0.0)
controls['Brightness'] = brightness

contrast = config.getfloat('ropey', 'contrast' ,fallback = 1.0)
controls['Contrast'] = contrast

saturation = config.getfloat('ropey', 'saturation' ,fallback = 1.0)
controls['Saturation'] = saturation

ae_constraint_mode = config.getint('ropey','aeconstraintmode' ,fallback = 0)
controls['AeConstraintMode'] = ae_constraint_mode

ae_enable = config.getboolean('ropey','aeenable', fallback = True)
controls['AeEnable'] = ae_enable

exposuretime = config.getint('ropey', 'exposuretime', fallback = 1000)
analoguegain = config.getfloat('ropey', 'analoguegain', fallback = 1.0)
if not ae_enable:
    controls['ExposureTime'] = exposuretime
    controls['AnalogueGain'] = analoguegain

ae_exposure_mode = config.getint('ropey','aeexposuremode' ,fallback = 0)
controls['AeExposureMode'] = ae_exposure_mode

exposurevalue = config.getfloat('ropey', 'exposurevalue' ,fallback = 0.0)
controls['ExposureValue'] = exposurevalue

awb_mode = config.getint('ropey','awbmode' ,fallback = 0)
controls['AwbMode'] = awb_mode

awb_enable = config.getboolean('ropey','awbenable' ,fallback = True)
controls['AwbEnable'] = awb_enable

# If Auto White Balance disabled get and create ColourGains tuple
if not awb_enable:
    redcolourgain = config.getfloat('ropey','redcolourgain', fallback = 1.0)
    bluecolourgain = config.getfloat('ropey','bluecolourgain', fallback = 1.0)
    colourgains = (redcolourgain,bluecolourgain)
    controls['ColourGains'] = colourgains

# Check for supported Auto Focus and skip these controls if not available
has_autofocus = config.getboolean('ropey', 'hasautofocus', fallback = False)

if has_autofocus:

    af_metering = config.getint('ropey','afmetering' ,fallback = 0)
    controls['AfMetering'] = af_metering

    af_mode = config.getint('ropey','afmode' ,fallback = 0)
    controls['AfMode'] = af_mode 

    lensposition = config.getfloat('ropey', 'lensposition' ,fallback = 1.0)
    controls['LensPosition'] = lensposition

    af_range = config.getint('ropey','afrange' ,fallback = 0)
    controls['AfRange'] = af_range 

# Not currently stored in config file
INF_TRIGGER_LEVEL = 999999  # Impossibly high to deactiviate detection

# State variables for inter thread control
was_button_pressed = False
should_reboot = False
should_exit = False
should_delete_files = False
set_manual_recording = False
should_shutdown = False
is_recording = False

# Misc constants and variables
total_motion = 0  # Total area of motion detected via frame differencing
kernel = array((9,9), dtype=uint8)  # Used in detection function
mask_name='' # Predefine for use later
most_recent_page ='/index.html' # Prepare for guided page redirects


# Set text colour, position and size for timestamp in recorded files.
# Yellow text, near top left of screen, in a small font
colour = (240, 240, 50)
origin = (8, 24)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

# Set Y and u,v colour for a red block REC stamp in streaming frames
Y,u,v = 190, 130, 230

# Set Y for change / trigger level stamp in streaming frames.
# White stamp so no need for u,v values.
Y_STREAM_STAMP = 255


class StreamingServer(socketserver.ThreadingMixIn, HTTPServer):
    """
    ThreadingMixIn: Creates new thread for each client connection
    allow_reuse_address:
    Allows immediate restart without "address already in use" errors
    daemon_threads:
    Client handler threads terminate when main thread exits
    """

    allow_reuse_address = True
    daemon_threads = True


class StreamingHandler(BaseHTTPRequestHandler):
    """
    Handles the streaming in response to the GET requests from the dynamically configurable page
    and the actions to take based on the POST requests from the client
    """
    def _redirect(self, path):
        self.send_response(303)
        self.send_header('Content-type', 'text/html')
        self.send_header('Location', path)
        self.end_headers()

    def do_POST(self):
        global message_1, stop_start, motion_button,\
               trigger_level,reset_trigger, should_delete_files,\
               should_shutdown, should_exit, should_reboot, mjpeg_abort,\
               video_count, set_manual_recording, post_data,\
               motion_button_colour, record_button_colour,\
               exit_button_colour, reboot_button_colour,\
               shutdown_button_colour, delete_button_colour,\
               VIDEO_WIDTH,STREAM_WIDTH,FRAMES_PER_SECOND, most_recent_page

        content_length = int(self.headers['Content-Length'])  # Get data length
        post_data = self.rfile.read(content_length).decode("utf-8")  # Get the data

        # If multi-parameter post data is submitted, split into items
        if most_recent_page =="/configuration.html" and "&" in post_data  :
            conf_items = post_data.split("&")
            for items in conf_items:
                name = items.split("=")[0]
                value = items.split("=")[1]
                # And populate config for later saving to ini file
                if value != '':
                    config.set('ropey',name,value)

        elif most_recent_page =="/controls.html":
            conf_items = post_data.split("&")
            for items in conf_items:
                name = items.split("=")[0]
                str_value = items.split("=")[1]
                # And populate config for later saving to ini file
                # But also set a controls dictionary and apply it 'on the fly'
                if str_value != '':
                    if name == "ColourGains":
                        Rg = float(str_value.split("-")[0])
                        Bg = float(str_value.split("-")[1])
                        value=(Rg,Bg)
                        config.set('ropey',"redcolourgain",str(Rg))
                        config.set('ropey',"bluecolourgain",str(Bg))
                    else:
                        value = eval(str_value)

                    if ("Af" in name or "Lens" in name)  and not has_autofocus:
                        continue
                    config.set('ropey',name,str_value)
                    controls[name] = value

                    if name == "AeEnable" and value == True:
                        controls.pop("ExposureTime", None)
                        controls.pop("AnalogueGain",None)

                    if name == "AwbEnable" and value == True:
                        controls.pop("ColourGains", None)

            picam2.set_controls(controls)

        else:
            post_data = post_data.split("=")[1]  # Value from single button presses

        if post_data == 'Manual_Recording_START':
            message_1 = "Live streaming with Manual Recording ACTIVE"
            stop_start = "Manual_Recording_STOP"
            record_button_colour = ACTIVE
            set_manual_recording = True

        elif post_data == 'Manual_Recording_STOP':
            message_1 = """Live Streaming with Manual Recording Stopped.
             (Short delay to close recording ..
              then wait for next action)."""
            stop_start = "Manual_Recording_START"
            record_button_colour = PASSIVE
            set_manual_recording = False

        elif post_data == 'DELETE_ALL_FILES':
            message_1 = """Press DELETE_ALL_FILES again to delete
             all files - or RESET to cancel"""
            if should_delete_files:
                os.system("rm Videos/*.mp4 Videos/*.jpg")
                video_count = 0
                should_delete_files = False
                delete_button_colour = DELETE_PASSIVE
                message_1 = "Video files deleted and video counter reset"
            else:
                should_delete_files = True
                delete_button_colour = DELETE_ACTIVE

        elif post_data =='RESET':
            message_1 = """Reset EXIT, DELETE, REBOOT and SHUTDOWN to
             initial default conditions i.e. Cancel the first press"""
            should_reboot = False
            should_delete_files = False
            should_exit = False
            should_shutdown = False
            exit_button_colour = PASSIVE
            reboot_button_colour = PASSIVE
            shutdown_button_colour = PASSIVE
            delete_button_colour = DELETE_PASSIVE

        elif post_data == 'REBOOT':
            message_1 = """ Press REBOOT again if you're sure - or RESET
             to cancel. (Short delay while files are saved)."""
            if should_reboot:
                cleanup()
                os.system("sudo reboot now")
            should_reboot = True
            reboot_button_colour = ACTIVE

        elif post_data == 'SHUTDOWN':
            message_1 = """Press SHUTDOWN again if you're sure - or 
            RESET to cancel. (Short delay while files are saved)."""
            if should_shutdown:
                cleanup()
                os.system("sudo shutdown now")
            should_shutdown = True
            shutdown_button_colour = ACTIVE

        elif post_data == 'EXIT':
            message_1 = """ Press EXIT again if you're sure - or RESET
             to cancel. (Short delay while files are saved)."""
            if should_exit:
                cleanup()
                mjpeg_abort = True
                sys.exit(0)
            should_exit = True
            exit_button_colour = ACTIVE

        elif post_data == 'Motion_Detect_ON':
            message_1 = "Live streaming with Motion Detection ACTIVE"
            motion_button = "Motion_Detect_OFF"
            motion_button_colour = ACTIVE
            trigger_level = reset_trigger

        elif post_data == 'Motion_Detect_OFF':
            message_1 = "Live streaming with Motion Detection INACTIVE"
            motion_button = "Motion_Detect_ON"
            motion_button_colour = PASSIVE
            trigger_level = INF_TRIGGER_LEVEL

        elif post_data == 'Inc_TriggerLevel':
            message_1 = """Decreasing motion sensitivity by increasing
             trigger level"""
            if trigger_level < INF_TRIGGER_LEVEL:
                trigger_level += 10
                reset_trigger += 10
            config.set('ropey','trigger_level',str(trigger_level))

        elif post_data == 'Dec_TriggerLevel':
            message_1 = "Increasing motion sensitivity by decreasing trigger level"
            if trigger_level > 10:
                trigger_level -= 10
                reset_trigger -= 10
            config.set('ropey','trigger_level',str(trigger_level))

        print("Control button pressed was {}".format(post_data))
        print()
        
        self._redirect(most_recent_page)


    def log_message(self, format, *args):
        return  # This re-definition suppresses the log_message output

    def _send_response_headers(self, content):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        global most_recent_page
        # HTML descriptions of dynamic home and configuration pages
        HOMEPAGE = """\
            <!DOCTYPE html>
              <html lang="en">
                <head>
                  <meta charset="UTF-8">
                  <meta name="viewport" content="width=device-width, initial-scale=1.0">
                  <title>Ropey-Cam</title>
                </head>
                <body>
                  <center>
                    <h2>Ropey-Cam  Live Streaming with motion-triggered Recording</h2>
                    <img src="stream.mjpg" width="{ph1}" height="{ph2}" />
                    <p> {ph3}  </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="{ph4}"style = "{ph6}">
                      <input type="submit" name="submit" value="Inc_TriggerLevel">
                      <input type="submit" name="submit" value="Dec_TriggerLevel">
                      <input type="submit" name="submit" value="{ph5}" style = "{ph7}">
                    </form>
                    <p> </p>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="DELETE_ALL_FILES" style = "{ph11}">
                      <input type="submit" name="submit" value="EXIT" style = "{ph8}">
                      <input type="submit" name="submit" value="RESET" style = "background-color:lightgreen;">
                      <input type="submit" name="submit" value="REBOOT" style ="{ph9}">
                      <input type="submit" name="submit" value="SHUTDOWN" style= "{ph10}">
                    </form>
                    <br>
                      <a href="/configuration.html" style="border: 1px solid lightgrey; padding: 6px;background-color: lightgrey; text-decoration: none;">Configuration  Entry  Page</a>
                      <a href="/controls.html" style="border: 1px solid lightgrey; padding: 6px;background-color: lightgrey; text-decoration: none;">Camera Control Entry Page</a>
                  </center>
                </body>
              </html>
            """.format(ph1 = STREAM_WIDTH,
                       ph2 = STREAM_HEIGHT,
                       ph3 = message_1,
                       ph4 = motion_button,
                       ph5 = stop_start,
                       ph6 = motion_button_colour,
                       ph7 = record_button_colour,
                       ph8 = exit_button_colour,
                       ph9 = reboot_button_colour,
                       ph10 = shutdown_button_colour,
                       ph11 = delete_button_colour)

        CONFPAGE = """\
            <!DOCTYPE html>
              <html lang="en">
                <html>
                <head><title>Configuration Entry</title></head>
                <body>
                  <center>
                  <a href="/"style="border: 1px solid lightgrey; padding: 10px;background-color: lightgrey; text-decoration: none;">Back to Home / Streaming Page </a>
                    <h2>Ropey-Cam Configuration Entry Page</h2>
                    <p> </p>
                    <form action="/" method="POST">
                      <label for "VIDEO_WIDTH">VIDEO WIDTH </label>
                      <input type="number" id="VIDEO_WIDTH" name="VIDEO_WIDTH" placeholder = {ph12} min="1024"  max="1920"step="32" style ="margin-right: 12px"  >

                      <label for "STREAM_WIDTH">STREAM WIDTH</label>
                      <input type="number" id="STREAM_WIDTH" name="STREAM_WIDTH" placeholder = {ph13} min="512" max="1280"step="128" style ="margin-right: 12px">

                      <label for "ASPECT_RATIO">ASPECT RATIO</label>
                      <input type="number" id="ASPECT_RATIO" name="ASPECT_RATIO" placeholder = {ph14} min="1.333" max="2.221"step=".444">
                      <p></p>
                      <label for "FRAMES_PER_SECOND">FPS</label>
                      <input type="number" id="FRAMES_PER_SECOND" name="FRAMES_PER_SECOND" placeholder = {ph15} min="10" max="30"step="5" style="margin-right: 20px">

                      <label for "SENSOR_MODE">MODE</label>
                      <input type="number" id="SENSOR_MODE" name="SENSOR_MODE" placeholder = {ph16} min="0" max={ph17} style="margin-right: 20px">

                      <label for "HFLIP Off"> Hflip .({ph18}).Off </label>
                      <input type="radio" name="HFLIP" value = False >

                      <label for "HFLIP On">On</label>
                      <input type="radio" name="HFLIP" value = True style="margin-right: 30px">

                      <label for "VFLIP Off"> Vflip .({ph19}).Off </label>
                      <input type="radio" name="VFLIP" value = False ">

                      <label for "VFLIP On">On</label>
                      <input type="radio" name="VFLIP" value = True>
                      <p></p>
                      <label for "trigger_level">Trigger @</label>
                      <input type="text" size = 4 id="trigger_level" name="trigger_level" placeholder = {ph20}>

                      <label for "AFTER_FRAMES"># Frames</label>
                      <input type="number" style = "width: 40px" id="AFTER_FRAMES" name="AFTER_FRAMES" placeholder = {ph21} min="0" max="50">

                      <label for "BUFFER_SECONDS"> Buffer</label>
                      <input type="number" style = "width: 40px" id="BUFFER_SECONDS" name="BUFFER_SECONDS" placeholder ={ph22} min ="1" max="10">

                      <label for "POST_ROLL">Post Roll</label>
                      <input type="number" style = "width: 40px" id="POST_ROLL" name = "POST_ROLL" placeholder = {ph23} min ="0" max="10">

                      <label for "MAX_DISK_USAGE">Storage Limit</label>
                      <input type="number" style = "width: 50px" id="MAX_DISK_USAGE" name = "MAX_DISK_USAGE" placeholder = {ph24} min ="0.1" max="0.975" step="0.025">
                      <p></p>
                      <label for "Motion Mask Off"> Motion Mask .({ph25}). Off</label>
                      <input type="radio" name="apply_motion_mask" value = False>

                      <label for "Motion Mask On"> On</label>
                      <input type="radio" name="apply_motion_mask" value = True style = "margin-right: 50px">

                      <label for "mask_name">Mask File Name.pgm</label>
                      <input type="text" id="mask_name" name="mask_name" placeholder = {ph26}>
                      <p></p>
                      <input type="submit" value="Submit to apply changes to internal config file">
                    </form>
                    <p></p>
                    <h3>The submitted configuration change takes effect on restart/reboot</h3>
                    <form action="/" method="POST">
                      <input type="submit" name="submit" value="EXIT" style ="{ph27}">
                      <input type="submit" name="submit" value="REBOOT" style ="{ph28}">
                    </form>
                  </center>
                </body>
                </html>
                """.format(ph12 = VIDEO_WIDTH,
                           ph13 = STREAM_WIDTH,
                           ph14 = ASPECT_RATIO,
                           ph15 = FRAMES_PER_SECOND,
                           ph16 = SENSOR_MODE,
                           ph17 = str(max_mode),
                           ph18 = str(HFLIP),
                           ph19 = str(VFLIP),
                           ph20 = trigger_level,
                           ph21 = AFTER_FRAMES,
                           ph22 = BUFFER_SECONDS,
                           ph23 = POST_ROLL,
                           ph24 = MAX_DISK_USAGE,
                           ph25 = str(apply_motion_mask),
                           ph26 = mask_name,
                           ph27 = exit_button_colour,
                           ph28 = reboot_button_colour
                           )
        CONTROLPAGE = """\
            <!DOCTYPE html>
              <html lang="en">
                <html>
                  <title>Camera Controls Entry</title>
                   </head>
                        <body>
                          <center>
                          <a href="/" style="border: 1px solid lightgrey; padding: 10px;background-color: lightgrey; text-decoration: none;">Back to Home / Streaming Page </a>
                            <h3>Ropey-Cam Camera Control Entry Page</h3>
                            <p> </p>
                            <form action="/" method = "POST">
                                <label for "Brightness"> Brightness (-1.0 through (0.0)  to   +1.0)  </label>
                                <input type = "number" id = "Brightness" name = "Brightness"  min ="-1.0" max="1.0" step="0.025" value ={ph30} >
                              <p></p> 
                                <label for "Contrast"> Contrast (0.0 through (1.0)  to  32.0)</label>
                                <input type = "number" id = "Contrast" name = "Contrast" min ="0.0" max="32.0" step="0.025" value ={ph31} >
                              <p></p>
                                <label for "Saturation"> Saturation (0.0 through (1.0)  to  32.0)</label>
                                <input type = "number" id = "Saturation" name = "Saturation" min ="0.0" max="32.0" step="0.025" value ={ph32} >
                                <p></p>
                              <p></p>
                                <label for = "AeConstraintMode"> AeConstraintMode :</label>
                                  <select id = "AeConstraintMode" name ="AeConstraintMode">
                                    <option value=""></option>
                                    <option value = 0> Normal </option>
                                    <option value = 1> Highlight </option>
                                    <option value = 2> Shadows </option>
                                    <option value = 3> Custom </option>
                                  </select>
                              <p></p>
                                <label for = "AeEnable"> AeEnable :</label>
                                  <select id = "AeEnable" name = "AeEnable">
                                    <option value = ""></option>
                                    <option value = True > True </option>
                                    <option value = False > False </option>
                                  </select>
                              <p></p>
                                <label for ="ExposureTime"> ExposureTime (microseconds)</label>
                                <input type = "number" id = "ExposureTime" name = "ExposureTime" placeholder = {ph34}>
                              <p></p>
                                <label for = "AnalogueGain">AnalogueGain</label>
                                <input type = "number" id = "AnalogueGain" name = "AnalogueGain" placeholder = {ph35}> 
                              <p></p>
                                <label for = "AeExposureMode"> AeExposureMode :</label>
                                  <select id = "AeExposureMode" name="AeExposureMode">
                                    <option value = ""></option>
                                    <option value = 0> Normal </option>
                                    <option value = 1> Short </option>
                                    <option value = 2> Long </option>
                                    <option value = 3> Custom </option>
                                  </select>
                              <p></p>
                                <label for = "ExposureValue"> ExposureValue (-8.0 through (0.0)  to  8.0 ) </label>
                                <input type = "number" id = "ExposureValue" name = "ExposureValue" min ="-8.0" max="8.0" step="0.05" value ={ph36} >
                              <p></p>
                                <label for = "AeMeteringMode"> AeMeteringMode :</label>
                                  <select id = "AeMeteringMode" name = "AeMeteringMode">
                                    <option value = ""></option>
                                    <option value = 0> CentreWeighted </option>
                                    <option value = 1> Spot </option>
                                    <option value = 2> Matrix </option>
                                    <option value = 3> Custom </option>
                                  </select>
                              <p></p>
                                <label for = "AwbMode"> AwbMode :</label>
                                  <select id = "AwbMode" name = "AwbMode">
                                    <option value = ""></option>
                                    <option value = 0> Auto </option>
                                    <option value = 1> Tungsten </option>
                                    <option value = 2 >Fluorescent </option>
                                    <option value = 3> Indoor </option>
                                    <option value = 4> Daylight </option>
                                    <option value = 5> Cloudy</option>
                                    <option value = 6> Custom </option>
                                  </select>
                              <p></p>
                                <label for ="AwbEnable"> AwbEnable :</label>
                                  <select id = "AwbEnable" name ="AwbEnable">
                                    <option value = ""> </option>
                                    <option value= True> True </option>
                                    <option value = False> False </option>
                                  </select>
                              <p></p>
                                <label for = "ColourGains"> ColourGains (Rg hyphen Bg) Rg-Bg</label>
                                <input type = "text" id = "ColourGains" name = "ColourGains">
                              <p></p>
                              <label for ="AfMetering"> AfMetering :</label>
                                <select id = "AfMetering" name ="AfMetering">
                                  <option value = ""> </option>
                                  <option value = 0 > Auto </option>
                                  <option value = 1 > Windows </option>
                                </select>
                              <p></p>
                                <label for = "AFMode"> AfMode :</label>
                                  <select id = "AfMode" name="AfMode">
                                    <option value = ""></option>
                                    <option value = 0> Manual </option>
                                    <option value = 1> Auto </option>
                                    <option value = 2> Continuous </option>
                                  </select>
                              <p></p>    
                                <label for "LensPosition"> LensPosition (0.0 through (1.0)  to   15.0)  </label>
                                <input type = "number" id = "LensPosition" name = "LensPosition" placeholder = "1.0"  >
                              <p></p>
                                <label for = "AFRange"> AfRange :</label>
                                  <select id = "AfRange" name="AfRange">
                                    <option value = ""></option>
                                    <option value = 0> Normal </option>
                                    <option value = 1> Macro </option>
                                    <option value = 2> Full </option>
                                  </select>
                              <p></p> 
                                <input type = "submit" value = "Submit to apply control changes to internal config file and immediately to camera">  
                            </form>
                          </center>
                         </body>
                        </html>
                        """.format(ph30 = controls["Brightness"],
                                   ph31 = controls["Contrast"],
                                   ph32 = controls["Saturation"],
                                   ph34 = exposuretime,
                                   ph35 = analoguegain,
                                   ph36 = controls["ExposureValue"])

        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()

        elif self.path == '/index.html':
            most_recent_page = '/index.html'
            content = HOMEPAGE.encode('utf-8')
            self._send_response_headers(content)

        elif self.path == '/configuration.html':
            most_recent_page = '/configuration.html'
            content = CONFPAGE.encode('utf-8')
            self._send_response_headers(content)

        elif self.path == '/controls.html':
            most_recent_page = '/controls.html'
            content = CONTROLPAGE.encode('utf-8')
            self._send_response_headers(content)

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
                pass

        else:
            self.send_error(404)
            self.end_headers()


def update_ini_file():
    global VIDEO_WIDTH
    # Sanity check for oversize 4:3 video frame
    if VIDEO_WIDTH > 1600 and ASPECT_RATIO == 1.333:
        VIDEO_WIDTH = 1600
    with open('ropey.ini', 'w') as configfile:
        config.write(configfile)


def apply_timestamp(request):
    clock_time = datetime.now()
    milliseconds = clock_time.microsecond // 1000
    timestamp = f"""Ropey-Cam     {clock_time:%d/%m/%Y      %H:%M:%S}.{milliseconds:03d}     {total_motion:06d}"""
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)


def capturebuffer():
    global cb_frame
    while True:
        buf2 = picam2.capture_array("lores")
        with cb_condition:
            cb_frame = buf2
            cb_condition.notify_all()


def yuv420_jpeg(yuvframe, height, width, quality):
                jpeg = encode_jpeg_yuv_planes(
                yuvframe[:height],
                yuvframe.reshape(height * 3, width // 2)[height * 2 : height * 2 + height // 2],
                yuvframe.reshape(height * 3, width // 2)[height * 2 + height // 2 :],
                quality=quality)
                return jpeg


def cleanup():
    global trigger_level, set_manual_recording,video_count
    set_manual_recording = False
    trigger_level = INF_TRIGGER_LEVEL
    config.set('ropey','video_count',str(video_count))
    update_ini_file()
    print("Closing any active recordings, writing ropey.ini file and waiting to", post_data)
    print()
    sleep(BUFFER_SECONDS + POST_ROLL + 2)


def mjpeg_encode():  # Superimpose data on YUV420 frames then encode them as jpegs.
    global mjpeg_frame
    while not mjpeg_abort:
        with cb_condition:
            cb_condition.wait()
            yuv = copy(cb_frame)

            # embed result of frame to frame difference calculation,
            #  versus current trigger level, in top left of frame.
            motion_stamp = f"{total_motion:06d}/{trigger_level:06d}"

            cv2.putText(yuv, motion_stamp, (12, 22), font, scale ,
                        (Y_STREAM_STAMP, 0, 0), thickness)

            if is_recording:
                # put a red REC stamp in top right of frame
                cv2.putText(yuv,"REC",(STREAM_WIDTH - 72, 22), font, 1, (Y, 0, 0), 2)
                yuv[STREAM_HEIGHT : STREAM_HEIGHT + 7, STREAM_WIDTH - 40:] = u
                yuv[STREAM_HEIGHT + STREAM_HEIGHT // 4 : STREAM_HEIGHT + STREAM_HEIGHT // 4 + 7, STREAM_WIDTH - 40 :] = v
                yuv[STREAM_HEIGHT : STREAM_HEIGHT + 7, STREAM_WIDTH // 2 - 40 : STREAM_WIDTH // 2] = u
                yuv[STREAM_HEIGHT + STREAM_HEIGHT // 4 : STREAM_HEIGHT + STREAM_HEIGHT // 4 + 7, STREAM_WIDTH // 2 - 40 : STREAM_WIDTH // 2] = v

            # Convert frame from yuv to jpeg
            buf = yuv420_jpeg(yuv, STREAM_HEIGHT, STREAM_WIDTH, 65)
            with mjpeg_condition:
                mjpeg_frame = buf
                mjpeg_condition.notify_all()


def open_files(frame):
    global video_count, file_title, video_file_title
    current_frame = frame
    video_count += 1

    # Prepare file names based on date and time
    now = datetime.now()
    date_time = now.strftime("%Y%m%d_%H%M%S")
    file_title = "Videos/{:05d}_{}".format(video_count, date_time)
    video_file_title = file_title + ".mp4"

    # save jpeg of trigger moment
    snapshot = yuv420_jpeg(current_frame, STREAM_HEIGHT, STREAM_WIDTH, 90)
    icon = Image.open(BytesIO(snapshot))
    icon.save(file_title + ".jpg")

    # Open output video file
    circ.open_output(PyavOutput(video_file_title))
    print(f'New recording starting after "trigger value" of  {total_motion:.0f}')
    print()


def close_files(start_time, close_time):
    circ.close_output()
    print("Closing and saving file",video_file_title, end=", ")
    print(f'which holds approx { (close_time - start_time):.0f} seconds worth of video')
    print()
    print("Waiting for next trigger or button initiated command.")
    print()


def control_storage():
    """ If running low on disk space delete oldest file pair
        """
    total, used, _ = disk_usage("Videos")
    used_space = used / total
    if used_space > MAX_DISK_USAGE:
        oldest_snapshot = sorted(glob("Videos/*.jpg"), key = os.path.getctime)[0]
        oldest_video_file=sorted(glob("Videos/*.mp4"), key = os.path.getctime)[0]
        os.remove(oldest_snapshot)
        os.remove(oldest_video_file)


def get_mask(frame1, frame2, kernel=array((9,9), dtype=uint8)):
    """ Obtains image mask
        Inputs:
            frame1 - Grayscale frame at time t
            frame2 - Grayscale frame at time t + 1
            kernel - (NxN) array for Morphological Operations
        Outputs:
            mask - Thresholded mask for moving pixels
        """

    frame_diff = cv2.subtract(frame2, frame1)

    # blur the frame difference
    frame_diff = cv2.medianBlur(frame_diff, 3)

    mask = cv2.adaptiveThreshold(frame_diff, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,\
            cv2.THRESH_BINARY_INV, 11, 3)

    mask = cv2.medianBlur(mask, 3)

    # morphological operations
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    return mask


def get_contour_detections(mask, thresh=20):
    """ Obtains initial proposed detections from contours discovered on the mask.
        Scores are taken as the bbox area, larger is higher.
        Inputs:
            mask - thresholded image mask
            thresh - threshold for contour size
        Outputs:
            detections - array of proposed detection bounding boxes and scores [[x1,y1,x2,y2,s]]
        """
    # get mask contours
    contours, _ = cv2.findContours(mask,
                                   cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_TC89_L1)
    detections = []
    for cnt in contours:
        x,y,w,h = cv2.boundingRect(cnt)
        area = w*h
        if area > thresh:
            detections.append([x,y,x+w,y+h, area])

    return array(detections)


def motion():
    global  is_recording, total_motion, video_count
    previous_frame = None
    motion_frames = 0
    previous_motion_score = 0

    while True:
        with cb_condition:
            cb_condition.wait()
            current_frame = copy(cb_frame)
            grey_frame=current_frame[:STREAM_HEIGHT, :]

        if previous_frame is not None:
            total_motion = 0

            # Apply motion mask if specified
            if apply_motion_mask:
                grey_frame = bitwise_and(grey_frame,mask_array)

            # get image mask for moving pixels
            mask = get_mask(previous_grey_frame, grey_frame, kernel)

            # get initially proposed detections from contours
            detections = get_contour_detections(mask, thresh = 20)

            # if there are any detections use the areas to give 'motion scores'
            if detections.size > 0:
                scores = detections[:, -1]
                total_motion = (scores.sum() + previous_motion_score) // 2

            motion_frames = motion_frames + 1 if total_motion > trigger_level else 0
            
            if motion_frames >= AFTER_FRAMES or set_manual_recording:
                if not is_recording:
                    is_recording = True
                    start_time = time()
                    open_files(current_frame)
                last_motion_time = time()
            else:
                # Wait for POST_ROLL + BUFFER_SECONDS seconds after motion stops
                # Then close the video recording file and check the disk usage
                if (is_recording and ((time() - last_motion_time) > (BUFFER_SECONDS + POST_ROLL))):
                    is_recording = False
                    close_time = time()
                    close_files(start_time, close_time)
                    control_storage()

        previous_frame = current_frame
        previous_grey_frame = grey_frame
        previous_motion_score = total_motion


def stream():
    global trigger_level, set_manual_recording, mjpeg_abort
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        # Shouldn't ever reach this but....
        cleanup()
        mjpeg_abort = True
        sys.exit(0)


os.environ["LIBCAMERA_LOG_LEVELS"] = "4"  # reduce libcamera messsages

# Configure Camera and start it running
# Instantiate camera
picam2 = Picamera2()

# Interrogate the sensor to find the supported modes
modes = picam2.sensor_modes
max_mode = len(modes) -1

# And select the mode to configure
mode = modes[SENSOR_MODE]

# Create the stored configuration
picam2.configure(picam2.create_video_configuration(sensor = {"output_size":mode['size'],'bit_depth':mode['bit_depth']},
                                                   controls = {'FrameRate' : FRAMES_PER_SECOND},
                                                   transform = Transform(hflip=HFLIP, vflip=VFLIP),
                                                   main = {"size" : (VIDEO_WIDTH, VIDEO_HEIGHT),'format' : "BGR888"},
                                                   lores = {"size" : (STREAM_WIDTH, STREAM_HEIGHT),'format' : "YUV420"}, buffer_count = 10))
# Define the encoder properties
encoder = H264Encoder(repeat = True, iperiod = FRAMES_PER_SECOND)

# Set the timestamp callback
picam2.pre_callback = apply_timestamp

# Set the stored set of camera controls
picam2.set_controls(controls)

# Circular Buffer properties enabled and started
circ = CircularOutput2(buffer_duration_ms = BUFFER_SECONDS * 1000)
encoder.output = [circ]
picam2.start_recording(encoder, circ, quality = Quality.VERY_HIGH)

# Short delay to allow camera auto algorithms to settle
sleep(1)

# Capture the current metadata for use in finding some current camera parameters
metadata = picam2.capture_metadata()
exposuretime = metadata["ExposureTime"]
analoguegain = metadata["AnalogueGain"]

# Check if this sensor supports AutoFocus
if "AfState" in metadata:
    config.set('ropey','hasautofocus', 'True')

# Start up the various 'infinite' threads.
cb_frame = None
buf2 = None
cb_condition = Condition()
cb_thread = Thread(target=capturebuffer, daemon = True)
cb_thread.start()

mjpeg_abort = False
mjpeg_frame = None
mjpeg_condition = Condition()
mjpeg_thread = Thread(target=mjpeg_encode, daemon = False)
mjpeg_thread.start()

stream_thread = Thread(target=stream, daemon = True)
stream_thread.start()

motion_thread = Thread(target=motion, daemon = True)
motion_thread.start()

# Join an 'infinite' thread to keep main thread alive 'til ready to exit by 'aborting' mjpeg thread
mjpeg_thread.join()
