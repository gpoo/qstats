#!/usr/bin/env python
# -*- coding:utf-8 -*-

from __future__ import print_function

import six
import json
import re
import email
from pymlstats.analyzer import ParseMessage


class AliasesFilter:
    aliases = {}
    to_delete = {}
    to_replace = {}
    to_replace_regex = {}


class Filter:
    def __init__(self, mbox, aliases, subject_filter=None):
        self.mbox = mbox
        self.subject = subject_filter
        self.aliases = self.load_aliases(aliases)

    def load_aliases(self, aliases):
        alias = AliasesFilter()

        if aliases is None:
            return alias

        with open(aliases, 'r') as f:
            data = json.load(f)

        for k, value in iter(data['aliases'].items()):
            for a in value['alias']:
                alias.aliases.setdefault(a, {'email': k.lower(),
                                             'name': value['name']})
        alias.to_delete = data['name_delete']
        alias.to_replace = data['name_replace']
        # [[a.replace('\\', '\\\\'), b] for a, b in data['text_patterns']]
        alias.to_replace_regex = data['name_patterns']

        return alias

    def apply_aliases_extended(self, header):
        def check_name_extended(name, aliases):
            def str_regex_replace(s, pattern, new):
                if six.PY2:
                    s = re.sub(pattern, new, s.decode('utf-8'))
                    return s.encode('utf-8')
                else:
                    return re.sub(pattern, new, s)

            for pattern in aliases.to_delete:
                name = name.replace(pattern, '')

            for pattern, new in aliases.to_replace:
                # name = str_replace(name, pattern, new)
                name = name.replace(pattern, new)

            for pattern, new in aliases.to_replace_regex:
                if re.match(pattern, name):
                    name = str_regex_replace(name, pattern, new)

            # Swap names if they come as 'Lastname, Firstname MiddleName'
            name = ' '.join([s.strip() for s in reversed(name.split(','))])

            return name

        addresses = []
        for name, mail in header:
            alias = mail.lower()
            if alias in self.aliases.aliases:
                n_name = self.aliases.aliases[alias]['name']
                n_mail = self.aliases.aliases[alias]['email'].lower()
            else:
                n_name, n_mail = name, mail.lower()

            n_name = check_name_extended(n_name, self.aliases)
            addresses.append([name, mail, n_name, n_mail])

        return addresses

    def parse_message(self, threaded_message):
        parser = ParseMessage()
        text = email.message_from_string(str(threaded_message))
        message = parser.parse_message(text)

        msg_subject = message['subject']
        msg_subject = re.sub('\[openstack\-dev\]', '', msg_subject,
                             flags=re.IGNORECASE)
        msg_subject = re.sub(r'\s+', ' ', msg_subject)
        message['subject'] = msg_subject

        return message

    def walk(self, container):
        L = list(container.items())
        L.sort()
        for subj, ctr in L:
            t = ThreadIterator(ctr)
            for c, depth in t.next():
                m = self.parse_message(c.message)
                s_generic, topic = check_subject(m['subject'])

                print(depth * ' ', end='')
                print(depth, s_generic, topic, m['subject'])

    def walk_extended(self, container):
        L = list(container.items())
        L.sort()
        for subj, ctr in L:
            t = ThreadIterator(ctr)
            for c, depth in t.next():
                m = self.parse_message(c.message)
                s_generic, topic = check_subject(m['subject'])

                addr = self.apply_aliases_extended(m['from'])

                print(depth * ' ', end='')
                print(depth, s_generic, topic, m['subject'])
                for n1, e1, n2, e2 in addr:
                    if n1 != n2 or e1 != e2:
                        print('%s %s <%s> -> %s <%s>' % (depth * ' ',
                                                         n1, e1, n2, e2))


class ThreadIterator():
    def __init__(self, root):
        self._current = root

    def __iter__(self):
        return self

    def next(self):
        return self._next(self._current)

    def _next(self, curr, depth=0):
        if curr.message:
            yield curr.message, depth

        for c in curr.children:
            for x in self._next(c, depth+1):
                yield x


def parse_message(threaded_message):
    parser = ParseMessage()
    text = email.message_from_string(str(threaded_message))
    message = parser.parse_message(text)

    msg_subject = message['subject']
    msg_subject = re.sub('\[openstack\-dev\]', '', msg_subject,
                         flags=re.IGNORECASE)
    msg_subject = re.sub(r'\s+', ' ', msg_subject)
    message['subject'] = msg_subject.strip()

    return message


def check_subject(subject):
    '''Check if the topics generic for OpenStack or particular to
       a specific project.
       When there are multiple topics, we assume is a broad discussion,
       and therefore, generic.
    '''
    topic_pattern = re.compile(r'((Fwd: )*\[[\w\-]*\]\s*)+', re.IGNORECASE)

    # s = re.match(r'((Fwd: )*\[[\w\-]*\]\s*)+', subject, re.IGNORECASE)
    s = subject.replace('\n', '')
    s = topic_pattern.match(s.strip())
    if s:
        f = s.group().lower()
        # f = re.sub(r'(\\n', ' ', f)
        f = re.sub(r'fwd:\s*', '', f)
        f = re.sub(r'\s*', '', f)
        f = re.sub(r'\[', '', f)
        f = re.sub(r'\]', ',', f).rstrip(',')
        c = f.split(',')
        if 'openstack' in c or 'general' in c or 'common' in c\
           or len(c) > 1:
            return True, c
        else:
            return False, None
    else:
        return True, ['openstack']
