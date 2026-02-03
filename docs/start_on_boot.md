## Start on reboot

In a headless mode it will be convenient if the application starts on any boot of the system. These instructions describe how to achieve this with a systemd service.


First create a systemd file on the 'Ropey-Cam' Raspberry Pi :-

`sudo nano /etc/systemd/system/ropeycam.service`

Then insert the following lines, (if copying and pasting remember to replace the two instances of username with *your* username)

```
[Unit]
Description=Video streaming and motion triggered video recording
After=multi-user.target
After=network.target

[Service]
Type=simple
User=username
ExecStart=/usr/bin/python3 /home/username/Ropey-Cam/Ropey-Cam.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Ctrl + X, Y followed by Enter to exit and save.

### Inform the system of the new service file

`sudo systemctl daemon-reload`

### Enable the service to start automatically on boot

`sudo systemctl enable ropeycam.service
`

After this point the script should be executed on next reboot as well as subsequent reboots.

### The following summarises common systemd commands for managing the ropeycam.service:

#### To start the service immediately:-

`sudo systemctl start ropeycam.service`

which will manually launch Ropey-Cam without rebooting


#### To stop running the service:-

`sudo systemctl stop ropeycam.service`

Which will halt RopeyCam (will restart on next boot if still enabled)

#### To stop and start the service:-

`sudo systemctl restart ropeycam.service`

Which will apply any configuration changes from ropey.ini

#### To view the service status:-

`sudo systemctl status ropeycam.service`

Which will check if service is active, and present recent logs

#### To enable auto-start on boot
`sudo systemctl enable ropeycam.service`

Which will configure the service to launch after installation

#### To disable auto-start

`sudo systemctl disable ropeycam.service`

Which will prevent service from launching on boot (for code editing)

#### To follow the service logs

`journalctl -u ropeycam.service -f`

Which will begin real-time log monitoring for debugging


