## Start on reboot

First create a systemd file on the 'Ropey-Cam' Raspberry Pi :-

`sudo nano /etc/systemd/system/ropeycam.service`

Then insert the following lines, replacing the two instances of username with *your* username

```
[Unit]
Description=Video streaming and motion triggered video recording
After=multi-user.target
After=network.target

[Service]
Type=simple
User=username
ExecStart=/usr/bin/python3 /home/username/Ropey-Cam/RopeyCamBuffer.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable the service

`sudo systemctl daemon-reload`

`sudo sytemctl enable ropeycam.service
`

After this point the script should be executed on next reboot as well as subsequent reboots.

To temporarily disable, to allow editing of the Ropey-Cam code for example 

`sudo systemctl disable ropeycam.service`

