#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# qstats, An assistant to review mail discussions
#
# Copyright (C) 2015-2016 Germán Poo-Caamaño <gpoo@gnome.org>
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

from __future__ import print_function

import re
import collections

import utils


class Network:
    def __init__(self, threads, csv_file, *args):
        self.threads = threads
        self.ithread = collections.OrderedDict()  # Internal dict of threads
        self.csv_file = csv_file
        self.content_type = {}
        self.in_progress = False  # State for variable initialization
        self.is_modified = False  # State that requires saving the data

        self.ithread = utils.load_threads_data_from_csv(self.csv_file)
        self.load_thread_containers(threads)

    def load_thread_containers(self, data):
        L = list(data.items())
        L.sort()
        regex = re.compile(r'\s+')
        for index, (subject, container) in enumerate(L, 1):
            subject = regex.sub(' ', subject).strip()

            # Metadata per thread
            ctn = container.message
            msgid = 'None' if not ctn else ctn.message_id
            cid = '{}-{}'.format(msgid, subject)

            if cid in self.ithread:
                self.ithread[cid]['container'] = container
            else:
                print('%s does not exists' % cid)

    def main(self):
        for cid, data in self.ithread.iteritems():
            if data['generic'] == 'True' and data['category'] != 'Other':
                print(data['container'])
