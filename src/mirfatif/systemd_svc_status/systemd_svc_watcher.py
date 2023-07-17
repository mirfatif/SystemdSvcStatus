#!/usr/bin/python

import builtins
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
from mirfatif.sys_desk_notifd import notify_deskd

SYS_D_SVC = 'org.freedesktop.systemd1'
SYS_D_MGR_IFACE = SYS_D_SVC + '.Manager'
SYS_D_PATH = '/org/freedesktop/systemd1'
# https://www.freedesktop.org/software/systemd/man/org.freedesktop.systemd1.html#Signals
SIG_JOB_REMOVED = 'JobRemoved'

DBUS_SVC = 'org.freedesktop.DBus'

# https://github.com/mineo/sagbescheid/blob/0.3.0/sagbescheid/unit.py#L17
SVC_PATH_REPLACEMENTS = {
    '_': '_5f',
    '-': '_2d',
    '.': '_2e',
    '/': '_2f',
    ':': '_3a',
    '@': '_40',
    '\\': '_5c'
}

BLACK_LIST_FILE: str = '/etc/systemd-svc-watcher/ignore.list'


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

    state = bus.call_blocking(
        bus_name=SYS_D_SVC,
        object_path=SYS_D_PATH + '/unit/' + unit,
        dbus_interface=DBUS_SVC + '.Properties',
        method='Get',
        signature='ss',
        args=(SYS_D_SVC + '.Unit', 'ActiveState')
    )

    sub_state = bus.call_blocking(
        bus_name=SYS_D_SVC,
        object_path=SYS_D_PATH + '/unit/' + unit,
        dbus_interface=DBUS_SVC + '.Properties',
        method='Get',
        signature='ss',
        args=(SYS_D_SVC + '.Unit', 'SubState')
    )

    unit = args[2]
    msg: str = f'{unit} becomes {state}'

    if state != sub_state:
        msg += f' ({sub_state})'

    if state == 'active' or (
            state == 'inactive' and (
            unit in black_list or (black_list_regex and black_list_regex.match(unit)))):
        print('Ignoring:', msg)
        return

    print(msg)

    if not (nid := notif_ids.get(unit)):
        nid = str(os.getpid()) + '|' + unit
        notif_ids[unit] = nid

    notify_deskd.notify_proxy(
        replace_old=nid,
        app_icon='text-x-systemd-unit',
        summary='Service state changed',
        body=f'{msg}',
        timeout=0,
        sys_bus=system_bus
    )


def kill_me(sig: int = None, *_):
    if sys.stdout.isatty():
        print(f'\r')

    if sig:
        print(f'{signal.strsignal(sig)}, exiting...')
    else:
        print('Exiting...')

    if bus:
        bus.close()

    if system_bus and system_bus != bus:
        system_bus.close()

    if loop:
        loop.quit()


def load_config():
    if os.path.exists(BLACK_LIST_FILE):
        try:
            with open(BLACK_LIST_FILE) as file:
                black_list.clear()
                global black_list_regex
                black_list_re: list[str] = []

                for line in file.read().split('\n'):
                    line = line.strip()

                    if line.startswith('#'):
                        continue

                    if line.startswith('REGEX|'):
                        black_list_re.append(line.removeprefix('REGEX|'))
                    else:
                        black_list.append(line)

                if black_list_re:
                    black_list_regex = re.compile('|'.join(black_list_re))

                print(f'Loaded {len(black_list)} (strings) + '
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
    try:
        signal_receivers = bus.call_blocking(
            bus_name=DBUS_SVC,
            object_path='/org/freedesktop/DBus',
            dbus_interface=DBUS_SVC + '.Debug.Stats',
            method='GetAllMatchRules',
            signature=None,
            args=()
        )
    finally:
        bus.close()

    for i in signal_receivers.items():
        val: dbus.Array = i[1]
        for match in val:
            if match.__contains__(f"'{SYS_D_MGR_IFACE}'") \
                    and match.__contains__(f"'{SYS_D_PATH}'") \
                    and match.__contains__(f"'{SIG_JOB_REMOVED}'"):
                print(match)


def main():
    user_bus: bool = len(sys.argv) > 1 and sys.argv[1:].__contains__('--user')

    DBusGMainLoop(set_as_default=True)

    global bus, system_bus, loop, print
    bus = dbus.SessionBus() if user_bus else dbus.SystemBus()

    check_sig_exported = '--check-signal-exported'

    if len(sys.argv) > 1 and sys.argv[1:].__contains__(check_sig_exported):
        check_signal_exported()
        sys.exit()

    load_config()

    system_bus = dbus.SystemBus() if user_bus else bus

    sys.excepthook = handle_uncaught_exc
    set_signal_handlers()

    if not user_bus and os.geteuid() != 0:
        priv_exec = 'priv_exec -k -u 0 --'
    else:
        priv_exec = ''

    sig_receivers_cmd: list[str] | None = None

    if sys.stdin.isatty() or os.geteuid() == 0:
        sig_receivers_cmd = f'{priv_exec} python3 {" ".join(sys.argv)} {check_sig_exported}'.split()
        print('\nBEFORE:')
        subprocess.call(sig_receivers_cmd)
        print('\nAdding signal receivers...\n')

    bus.call_blocking(
        SYS_D_SVC,
        SYS_D_PATH,
        SYS_D_MGR_IFACE,
        'Subscribe',
        None,
        ()
    )

    bus.add_signal_receiver(
        handle_dbus_signal,
        SIG_JOB_REMOVED,
        SYS_D_MGR_IFACE,
        SYS_D_SVC,
        SYS_D_PATH
    )

    if sig_receivers_cmd:
        print('AFTER:')
        subprocess.call(sig_receivers_cmd)
        print()

    if sys.stdin.isatty():
        print = print
    else:
        print = functools.partial(print, flush=True)

    print('Listening...')

    loop = GLib.MainLoop()
    loop.run()


bus: dbus.SystemBus | dbus.SessionBus | None = None
system_bus: dbus.SystemBus | None = None
loop: GLib.MainLoop | None = None

black_list_regex: Pattern[str] | None = None
black_list: list[str] = []
notif_ids: dict[str, str] = {}

print = builtins.print

if __name__ == "__main__":
    main()
