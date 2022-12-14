#!/usr/bin/python
import functools
import os
import re
import signal
import subprocess
import sys
import traceback
from re import Pattern

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from mirfatif.dbus_notify import dbus_notify

SYS_D_SVC = 'org.freedesktop.systemd1'
SYS_D_MGR_IFACE = SYS_D_SVC + '.Manager'
SYS_D_PATH = '/org/freedesktop/systemd1'
# https://www.freedesktop.org/software/systemd/man/org.freedesktop.systemd1.html#Signals
SIG_JOB_REMOVED = 'JobRemoved'

DBUS_SVC = 'org.freedesktop.DBus'

APP_ICON = 'app_icon'
SUMMARY = 'summary'
BODY = 'body'
TIMEOUT = 'timeout'

CHECK_SIGNAL_EXPORTED = '--check-signal-exported'

NOTIF_IDS: dict[str, str] = {}

# https://github.com/mineo/sagbescheid/blob/0.3.0/sagbescheid/unit.py#L17
SVC_PATH_REPLACEMENTS = {
    '-': '_2d',
    '.': '_2e',
    '/': '_2f',
    ':': '_3a',
    '@': '_40',
    '\\': '_5c'
}

BLACK_LIST_FILE: str = '/etc/sys-svc-watcher/ignore.list'
BLACK_LIST: list[str] = []
BLACK_LIST_REGEX: Pattern[str] | None = None

system_bus: dbus.SystemBus
loop: GLib.MainLoop

if sys.stdin.isatty():
    print = print
else:
    print = functools.partial(print, flush=True)


def print_err(msg: str):
    print(msg, file=sys.stderr)


def print_exc_line():
    etype, value, tb = sys.exc_info()
    print(''.join(traceback.format_exception_only(etype, value)), file=sys.stderr, end='')


def handle_dbus_signal(*args) -> None:
    if not args:
        print_err('Empty signal received')
        return

    if len(args) != 4 or \
            not isinstance(args[1], dbus.ObjectPath) or \
            not isinstance(args[2], dbus.String):
        print_err(f'Bad signal: {args}')
        return

    unit: str = args[2]

    for frm, to in SVC_PATH_REPLACEMENTS.items():
        unit = unit.replace(frm, to)

    state = system_bus.call_blocking(
        bus_name=SYS_D_SVC,
        object_path=SYS_D_PATH + '/unit/' + unit,
        dbus_interface=DBUS_SVC + '.Properties',
        method='Get',
        signature='ss',
        args=(SYS_D_SVC + '.Unit', 'ActiveState')
    )

    unit = args[2]
    msg: str = f'{unit} becomes {state}'

    if state == 'active' or (
            state == 'inactive' and (
            unit in BLACK_LIST or (BLACK_LIST_REGEX and BLACK_LIST_REGEX.match(unit)))):
        print('Ignoring:', msg)
        return

    print(msg)

    if not (nid := NOTIF_IDS.get(unit)):
        nid = str(os.getpid()) + '|' + unit
        NOTIF_IDS[unit] = nid

    dbus_notify.notify(
        replace_old=nid,
        app_icon='text-x-systemd-unit',
        summary='Service state changed',
        body=f'{msg}',
        timeout=0,
        bus=system_bus
    )


def kill_me(sig: int = None, *_):
    if sys.stdout.isatty():
        print(f'\r')

    if sig:
        print(f'{signal.strsignal(sig)}, exiting...')
    else:
        print('Exiting...')

    system_bus.close()

    if loop:
        loop.quit()


def load_config():
    if os.path.exists(BLACK_LIST_FILE):
        try:
            with open(BLACK_LIST_FILE) as file:
                BLACK_LIST.clear()
                global BLACK_LIST_REGEX
                black_list_re: list[str] = []

                for line in file.read().split('\n'):
                    line = line.strip()

                    if line.startswith('#'):
                        continue

                    if line.startswith('REGEX|'):
                        black_list_re.append(line.removeprefix('REGEX|'))
                    else:
                        BLACK_LIST.append(line)

                if black_list_re:
                    BLACK_LIST_REGEX = re.compile('|'.join(black_list_re))

                print(f'Loaded {len(BLACK_LIST)} (strings) + '
                      f'{len(black_list_re)} (regex) services from {BLACK_LIST_FILE}')

        except (PermissionError, FileNotFoundError):
            print_exc_line()


def set_signal_handlers():
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
        signal.signal(sig, kill_me)

    signal.signal(signal.SIGCHLD, lambda *_: os.wait())

    if not sys.stdin.isatty():
        signal.signal(signal.SIGUSR1, lambda *_: load_config())


def handle_uncaught_exc(err_type, value, tb):
    print_err(f'Uncaught exception:')
    traceback.print_exception(err_type, value, tb)
    kill_me()


def check_signal_exported():
    sys_bus: dbus.SystemBus = dbus.SystemBus()
    try:
        signal_receivers = sys_bus.call_blocking(
            bus_name=DBUS_SVC,
            object_path='/org/freedesktop/DBus',
            dbus_interface=DBUS_SVC + '.Debug.Stats',
            method='GetAllMatchRules',
            signature=None,
            args=()
        )
    finally:
        sys_bus.close()

    for i in signal_receivers.items():
        val: dbus.Array = i[1]
        for match in val:
            if match.__contains__(f"'{SYS_D_MGR_IFACE}'") \
                    and match.__contains__(f"'{SYS_D_PATH}'") \
                    and match.__contains__(f"'{SIG_JOB_REMOVED}'"):
                print(match)


def start():
    if len(sys.argv) > 1 and sys.argv[1] == CHECK_SIGNAL_EXPORTED:
        check_signal_exported()
        sys.exit()

    load_config()

    DBusGMainLoop(set_as_default=True)

    global system_bus
    system_bus = dbus.SystemBus()

    sys.excepthook = handle_uncaught_exc
    set_signal_handlers()

    if os.getuid() != 0:
        priv_exec = 'priv_exec -u 0 --'
    else:
        priv_exec = ''

    show_sig_receivers: bool = sys.stdin.isatty() or os.getuid() == 0

    if show_sig_receivers:
        print('\nBEFORE:')
        subprocess.call(f'{priv_exec} {sys.argv[0]} {CHECK_SIGNAL_EXPORTED}'.split())
        print('\nAdding signal receivers...\n')

    system_bus.call_blocking(
        SYS_D_SVC,
        SYS_D_PATH,
        SYS_D_MGR_IFACE,
        'Subscribe',
        None,
        ()
    )

    system_bus.add_signal_receiver(
        handle_dbus_signal,
        SIG_JOB_REMOVED,
        SYS_D_MGR_IFACE,
        SYS_D_SVC,
        SYS_D_PATH
    )

    if show_sig_receivers:
        print('AFTER:')
        subprocess.call(f'{priv_exec} {sys.argv[0]} {CHECK_SIGNAL_EXPORTED}'.split())
        print()


start()

print('Listening...')
sys.stdout.flush()
loop = GLib.MainLoop()
loop.run()
