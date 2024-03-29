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


'''
Create a social network from email threads, based on the idea used by
Bohn et al "Content-Based Social Network Analysis of Mailing Lists",
2011, The R Journal.
http://journal.r-project.org/archive/2011-1/RJournal_2011-1_Bohn~et~al.pdf

"Somebody answering an e-mail [is] connected to all the authors who wrote
something before (chronologically) in the same thread as we assume that
the respondent is aware of all the previous e-mails."
'''


class Network:
    def __init__(self, threads, csv_file, aliases, *args):
        self.threads = threads
        self.ithread = collections.OrderedDict()  # Internal dict of threads
        self.csv_file = csv_file
        self.aliases = aliases

        self.ithread = utils.load_threads_data_from_csv(self.csv_file)
        self.load_thread_containers(threads)

    def load_thread_containers(self, data, verbose=False):
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
                if verbose:
                    print('%s does not exists' % cid)

    def main(self, verbose=False):
        pairs = collections.Counter()
        senders_and_recipients = collections.Counter()
        names = {}

        for cid, data in self.ithread.iteritems():
            if data['generic'] != 'True' or data['category'] != 'Other':
                continue
            # Check for consistency of
            if 'container' not in data:
                if verbose:
                    print('No container for %s' % cid)
                continue
            p, s, r, n = self.do_pair_discussion_participans(data['container'])
            pairs.update(p)
            senders_and_recipients.update(s)
            senders_and_recipients.update(r)
            names.update(n)

        utils.print_flat_relations_gexf(pairs, senders_and_recipients, names)

    def do_pair_discussion_participans(self, container, verbose=False):
        '''
            Establish relationhips bewtween participants in a discussion.
            Two participants are related if both of them participate in
            the same thread of a discussion. For example, in the following
            discussion started by A:
                A
                + B
                  + C
                  + D
                    + E
                B -> A                       '->': replies.  B replies to A
                C -> B, C -> A
                D -> B, D -> A
                E -> D, E -> B, E -> A

            D and C, E and C are not directly engaged in the same thread,
            although both of them participate in the same discussion.

        '''
        offset = 0
        sender = []
        senders = []
        recipients = []
        interactions = []
        names = {}
        unique_pairs = []

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

            names[addr.normalized_email] = addr.normalized_name

            for x in range(0, depth):
                if sender[depth] != sender[x]:
                    tkey = '%d %s -> %s' % (x, sender[depth], sender[x])
                    if tkey in unique_pairs:
                        continue
                    unique_pairs.append(tkey)

                    key = '%s -> %s' % (sender[depth], sender[x])
                    interactions.append(key)
                    senders.append(sender[depth])
                    recipients.append(sender[depth-1])
                    if verbose:
                        print(i, depth * ' ' + key, depth, x)

        return interactions, senders, recipients, names
