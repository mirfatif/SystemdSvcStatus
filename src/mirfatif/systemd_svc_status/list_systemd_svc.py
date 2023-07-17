#!/usr/bin/python

import collections
import getopt
import os
import sys
import traceback

import dbus

SYS_D_SVC = 'org.freedesktop.systemd1'
SYS_D_MGR_IFACE = SYS_D_SVC + '.Manager'
SYS_D_PATH = '/org/freedesktop/systemd1'

DBUS_SVC = 'org.freedesktop.DBus'

COLS = os.get_terminal_size().columns if sys.stdout.isatty() else 1000

SPACE = 5
STATE_WID = 10
NAME_WID = COLS - (STATE_WID + SPACE) * 5

SORT_LOADED = 'loaded'
SORT_ACTIVE = 'active'
SORT_SUB_ACTIVE = 'sub-active'
SORT_FILE_STATE = 'file-state'
SORT_FILE_PRESET = 'file-preset'

ARG_HELP = 'help'
ARG_USER = 'user'
ARG_DESC_FILE = 'desc-file'
ARG_SORT_BY = 'sort-by'
ARG_TYPE = 'type'
ARG_LOADED = 'loaded'
ARG_ACTIVE = 'active'
ARG_SUB_ACTIVE = 'sub-active'
ARG_FILE_STATE = 'file-state'
ARG_FILE_PRESET = 'file-preset'

# https://www.freedesktop.org/software/systemd/man/org.freedesktop.systemd1.html
Unit = collections.namedtuple(
    'Unit',
    ['name', 'desc', 'loaded', 'active', 'sub_active', 'file', 'file_state', 'file_preset']
)


def trunc_str(string: str, length: int):
    return (string[:length - 3] + '...') if len(string) > length else string


def print_bold(text: str, **kwargs):
    print(f'\033[1m{text}\033[0m', **kwargs)


def get_sort_key(u: Unit, opt_sort_key: str):
    if opt_sort_key == SORT_LOADED:
        sort = u.loaded
    elif opt_sort_key == SORT_ACTIVE:
        sort = u.active
    elif opt_sort_key == SORT_SUB_ACTIVE:
        sort = u.sub_active
    elif opt_sort_key == SORT_FILE_STATE:
        sort = u.file_state
    elif opt_sort_key == SORT_FILE_PRESET:
        sort = u.file_preset
    else:
        sort = u.name

    if sort:
        sort = sort.lower()

    return sort


def print_usage(ex_code: int = None):
    print(f'\nUsage:\n\t{os.path.basename(sys.argv[0])} [OPTIONS]')
    print(f'\nOptions:')
    print(f'\t-h|--{ARG_HELP}                  Show help')
    print(f'\t--{ARG_USER}                     Show session services')
    print(f'\t--{ARG_DESC_FILE}                Show service description and file')
    print(f'\t--{ARG_SORT_BY}=<SORT_KEY>       Sort column')
    print(f'\t--{ARG_TYPE}=<TYPE>              Types')
    print(f'\t--{ARG_LOADED}=<LOADED>          Loaded states')
    print(f'\t--{ARG_ACTIVE}=<ACTIVE>          Active states')
    print(f'\t--{ARG_SUB_ACTIVE}=<SUB_ACTIVE>  Sub-active states')
    print(f'\t--{ARG_FILE_STATE}=<STATE>       File states')
    print(f'\t--{ARG_FILE_PRESET}=<PRESET>     File presets')

    def print_keys(f_name: str, f_value: str):
        print(f'\n\t{f_name}:\n\t\t {f_value}')

    print_keys('SORT_KEY', f'{SORT_LOADED}, {SORT_ACTIVE}, {SORT_SUB_ACTIVE}, {SORT_FILE_STATE}, {SORT_FILE_PRESET}')

    print('\n\tAll filters are comma-separated lists.\n')

    print_keys('TYPE', 'all, automount, device, mount, path, scope, service, slice, socket, target, timer')
    print_keys('LOADED', 'loaded, not-found')
    print_keys('ACTIVE', 'active, inactive, failed')
    print_keys('SUB_ACTIVE',
               'abandoned, active, dead, exited, failed, listening, mounted, plugged, running, waiting')
    print_keys('STATE',
               'enabled, enabled-runtime, linked, linked-runtime, '
               'masked, masked-runtime, static, disabled, invalid')
    print_keys('PRESET', 'enabled, disabled')

    print()

    if ex_code is not None:
        sys.exit(ex_code)


def main():
    opt_show_user = False
    opt_show_desc_file = False
    opt_sort_key: str | None = None
    opt_types: list[str] | None = None
    opt_loaded_states: list[str] | None = None
    opt_active_states: list[str] | None = None
    opt_sub_active_states: list[str] | None = None
    opt_file_states: list[str] | None = None
    opt_file_presets: list[str] | None = None

    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            'h',
            [
                ARG_HELP,
                ARG_USER,
                ARG_DESC_FILE,
                f'{ARG_SORT_BY}=',
                f'{ARG_TYPE}=',
                f'{ARG_LOADED}=',
                f'{ARG_ACTIVE}=',
                f'{ARG_SUB_ACTIVE}=',
                f'{ARG_FILE_STATE}=',
                f'{ARG_FILE_PRESET}='
            ]
        )
    except getopt.GetoptError:
        etype, value, tb = sys.exc_info()
        print(''.join(traceback.format_exception_only(etype, value)), file=sys.stderr, end='')
        print_usage()
        sys.exit(1)

    if args:
        print(f'Unexpected arguments: {" ".join(args)}', file=sys.stderr)
        print_usage(1)

    for opt, val in opts:
        if opt == f'--{ARG_HELP}' or opt == '-h':
            print_usage(0)
        elif opt == f'--{ARG_USER}':
            opt_show_user = True
        elif opt == f'--{ARG_DESC_FILE}':
            opt_show_desc_file = True
        elif opt == f'--{ARG_SORT_BY}':
            opt_sort_key = val
        elif opt == f'--{ARG_TYPE}':
            opt_types = val.split(',')
        elif opt == f'--{ARG_LOADED}':
            opt_loaded_states = val.split(',')
        elif opt == f'--{ARG_ACTIVE}':
            opt_active_states = val.split(',')
        elif opt == f'--{ARG_SUB_ACTIVE}':
            opt_sub_active_states = val.split(',')
        elif opt == f'--{ARG_FILE_STATE}':
            opt_file_states = val.split(',')
        elif opt == f'--{ARG_FILE_PRESET}':
            opt_file_presets = val.split(',')

    bus = dbus.SessionBus() if opt_show_user else dbus.SystemBus()

    units = bus.call_blocking(
        bus_name=SYS_D_SVC,
        object_path=SYS_D_PATH,
        dbus_interface=SYS_D_MGR_IFACE,
        method='ListUnits',
        signature=None,
        args=()
    )

    units_map: dict[str, list[Unit]] = {}
    type_count: dict[str, int] = {}
    loaded_count: dict[str, dict[str, int]] = {}
    active_count: dict[str, dict[str, int]] = {}
    sub_active_count: dict[str, dict[str, int]] = {}
    file_state_count: dict[str, dict[str, int]] = {}
    file_preset_count: dict[str, dict[str, int]] = {}
    name_max_len = 0
    name_wid = NAME_WID

    dicts: list[dict[str, dict[str, int]]] = [
        loaded_count,
        active_count,
        sub_active_count,
        file_state_count,
        file_preset_count
    ]

    headers: list[str] = ['Loaded', 'Active', 'SubActive', 'FileState', 'FilePreset']

    def print_row(u: Unit):
        print(f'{u.name:<{name_wid + SPACE}}'
              f'{u.loaded:<{STATE_WID + SPACE}}'
              f'{u.active:<{STATE_WID + SPACE}}'
              f'{u.sub_active:<{STATE_WID + SPACE}}'
              f'{u.file_state:<{STATE_WID + SPACE}}'
              f'{u.file_preset:<{STATE_WID}}')

    def print_header():
        print_row(Unit('Name', '', headers[0], headers[1], headers[2], '', headers[3], headers[4]))

    for name, desc, loaded, active, sub_active, _, path, _, _, _ in units:
        unit_type = name.split('.')[-1]

        count = (type_count.get(unit_type) or 0) + 1
        type_count[unit_type] = count

        if opt_types:
            if 'all' not in opt_types and unit_type not in opt_types:
                continue
        elif unit_type != 'service':
            continue

        if opt_loaded_states and loaded not in opt_loaded_states:
            continue

        if opt_active_states and active not in opt_active_states:
            continue

        if opt_sub_active_states and sub_active not in opt_sub_active_states:
            continue

        file_state = bus.call_blocking(
            bus_name=SYS_D_SVC,
            object_path=path,
            dbus_interface=DBUS_SVC + '.Properties',
            method='Get',
            signature='ss',
            args=(SYS_D_SVC + '.Unit', 'UnitFileState')
        )

        if opt_file_states and file_state not in opt_file_states:
            continue

        file_preset = bus.call_blocking(
            bus_name=SYS_D_SVC,
            object_path=path,
            dbus_interface=DBUS_SVC + '.Properties',
            method='Get',
            signature='ss',
            args=(SYS_D_SVC + '.Unit', 'UnitFilePreset')
        )

        if opt_file_presets and file_preset not in opt_file_presets:
            continue

        if file_state:
            file_state = file_state.replace('-runtime', '-rt')

        file = None if not opt_show_desc_file else bus.call_blocking(
            bus_name=SYS_D_SVC,
            object_path=path,
            dbus_interface=DBUS_SVC + '.Properties',
            method='Get',
            signature='ss',
            args=(SYS_D_SVC + '.Unit', 'FragmentPath')
        )

        name = trunc_str(name.replace('\\x2d', '-'), name_wid)
        unit = Unit(name, desc, loaded, active, sub_active, file, file_state, file_preset)

        if not (lst := units_map.get(unit_type)):
            lst = [unit]
        else:
            lst.append(unit)

        units_map[unit_type] = lst

        for d, k in [
            (loaded_count, loaded),
            (active_count, active),
            (sub_active_count, sub_active),
            (file_preset_count, file_preset),
            (file_state_count, file_state)
        ]:
            if k:
                count = d.get(unit_type) or {}
                count[k] = (count.get(k) or 0) + 1
                d[unit_type] = count

        name_max_len = max(name_max_len, len(name))

    name_wid = min(name_wid, name_max_len)
    total_wid = name_wid + (STATE_WID + SPACE) * 5

    for key in sorted(units_map.keys()):
        print_bold(f'{key.upper()}S: ', end='', file=sys.stderr)
        print(f'{len(units_map[key])}', end='', file=sys.stderr)
        if len(units_map[key]) != type_count[key]:
            print(f' / {type_count[key]}', end='', file=sys.stderr)
        print(file=sys.stderr)

        print(''.join(['-' for _ in range(total_wid)]), file=sys.stderr)
        for i in range(0, len(headers), 1):
            t, d = headers[i], dicts[i]
            if count := d.get(key):
                print(t + ':', ', '.join([f'{n}: {c}' for n, c in count.items()]), file=sys.stderr)
        print(''.join(['=' for _ in range(total_wid)]), file=sys.stderr)

        print_header()
        print(''.join(['-' for _ in range(total_wid)]), file=sys.stderr)

        for unit in sorted(units_map[key], key=lambda u: get_sort_key(u, opt_sort_key)):
            print_row(unit)

            if opt_show_desc_file:
                if unit.desc:
                    print_bold('Desc: ', end='')
                    print(unit.desc)
                if unit.file:
                    print_bold('File: ', end='')
                    print(unit.file)
                if unit.desc or unit.file:
                    print()

        print(file=sys.stderr)


if __name__ == '__main__':
    main()
