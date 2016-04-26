#!/usr/bin/env python

import argparse
import sys
import codecs
from qstats.qstats import parse, print_threads, print_roots, save, load
from qstats.filter import Filter
from qstats.ui import UI


def do_gui(fname, aliases, verbose=0):
    o = load(fname)
    # p = Filter(o, aliases)
    ui = UI(o, 'output_file')
    ui.main()


def do_filter(fname, aliases, verbose=0):
    o = load(fname)
    p = Filter(o, aliases)
    p.walk_extended(o)


def do_load(fname, root_only=False, verbose=0):
    o = load(fname)

    if root_only:
        print_roots(o, debug=False)
        return

    if verbose > 1:
        print_threads(o, debug=True)
    elif verbose == 1:
        print_threads(o, debug=False)


def do_parse(files, save_file, verbose=False):
    subject_table = parse(files)
    if save_file:
        print('Save')
        save(subject_table, save_file)
    if verbose:
        print_threads(subject_table)


def main():
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

    help_parse = 'Parse compressed mailbox archives'

    arger = argparse.ArgumentParser()

    # Arguments for top-level
    arger.add_argument("-v", "--verbose", action="count", default=0)

    subparsers = arger.add_subparsers(dest='command',
                                      title='Commands',
                                      description='Commands available')

    # Commands' parsers
    report_parser = subparsers.add_parser('report', help='Print a report')
    report_parser.add_argument('file')
    report_parser.add_argument('-r', '--root-only', action='store_true',
                               dest='root')

    filter_parser = subparsers.add_parser('filter',
                                          help='Filter an existing mbox')
    filter_parser.add_argument('file', help='MBox Pickled')
    filter_parser.add_argument('-a', '--aliases', dest='aliases')

    parse_parser = subparsers.add_parser("parse", help=help_parse)
    parse_parser.add_argument("files", nargs="+")
    parse_parser.add_argument('-s', '--save', dest='save')

    gui_parser = subparsers.add_parser("gui", help=help_parse)
    gui_parser.add_argument("file", help='MBox Pickled')
    gui_parser.add_argument('-a', '--aliases', dest='aliases')

    # Parse
    opts = arger.parse_args()

    # Commands in alphabetical order
    if opts.command == 'gui':
        do_gui(opts.file, opts.aliases, opts.verbose)

    elif opts.command == 'filter':
        do_filter(opts.file, opts.aliases, opts.verbose)

    elif opts.command == "parse":
        do_parse(opts.files, opts.save, opts.verbose)

    elif opts.command == 'report':
        do_load(opts.file, opts.root, opts.verbose)

    else:
        # argparse will error on unexpected commands, but
        # in case we mistype one of the elif statements...
        raise ValueError("Unhandled command %s" % opts.command)


if __name__ == '__main__':
    main()
