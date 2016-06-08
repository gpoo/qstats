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
from .filter import ThreadIterator, parse_message, apply_aliases


class Network:
    def __init__(self, threads, csv_file, aliases, *args):
        self.threads = threads
        self.ithread = collections.OrderedDict()  # Internal dict of threads
        self.csv_file = csv_file
        self.aliases = aliases

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
            if data['generic'] != 'True' or data['category'] != 'Other':
                continue
            self.do_process_thread(data['container'])

    def do_process_thread(self, container):
        offset = 0
        sender = []
        for (i, (c, depth)) in enumerate(ThreadIterator(container).next()):
            # Some threads starts at a different depth. To make the threads
            # homogeneous, we make them all to start from 0.
            if i == 0 and depth != 0:
                offset = depth
            depth = depth - offset

            msg = parse_message(c.message)
            # Because is the 'From' header, we expect only one address
            addr = apply_aliases(msg['from'], self.aliases)[0]

            if len(sender) <= depth:
                sender.append(addr.normalized_email)
            else:
                sender[depth] = addr.normalized_email

            # Print only when there is a reply and it corresponds to a
            # different person
            if depth > 0 and sender[depth] != sender[depth-1]:
                print(' '*depth, '%s -> %s' % (sender[depth], sender[depth-1]))
