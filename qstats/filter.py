#!/usr/bin/env python
#-*- coding:utf-8 -*-

import sys
sys.path.insert(0, '/home/gpoo/code/research/ml/mailingliststat')

import six
import json
import re
import email
from email.header import decode_header
from email.utils import getaddresses, parsedate_tz
from pymlstats.analyzer import ParseMessage


class Filter:
    def __init__(self, mbox, aliases, subject_filter=None):
        self.mbox = mbox
        self.subject = subject_filter
        self.aliases = self.load_aliases(aliases)

    def load_aliases(self, aliases):
        inv_dict = {}

        if aliases is None:
            return inv_dict

        with open(aliases, 'r') as f:
            data = json.load(f)

        for k, value in iter(data.items()):
            for a in value['alias']:
                inv_dict.setdefault(a, {'email': k.lower(), 'name': value['name']})
                # inv_dict[a] = {'email': k, 'name': value['name']}

        return inv_dict

    def walk(self, container):
        L = list(container.items())
        L.sort()
        for subj, ctr in L:
            for topic, subject, depth in self.print_container(ctr):
                sys.stdout.write(depth * ' ')
                print('%s: %s' % (subject, topic))
#            for depth, message in self.print_container(ctr):
#                #sys.stdout.write(depth * ' ')
#                sys.stdout.write(repr(message.subject))
#                sys.stdout.write('\n')
#            #    print ctr.message.subject
#            # self.print_container(ctr)

    def print_container(self, container, depth=0, debug=False):
        s_generic = False
        topic = None

        if container.message:
            sys.stdout.write(depth * ' ')
            #sys.stdout.write(repr(container.message.subject))
            #sys.stdout.write('\n')
            msg = ParseMessage()
            text = email.message_from_string(str(container.message.message))
            message = msg.parse_message(text)
            msg_from = message['from']

            addr = self.apply_aliases(msg_from)

            msg_subject = message['subject']
            msg_subject = re.sub('\[openstack\-dev\]', '', msg_subject,
                                 flags=re.IGNORECASE)
            msg_subject = re.sub(r'\s+', ' ', msg_subject)
            s_generic, topic = check_subject(msg_subject)

            if s_generic:
                yield topic, msg_subject, depth
                # sys.stdout.write(depth * ' ')
                # print('%s %s: %s' % (s_generic, topic, msg_subject))

        for c in container.children:
            self.print_container(c, depth+1, debug)

    def apply_aliases(self, header):
        addresses = []
        for name, mail in header:
            alias = mail.lower()
            if alias in self.aliases:
                n_name = self.aliases[alias]['name']
                n_mail = self.aliases[alias]['email'].lower()
            else:
                n_name, n_mail = name, mail.lower()

            n_name = check_name(n_name)
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

    def walk2(self, container):
        L = list(container.items())
        L.sort()
        for subj, ctr in L:
            t = ThreadIterator(ctr)
            s = re.sub('\s+', ' ', subj)
            for c, depth in t.next():
                m = self.parse_message(c.message)
                s_generic, topic = check_subject(m['subject'])

                print depth * ' ',
                print depth, s_generic, topic, m['subject']


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


def check_name(name):
    '''
    def str_replace(s, old, new):
        return s.replace(pattern, new)
#        if six.PY2:
#             return s.decode('utf-8').replace(pattern, new).encode('utf-8')
#        else:
#            return s.replace(pattern, new)
    '''

    def str_regex_replace(s, pattern, new):
        if six.PY2:
            s = re.sub(pattern, new, s.decode('utf-8'))
            return s.encode('utf-8')
        else:
            return re.sub(pattern, new, s)

    to_delete = (
                   '"',
                   '\'',
#                   u'\n',
                   u'(CloudOS개발팀)', # CloudOS
                   'Cloud OS R&D',
                   'HP Cloud Services', # HP
                   'HP Storage R&D',
                   'HP Networking',
                   'HPN R&D',
                   'HP Servers',
                   'HP Converged Cloud - Cloud OS',
                   '-X bradjone - AAP3 INC@Cisco',  # Cisco
                   '-X jodavidg - AAP3 INC@Cisco',
                   '-X limao - YI JIN XIN XI FU WUSU ZHOUYOU XIAN GONG SI at\n Cisco',
                   'Brazil R&D-ECL',
                   'HPCS - Ft. Collins',
                   'HPCS Fort Collins',
                   'HPCS Quantum',
                   'STSD',
                   'Contractor',
                   '<gfa>',
                   'ESSN Storage MSDU',
                   '/ NSN',
                   'EXT-Tata Consultancy Ser - FI/Espoo',
                   '(SDN Project)',
                   'LARC-E301[SCIENCE SYSTEMS AND APPLICATIONS, INC]',
                   'PNB Roseville',
                   '-B39208',  # freescale
                   '-B37839',
                   '-B22160',
                   '-B37207',
                   'graflu0',
                   ',ES-OCTO-HCC-CHINA-BJ',
                   'EB SW Cloud - R&D - Corvallis',
                   '71510',
                   'Cloud Services',  # Generic?
                )

    to_replace = (
                    ('michel.gauthier@bull.net', 'Michel Gauthier'),
                    ('Surya_Prabhakar@Dell.com', 'Surya Prabhakar'),
                    ('Greg_Jacobs@Dell.com', 'Greg Jacobs'),
                    ('Phani_Achanta@DELL.com', 'Phani Achanta'),
                    ('Rajesh_Mohan3@Dell.com', 'Rajesh Mohan3'),
                    ('Surya_Prabhakar@Dell.com', 'Surya Prabhakar'),
                    ('Greg_Jacobs@Dell.com', 'Greg Jacobs'),
                    ('Yuling_C@DELL.com', 'Yuling C'),
                    ('Rob_Hirschfeld@Dell.com', 'Rob Hirschfeld'),
                    ('Arkady_Kanevsky@DELL.com', 'Arkady Kanevsky'),
                    ('Stanislav_M@DELLTEAM.com', 'Stanislav M'),
                    ('afe.young@gmail.com', 'Afe Young'),
                    ('lzy.dev@gmail.com', 'Lzy Dev'),
                    ('stuart.mclaren@hp.com', 'Stuart Mclaren'),
                    ('andrew.melton@mailtrust.com', 'Andrew Melton'),
                    ('thomas.morin@orange.com', 'Thomas Morin'),
                    ('Rohit.Karajgi@ril.com', 'Rohit Karajgi'),
                    ('jonathan_gershater@trendmicro.com', 'Jonathan Gershater'),
                    ('venkatesh.nag@wipro.com', 'Venkatesh Nag'),
                    # Alcatel
                    ('MENDELSOHN, ITAI ITAI', 'Itai Mendelsohn'),
                    ('SMIGIELSKI, Radoslaw Radoslaw', 'Radoslaw Smigielski'),
                    ('SHAH, Ronak Ronak R', 'Ronak Shah'),
                    ('Stein, Manuel Manuel', 'Manuel Stein'),
                    ('ELISHA, Moshe Moshe', 'Moshe Elisha'),
                    ('GROSZ, Maty Maty', 'Maty Grosz'),
                    ('Vishal2 Agarwal', 'Vishal Agarwal'),
                    # Red Hat
                    ('marios@redhat.com', 'Marios Andreou'),
                    ('sbauza@redhat.com', 'Sylvain Bauza'),
                    ('tfreger@redhat.com', 'Toni Frege'),
                    # Aegis
                    ('michal@aegis.org.pl', 'Michal Smereczynski'),
                )

    to_replace_regex = (
                    (r'Rochelle.*Grober.*', 'Rochelle Grober'),
                    # StackStorm
                    (r'Dmitri Zimine.*StackStorm', 'Dmitri Zimine'),
                )

    for pattern in to_delete:
        name = name.replace(pattern, '')

    for pattern, new in to_replace:
        # name = str_replace(name, pattern, new)
        name = name.replace(pattern, new)

    for pattern, new in to_replace_regex:
        if re.match(pattern, name):
            name = str_regex_replace(name, pattern, new)

    # Swap names if they come as 'Lastname, Firstname MiddleName'
    name = ' '.join([s.strip() for s in reversed(name.split(','))])

    return name
