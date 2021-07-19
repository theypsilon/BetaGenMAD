#!/usr/bin/env python3
# Copyright (c) 2021 José Manuel Barroso Galindo <theypsilon@gmail.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import subprocess
from pathlib import Path
import configparser
from inspect import currentframe, getframeinfo
import itertools
import os
import io
import hashlib
import distutils.util
import datetime
import difflib
import shutil
import time
import json
import xml.etree.cElementTree as ET
import urllib.request
from xml.dom import minidom

def main():

    print('START!')

    run_succesfully('git clone https://github.com/theypsilon/BetaDistrib.git')
    run_succesfully('git clone https://github.com/jotego/jtbin.git')

    mister_devel_mras = list(MraFinder('BetaDistrib/_Arcade').find_all_mras())
    jtbin_mras = list(MraFinder('jtbin/mra').find_all_mras())

    run_succesfully('rm -rf result || true')
    run_succesfully('mkdir -p result')
    mra_reader = MraReader('result')
    for mra in (mister_devel_mras + jtbin_mras):
        print(str(mra))
        mra_reader.translate_mra(mra)

    run_succesfully('git add result')
    run_succesfully('git commit -m "Result" || true')
    run_succesfully('git push origin main')

    print('Done.')

def translate_mame_rotation(rot):
    if rot == 'rot0':
        return 0
    elif  rot == 'rot90':
        return 90
    elif  rot == 'rot180':
        return 180
    elif  rot == 'rot270':
        return 270
    else:
        return None

def translate_mad_rotation(rot):
    if rot == 'horizontal':
        return 0
    elif  rot == 'vertical (cw)':
        return 90
    elif  rot == 'horizontal (180)':
        return 180
    elif  rot == 'vertical (ccw)':
        return 270
    else:
        return None

class MraFinder:
    def __init__(self, dir):
        self._dir = dir

    def find_all_mras(self):
        return sorted(self._scan(self._dir), key=lambda mad: mad.name.lower())

    def _scan(self, directory):
        for entry in os.scandir(directory):
            if entry.is_dir(follow_symlinks=False):
                yield from self._scan(entry.path)
            elif entry.name.lower().endswith(".mra"):
                yield Path(entry.path)

def read_mra_fields(mra_path, tags):
    fields = { i : '' for i in tags }

    try:
        context = ET.iterparse(str(mra_path), events=("start",))
        for event, elem in context:
            elem_tag = elem.tag.lower()
            if elem_tag in tags:
                tags.remove(elem_tag)
                elem_value = elem.text
                if isinstance(elem_value, str):
                    fields[elem_tag] = elem_value
                if len(tags) == 0:
                    break
    except Exception as e:
        print("Line %s || %s (%s)" % (lineno(), e, mra_path))

    return fields

def lineno():
    return getframeinfo(currentframe().f_back).lineno

class MraReader:
    def __init__(self, targetdir):
        self._targetdir = targetdir

    def translate_mra(self, mra):
        fields = read_mra_fields(mra, [
            'name',
            'setname',
            'rotation',
            'flip',
            'resolution',
            'region',
            'homebrew',
            'bootleg',
            'year',
            'category',
            'manufacturer'
        ])

        doc = ET.Element("misterarcadedescription")

        ET.SubElement(doc, "name").text = fields["name"]
        ET.SubElement(doc, "setname").text = fields["setname"]

        set_if_not_empty(doc, fields, 'name')
        set_if_not_empty(doc, fields, 'flip')
        set_if_not_empty(doc, fields, 'resolution')
        set_if_not_empty(doc, fields, 'region')
        set_if_not_empty(doc, fields, 'homebrew')
        set_if_not_empty(doc, fields, 'bootleg')
        set_if_not_empty(doc, fields, 'year')
        set_if_not_empty(doc, fields, 'category')
        set_if_not_empty(doc, fields, 'manufacturer')

        mra_path = str(mra.resolve())
        parts = mra_path.split('/')
        base = parts[0] + '/' + parts[1] + '/'
        target_path = self._targetdir + mra_path.replace(base, '').replace('.mra', '.mad')
        os.makedirs(str(Path(target_path).parent), exist_ok=True)

        print(target_path)

        xmlstr = minidom.parseString(ET.tostring(doc)).toprettyxml(indent="   ")
        with open(target_path, "w") as f:
            f.write(xmlstr)

def create_orphan_branch(branch):
    run_succesfully('git checkout -qf --orphan %s' % branch)
    run_succesfully('git rm -rf .')

def force_push_file(file_name, branch):
    run_succesfully('git add %s' % file_name)
    run_succesfully('git commit -m "BOT: Releasing new MAD database." > /dev/null 2>&1 || true')
    run_succesfully('git fetch origin %s > /dev/null 2>&1 || true' % branch)
    if not run_conditional('git diff --exit-code %s origin/%s' % (branch, branch)):
        print("There are changes to push.")
        print()

        run_succesfully('git push --force origin %s' % branch)
        print()
        print("New %s ready to be used." % file_name)
    else:
        print("Nothing to be updated.")

def set_if_not_empty(doc, fields, key):
    if fields[key] != '':
        ET.SubElement(doc, key).text = fields[key]

def save_data_to_compressed_json(db, json_name, zip_name):

    with open(json_name, 'w') as f:
        json.dump(db, f, sort_keys=True)

    run_succesfully('touch -a -m -t 202108231405 %s' % json_name)
    run_succesfully('zip -rq -D -X -9 -A --compression-method deflate %s %s' % (zip_name, json_name))

def hash(file):
    with open(file, "rb") as f:
        file_hash = hashlib.md5()
        chunk = f.read(8192)
        while chunk:
            file_hash.update(chunk)
            chunk = f.read(8192)
        return file_hash.hexdigest()

def run_conditional(command):
    result = subprocess.run(command, shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE)

    stdout = result.stdout.decode()
    if stdout.strip():
        print(stdout)
        
    return result.returncode == 0

def run_succesfully(command):
    result = subprocess.run(command, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    stdout = result.stdout.decode()
    stderr = result.stderr.decode()
    if stdout.strip():
        print(stdout)
    
    if stderr.strip():
        print(stderr)

    if result.returncode != 0:
        raise Exception("subprocess.run Return Code was '%d'" % result.returncode)

if __name__ == '__main__':
    main()