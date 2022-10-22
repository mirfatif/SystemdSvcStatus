#!/usr/bin/python

import os
import signal
import subprocess
import sys
import traceback

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

INTERFACE = 'com.mirfatif.SysDeskNotifD'
SIGNAL = 'Notify'

APP_NAME = 'app_name'
REPLACE_ID = 'replace_id'
REPLACE_OLD = 'replace_old'
APP_ICON = 'app_icon'
SUMMARY = 'summary'
BODY = 'body'
TIMEOUT = 'timeout'

# https://specifications.freedesktop.org/notification-spec/notification-spec-latest.html
# https://docs.xfce.org/apps/xfce4-notifyd/spec
# App name, notif id to replace, app icon, summary, body, actions list, hints dict, timeout
NOTIF_SIGN = 'susssasa{sv}i'

CHECK_SIGNAL_EXPORTED = '--check-signal-exported'

system_bus: dbus.SystemBus
user_bus: dbus.SessionBus
loop: GLib.MainLoop


def print_err(msg: str):
    print(msg, file=sys.stderr)


def get_notif_str(d: dict, key: str) -> str:
    if (s := d.get(key)) and isinstance(s, str):
        return s

    if s:
        print_err(f'Bad {key}: {s} ({type(s)})')

    return ''


def get_notif_int(d: dict, key: str, default: int, multiplier: int = 1) -> int:
    if (i := d.get(key)) is not None and isinstance(i, int) and (i := int(i)) >= 0:
        return i * multiplier

    if i := d.get(key):
        print_err(f'Bad {key}: {i} ({type(i)})')

    return default


NOTIF_IDS: dict[str, int] = {}


def handle_dbus_signal(*args):
    if not args:
        return

    if not len(args) == 1 or not isinstance((req := args[0]), dbus.Dictionary):
        print_err(f'Bad request: {type(args)}')
        print(args, file=sys.stderr)
        return

    app_name: str = get_notif_str(req, APP_NAME)
    replace_id: int = get_notif_int(req, REPLACE_ID, 0)
    replace_old: str = get_notif_str(req, REPLACE_OLD)
    app_icon: str = get_notif_str(req, APP_ICON)
    summary: str = get_notif_str(req, SUMMARY)
    body: str = get_notif_str(req, BODY)
    timeout: int = get_notif_int(req, TIMEOUT, -1, 1000)

    if not replace_id and replace_old:
        if nid := NOTIF_IDS.get(replace_old):
            replace_id = nid

    # Returns new notif id
    nid = user_bus.call_blocking(
        'org.freedesktop.Notifications',
        '/org/freedesktop/Notifications',
        'org.freedesktop.Notifications',
        'Notify',
        NOTIF_SIGN,
        (app_name, replace_id, app_icon, summary, body, [], [], timeout)
    )

    if replace_old and nid:
        NOTIF_IDS[replace_old] = nid


def kill_me(sig: int = None, *_):
    if sys.stdout.isatty():
        print(f'\r')

    if sig:
        print(f'{signal.strsignal(sig)}, exiting...')
    else:
        print('Exiting...')

    system_bus.close()
    user_bus.close()

    if loop:
        loop.quit()


def set_signal_handlers():
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        signal.signal(sig, kill_me)
    signal.signal(signal.SIGCHLD, lambda *_: os.wait())


def handle_uncaught_exc(err_type, value, tb):
    print_err(f'Uncaught exception:')
    traceback.print_exception(err_type, value, tb)
    kill_me()


def check_signal_exported():
    sys_bus: dbus.SystemBus = dbus.SystemBus()
    try:
        signal_receivers = sys_bus.call_blocking(
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus.Debug.Stats',
            'GetAllMatchRules',
            None,
            ()
        )
    finally:
        sys_bus.close()

    for i in signal_receivers.items():
        val: dbus.Array = i[1]
        for match in val:
            if match.__contains__(INTERFACE):
                # print(f'Key: {i[0]}, Sig: {val.signature}, Count: {len(val)}')
                assert len(val) == 1
                print(match)


def start():
    if len(sys.argv) > 1 and sys.argv[1] == CHECK_SIGNAL_EXPORTED:
        check_signal_exported()
        sys.exit()

    DBusGMainLoop(set_as_default=True)

    global system_bus, user_bus

    system_bus = dbus.SystemBus()
    user_bus = dbus.SessionBus()

    sys.excepthook = handle_uncaught_exc
    set_signal_handlers()

    system_bus.add_signal_receiver(handle_dbus_signal, SIGNAL, INTERFACE)

    if sys.stdin.isatty() or os.getuid() == 0:
        if os.getuid() != 0:
            priv_exec = 'priv_exec -u 0 --'
        else:
            priv_exec = ''
        subprocess.call(f'{priv_exec} {sys.argv[0]} {CHECK_SIGNAL_EXPORTED}'.split())


start()

print('Listening...')
sys.stdout.flush()
loop = GLib.MainLoop()
loop.run()
