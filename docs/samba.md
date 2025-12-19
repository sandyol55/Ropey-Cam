## Suggestions for setting up a samba share.

These instructions *should* result in a functioning share, but it may be useful to check some online tutorials and find / use an independent set of commands that suit *your* intended use.  e.g. the Global WORKGROUP lines of the configuration file may be unnecessary or incorrect, as may some of the Ropey-Cam share configuration definitions!

Firstly install the samba packages on the 'Ropey-Cam' Raspberry Pi.

`sudo apt install samba samba-common-bin -y`

Then find, backup and modify the smb.conf file.

`cd /etc/samba`

`ls`

`sudo cp smb.conf smb.bak.conf`

`ls`

`sudo nano smb.conf`

Then add the following lines to the file.
In the [global] section below workgroup = WORKGROUP

> wins support = yes

> security = user
 
> passdb backend = tdbsam

> obey pam restrictions = yes

> unix password sync = yes

Then scroll to the bottom of the file and add a new share section as below
with all instances of username replaced by *your* username

```
[Ropey-Cam]
comment = Ropey-Cam on Raspberry Pi
path = /home/username/Ropey-Cam
available = yes
browsable = yes
writeable = yes
read only = no
create mask = 0777
directory mask = 0777
public = no
valid users = username
guest ok = no
```
 Then ctrl +X, Y followed by Enter to save
 
 Next set up a Samba password for *your* username :-
 
 `sudo smbpasswd -a username`
 
 You will now be prompted for a password
 
 Enter password then retype it.

you should get a confirmation.

`Added user username.` 

Then start the samba service.

`sudo systemctl restart smbd`

And to ensure it starts on reboot 

`sudo systemctl enable smbd`

---

### Confirm successful creation

To check for successful creation go to a file manager on a networked device and look for the Ropey-Cam share.

On a Pi with the standard File Manager, open the Go menu and select Network

Or on a Pi with Thunar, open the Go menu and select Browse Network

The network share with the server device name should appear and opening it should lead to the Ropey-Cam share and two other shares defined in the samba configuration.

Open the Ropey-Cam shared folder and the files and the Videos sub-folder should be available for browsing.

---
### Windows (11)

On a Windows (11) PC open the File Explorer and in the Home search bar enter


`\\192.168.0.200\Ropey-Cam`

replacing the IP address with the address of *your* Raspberry Pi server device.

The share should open.

To make a more permanent link got to This PC and from the ... menu select Map Network drive and fill in the prompted details, using the same \\server\share format.

 