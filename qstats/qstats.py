#!/usr/bin/env python

import sys
sys.path.insert(0, '/home/gpoo/code/research/ml/mailingliststat')

import gzip
import pickle
from pymlstats.strictmbox import CustomMailbox
from .jwzthreading import make_message, thread


def process_mbox(fp):
    # print(fp.read())
    mbox = CustomMailbox(fp)
    msglist = []
    for msg in mbox:
        m = make_message(msg)
        msglist.append(m)
    return msglist


def parse(files_list):
    msglist = []

    for f in files_list:
        fp = gzip.GzipFile(f, mode='r')
        msglist += process_mbox(fp)
        fp.close()

    return thread(msglist)


def print_threads(o, debug=False):
    # Output
    L = list(o.items())
    L.sort()
    for subj, container in L:
        print_container(container, debug=debug)


def print_roots(o, debug=False):
    L = list(o.items())
    L.sort()
    for subj, container in L:
        # print_container(container, debug=True)

        if debug:
            # Printing the repr() is more useful for debugging
            sys.stdout.write(repr(container))
        else:
            if container.message:
                sys.stdout.write(repr(container.message) + ' ' +
                                 repr(container.message.subject))
            else:
                sys.stdout.write('+++' + subj)
        sys.stdout.write('\n')


def print_container(container, depth=0, debug=False):
    sys.stdout.write(depth*' ')
    if debug:
        # Printing the repr() is more useful for debugging
        sys.stdout.write(repr(container))
    else:
        sys.stdout.write(repr(container.message and container.message.subject))

    sys.stdout.write('\n')
    for c in container.children:
        print_container(c, depth+1, debug)


def save(o, fname):
    with open(fname, 'wb') as fp:
        pickle.dump(o, fp, -1)


def load(fname):
    with open(fname, 'rb') as fp:
        o = pickle.load(fp)

    return o
