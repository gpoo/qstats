#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# qstats, An assistant to review mail discussions
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import collections
import csv


def backup_file(filename):
    '''
       `filename` is saved a 'filename.yyy', where 'y' is an integer and
       following the format: '%s.%03d'.
       Returns True if it made a backup, and False otherwise.
    '''
    if os.path.isfile(filename):
        name, version = os.path.splitext(filename)

        try:
            num = int(version)
            base = name
        except ValueError:
            base = filename

        try:
            xrange
        except NameError:
            xrange = range

        # Find the next one
        for i in xrange(1000):
            new_file = '%s.%03d' % (base, i)
            if not os.path.isfile(new_file):
                os.rename(filename, new_file)
                return True

    return False


def load_threads_data_from_csv(filename):
    threads_data = collections.OrderedDict()

    if not os.path.isfile(filename):
        return threads_data

    try:
        with open(filename, 'r') as fd:
            reader = csv.DictReader(fd, quoting=csv.QUOTE_MINIMAL)
            for row in reader:
                key = row.pop('id', None)
                threads_data[key] = row
    except csv.Error as e:
        print('Error reading file: %s' % e)

    return threads_data
