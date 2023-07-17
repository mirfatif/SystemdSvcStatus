# SystemD Service Status

Monitor `systemd` services status.

Run `systemd_svc_watcher.py` in background (preferably as a `systemd` service). It shows a desktop notification when a
service dies.
Use `list_systemd_svc.py` from terminal to view a list of all services.

```
~$ sysd_services.py -h

Usage:
	sysd_services.py [OPTIONS]

Options:
	-h|--help                  Show help
	--user                     Show session services
	--desc-file                Show service description and file
	--sort-by=<SORT_KEY>       Sort column
	--type=<TYPE>              Types
	--loaded=<LOADED>          Loaded states
	--active=<ACTIVE>          Active states
	--sub-active=<SUB_ACTIVE>  Sub-active states
	--file-state=<STATE>       File states
	--file-preset=<PRESET>     File presets

	SORT_KEY:
		 loaded, active, sub-active, file-state, file-preset

	All filters are comma-separated lists.


	TYPE:
		 all, automount, device, mount, path, scope, service, slice, socket, target, timer

	LOADED:
		 loaded, not-found

	ACTIVE:
		 active, inactive, failed

	SUB_ACTIVE:
		 abandoned, active, dead, exited, failed, listening, mounted, plugged, running, waiting

	STATE:
		 enabled, enabled-runtime, linked, linked-runtime, masked, masked-runtime, static, disabled, invalid

	PRESET:
		 enabled, disabled
```

## Installation

Optional dependency: [`priv_exec`](https://github.com/mirfatif/priv_exec). Put the binary on your `$PATH`.

```
~$ export PYTHONUSERBASE=/opt/python_user_base
~$ export PATH=$PYTHONUSERBASE/bin:$PATH

~$ sudo mkdir -p $PYTHONUSERBASE
~$ sudo chown $(id -u) $PYTHONUSERBASE

~$ sudo apt install python3-gi python3-dbus
~$ pip install --ignore-installed --upgrade pip
~$ pip install --upgrade "systemd_svc_status @ git+https://github.com/mirfatif/SystemdSvcStatus"

~$ sudo ln -s $PYTHONUSERBASE/lib/python3.*/site-packages/mirfatif/systemd_svc_status/etc/systemd-svc-watcher /etc/
~$ sudo ln -s $PYTHONUSERBASE/lib/python3.*/site-packages/mirfatif/systemd_svc_status/etc/systemd/user/systemd_svc_watcher.service /etc/systemd/user/
~$ sudo ln -s $PYTHONUSERBASE/lib/python3.*/site-packages/mirfatif/systemd_svc_status/etc/systemd/system/systemd_svc_watcher.service /etc/systemd/system/

~$ systemctl --user enable systemd_svc_watcher.service
~$ sudo systemctl enable systemd_svc_watcher.service

~$ systemctl --user start systemd_svc_watcher.service
~$ sudo systemctl start systemd_svc_watcher.service
```

## TODO

Replace legacy [dbus-python](https://dbus.freedesktop.org/doc/dbus-python/)
with [dbus-fast](https://github.com/bluetooth-devices/dbus-fast).
