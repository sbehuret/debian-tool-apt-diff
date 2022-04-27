#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
import re
import shlex
from pprint import pprint

def cmdline_args():
    p = argparse.ArgumentParser(description='Compare or save APT packages')

    p.add_argument('action', choices=('compare', 'save'), nargs='?', default='compare', help='compare two APT snapshots or save APT snapshot')
    p.add_argument('target', nargs='?', default=os.getcwd(), help='target APT snapshot, defaults to current directory')
    p.add_argument('source', nargs='?', default=None, help='source APT snapshot, defaults to current system')
    p.add_argument('-s', '--summary', default=False, action='store_true', help="APT snapshot comparison summary")
    p.add_argument('-f', '--filter', default=False, action='store_true', help="filter APT snapshot comparison")
    p.add_argument('-r', '--reverse', default=False, action='store_true', help="reverse APT snapshot comparison")

    return(p.parse_args())

def _filter_apt_objdiff(apt_objdiff):
    if 'autos' not in apt_objdiff['_change']:
        return

    packages = set(apt_objdiff['_change']['autos']['_diff']['_delete'].keys())

    for package in packages:
        try:
            if package in apt_objdiff['_change']['manuals']['_diff']['_add']:
                del apt_objdiff['_change']['autos']['_diff']['_delete'][package]
                apt_objdiff['_change']['manuals']['_diff']['_add'][package] = 'Was Auto'
        except KeyError:
            pass

    packages = set(apt_objdiff['_change']['autos']['_diff']['_add'].keys())

    for package in packages:
        try:
            if package in apt_objdiff['_change']['manuals']['_diff']['_delete']:
                del apt_objdiff['_change']['autos']['_diff']['_add'][package]
                apt_objdiff['_change']['manuals']['_diff']['_delete'][package] = 'Now Auto'
        except KeyError:
            pass

def _filter_apt_snapshot(apt_snapshot):
    exclude_pattern = '^lib.+$'
    exclude_regex = re.compile(exclude_pattern)

    exclude_exception_pattern = '^(?:(?:lib.*(?:bin|tool|prog|script|exec|util|client|server|srv|plugin|ext|mod|core|base|extra|proto|conf|option|param|test)|libc(?:-|\d|$)|libnss-|libvirt-|libnetfilter-|libblockdev-).*|lib.*cli|libinput-pad-xtest|libapache2-mod-|libapache2-mpm-|libphp-jpgraph|libtiff-opengl)$'
    exclude_exception_regex = re.compile(exclude_exception_pattern)

    replace_pattern = '^(lib[^\d]*)(\d+(?:[\.-]\d+)*)([^\d]*)$'
    replace_regex = re.compile(replace_pattern)

    python_pattern = '^(python)(\d+(?:\.\d+)*|)(.*)$'
    python_regex = re.compile(python_pattern)

    snapshot_types = set(apt_snapshot.keys())

    for snapshot_type in snapshot_types:
        if snapshot_type in ('autos', 'selections', 'selversions', 'seldetails'):
            packages = set(apt_snapshot[snapshot_type].keys())

            for package in packages:
                if exclude_regex.match(package) and not exclude_exception_regex.match(package):
                    del apt_snapshot[snapshot_type][package]

        if snapshot_type in ('manuals', 'autos', 'selections', 'selversions', 'seldetails'):
            packages = set(apt_snapshot[snapshot_type].keys())

            for package in packages:
                replace_matches = replace_regex.match(package)

                if replace_matches:
                    if re.match('^\d+$', replace_matches.group(2)):
                        new_package = replace_regex.sub(r'\1X\3', package)
                    elif re.match('^\d+[\.-]\d+$', replace_matches.group(2)):
                        new_package = replace_regex.sub(r'\1X.X\3', package)
                    else:
                        new_package = replace_regex.sub(r'\1X.X.X\3', package)

                    apt_snapshot[snapshot_type][new_package] = apt_snapshot[snapshot_type][package]
                    del apt_snapshot[snapshot_type][package]

                    package = new_package

                python_matches = python_regex.match(package)

                if python_matches:
                    new_package = python_regex.sub(r'\1X\3', package)
                    apt_snapshot[snapshot_type][new_package] = apt_snapshot[snapshot_type][package]
                    del apt_snapshot[snapshot_type][package]

        if snapshot_type == 'selections':
            packages = set(apt_snapshot[snapshot_type].keys())

            for package in packages:
                if apt_snapshot[snapshot_type][package] == 'install':
                    del apt_snapshot[snapshot_type][package]

def _process_apt_output_advanced(output, separator, mainfield, maxfield=None, discard=None):
    new_output = {}

    for line in output.rstrip('\n').split('\n'):
        elements = re.sub(re.escape(separator) + '+', separator, line.strip(separator)).split(separator)
        key = elements[mainfield]
        discard = set(discard) if discard else set()
        discard.add(mainfield)
        new_output[key] = []

        for i,v in enumerate(elements):
            if i in discard:
                continue
            if maxfield is not None and i >= maxfield:
                continue

            new_output[key].append(v)

        count = len(new_output[key])

        if count == 0:
            new_output[key] = None
        elif count == 1:
            new_output[key] = new_output[key][0]
        elif count > 1:
            new_output[key] = set(new_output[key])

    return new_output

def _process_apt_output_simple(output):
    return {key: None for key in output.rstrip('\n').split('\n')}

def _process_apt_snapshot(apt_snapshot):
    apt_snapshot['selections'] = _process_apt_output_advanced(apt_snapshot['selections'], '\t', 0)
    apt_snapshot['seldetails'] = _process_apt_output_advanced(apt_snapshot['seldetails'], ' ', 1, maxfield=4)
    apt_snapshot['selversions'] = _process_apt_output_advanced(apt_snapshot['selversions'], '\t', 0)
    apt_snapshot['obsconffiles'] = _process_apt_output_advanced(apt_snapshot['obsconffiles'], ' ', 0, discard=(2,))
    apt_snapshot['autos'] = _process_apt_output_simple(apt_snapshot['autos'])
    apt_snapshot['manuals'] = _process_apt_output_simple(apt_snapshot['manuals'])
    apt_snapshot['holds'] = _process_apt_output_simple(apt_snapshot['holds'])

    return apt_snapshot

def get_apt_snapshot_from_system():
    apt_snapshot = {
        'selections': subprocess.run(('/bin/sh', '-c', 'dpkg --get-selections'), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'seldetails': subprocess.run(('/bin/sh', '-c', 'dpkg -l | grep -P \'^\w+ \''), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'selversions': subprocess.run(('/bin/sh', '-c', 'dpkg-query -W'), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'obsconffiles': subprocess.run(('/bin/sh', '-c', 'dpkg-query -W -f=\'${Conffiles}\n\' | grep -P \' obsolete$\''), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'autos': subprocess.run(('/bin/sh', '-c', 'apt-mark showauto'), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'manuals': subprocess.run(('/bin/sh', '-c', 'apt-mark showmanual'), stdout=subprocess.PIPE).stdout.decode('utf-8'),
        'holds': subprocess.run(('/bin/sh', '-c', 'apt-mark showhold'), stdout=subprocess.PIPE).stdout.decode('utf-8'),
    }

    _process_apt_snapshot(apt_snapshot)

    return apt_snapshot

def save_apt_snapshot_from_system(directory):
    subprocess.run(('/bin/sh', '-c', 'mkdir -p ' + shlex.quote(directory)))

    with open(directory + os.path.sep + 'selections', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'dpkg --get-selections'), stdout=file)

    with open(directory + os.path.sep + 'seldetails', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'dpkg -l | grep -P \'^\w+ \''), stdout=file)

    with open(directory + os.path.sep + 'selversions', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'dpkg-query -W'), stdout=file)

    with open(directory + os.path.sep + 'obsconffiles', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'dpkg-query -W -f=\'${Conffiles}\n\' | grep -P \' obsolete$\''), stdout=file)

    with open(directory + os.path.sep + 'autos', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'apt-mark showauto'), stdout=file)

    with open(directory + os.path.sep + 'manuals', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'apt-mark showmanual'), stdout=file)

    with open(directory + os.path.sep + 'holds', 'w') as file:
        subprocess.run(('/bin/sh', '-c', 'apt-mark showhold'), stdout=file)

def load_apt_snapshot(directory):
    apt_snapshot = {}

    with open(directory + os.path.sep + 'selections', 'r') as file:
        apt_snapshot['selections'] = file.read()

    with open(directory + os.path.sep + 'seldetails', 'r') as file:
        apt_snapshot['seldetails'] = file.read()

    with open(directory + os.path.sep + 'selversions', 'r') as file:
        apt_snapshot['selversions'] = file.read()

    with open(directory + os.path.sep + 'obsconffiles', 'r') as file:
        apt_snapshot['obsconffiles'] = file.read()

    with open(directory + os.path.sep + 'autos', 'r') as file:
        apt_snapshot['autos'] = file.read()

    with open(directory + os.path.sep + 'manuals', 'r') as file:
        apt_snapshot['manuals'] = file.read()

    with open(directory + os.path.sep + 'holds', 'r') as file:
        apt_snapshot['holds'] = file.read()

    _process_apt_snapshot(apt_snapshot)

    return apt_snapshot

def build_object_differential(from_objdict, to_objdict):
    if type(from_objdict) is not dict:
        raise TypeError('Expected dict for from_objdict')

    if type(to_objdict) is not dict:
        raise TypeError('Expected dict for to_objdict')

    objdiff = {
        '_add': {},
        '_delete': {},
        '_change': {}
    }

    for key in to_objdict:
        if key not in from_objdict:
            objdiff['_add'][key] = to_objdict[key]
        elif from_objdict[key] != to_objdict[key]: # safe_value_differs is ineffective against NaNs embedded in dict
            if type(from_objdict[key]) is dict and type(to_objdict[key]) is dict:
                objdiff['_change'][key] = {
                   '_diff': build_object_differential(from_objdict[key], to_objdict[key])
                }
            else:
                objdiff['_change'][key] = {
                    '_from': from_objdict[key],
                    '_to': to_objdict[key]
                }

    for key in from_objdict:
        if key not in to_objdict:
            objdiff['_delete'][key] = from_objdict[key]

    return objdiff

if __name__ == '__main__':
    if sys.version_info<(3,5,0):
        sys.stderr.write('You need python 3.5 or later to run this script\n')
        sys.exit(1)

    try:
        args = cmdline_args()
    except Exception as e:
        sys.stderr.write('Error while parsing argumens: %s\n' % str(e))
        sys.exit(1)

    action = args.action
    summary = args.summary
    filter = args.filter
    reverse = args.reverse
    source = args.source.rstrip(os.path.sep) if args.source is not None else None
    target = args.target.rstrip(os.path.sep)

    print('Action: %s' % action)

    if action == 'compare':
        if source is None:
            target, source = source, target

        if source is None:
            print('Source is set to current APT packages')
        else:
            print('Source: %s' % source)

        if target is None:
            print('Target is set to current APT packages')
        else:
            print('Target: %s' % target)

        print('Summary: %s' % summary)

        print('Filter: %s' % summary)

        print('Reverse: %s' % reverse)

        if source:
            source_snapshot = load_apt_snapshot(source)
        else:
            source_snapshot = get_apt_snapshot_from_system()

        if target:         
            target_snapshot = load_apt_snapshot(target)
        else:
            target_snapshot = get_apt_snapshot_from_system()

        if reverse:
            target_snapshot, source_snapshot = source_snapshot, target_snapshot

        if filter:
            _filter_apt_snapshot(source_snapshot)
            _filter_apt_snapshot(target_snapshot)

        if summary:
            del source_snapshot['seldetails']
            del source_snapshot['selversions']
            del target_snapshot['seldetails']
            del target_snapshot['selversions']

        print('Differential:')

        objdiff = build_object_differential(source_snapshot, target_snapshot)

        if filter:
            _filter_apt_objdiff(objdiff)

        pprint(objdiff)

    if action == 'save':
        print('Target: %s' % target)

        save_apt_snapshot_from_system(target)
