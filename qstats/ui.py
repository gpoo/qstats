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

import os.path
import sys
import codecs
import csv
import re
import gi

gi.require_version('GtkSource', '3.0')
gi.require_version('Gtk', '3.0')

from gi.repository import GObject, Gtk, Gdk, GtkSource, Pango

from .filter import ThreadIterator, parse_message, check_subject


class UI:
    APP_NAME = 'Discussions\' Classifier'

    def __init__(self, threads, output_file, ui='qstats.ui', *args):
        # self.index = files_location
        # self.metadata = metadata
        self.threads = threads
        self.output_file = output_file
        self.content_type = {}
        self.in_progress = False  # State for variable initialization
        self.is_modified = False  # State that requires saving the data
        self.cache_filtered_subject = {}

        builder = Gtk.Builder()
        builder.add_from_file(os.path.join(os.path.dirname(__file__), ui))
        self.accelerators = Gtk.AccelGroup()

        self.window = builder.get_object('window')
        self.window.add_accel_group(self.accelerators)
        self.window.set_title(self.APP_NAME)

        sw = builder.get_object('sw_textview')

        self.textbuffer = GtkSource.Buffer()
        self.lm = GtkSource.LanguageManager()

        self.sourceview = GtkSource.View.new_with_buffer(self.textbuffer)
        self.sourceview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.sourceview.set_show_line_marks(True)
        self.add_accelerator(self.sourceview, '<alt>o', 'grab-focus')
        sw.add(self.sourceview)

        sw = builder.get_object('sw_treeview_main')
        self.model = Gtk.ListStore(str, GObject.TYPE_PYOBJECT)
        self.list_threads = Gtk.TreeView()
        self.list_threads.set_headers_visible(False)
        self.list_threads.set_model(self.model)
        self.add_accelerator(self.list_threads, '<alt>g', 'grab-focus')
        self.selinfo = self.list_threads.get_selection()
        self.selinfo.connect('changed', self.select_row)

        # Renderers for Threads
        renderer = Gtk.CellRendererText()
        renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        # renderer.set_property('xalign', 1.0)
        col = Gtk.TreeViewColumn('Thread id', renderer, text=0)
        col.set_resizable(True)
        self.list_threads.append_column(col)

        sw.add(self.list_threads)

        # Old list files
        self.model_files = Gtk.ListStore(str, str, str, int, int, int, str)
        self.list_files = Gtk.TreeView()
        self.list_files.set_model(self.model_files)
        self.add_accelerator(self.list_files, '<alt>f', 'grab-focus')
        self.selinfo_files = self.list_files.get_selection()
        self.selinfo_files.connect('changed', self.select_row_files)

        # Messages per thread
        sw = builder.get_object('sw_treeview_detail')
        self.model_thread = Gtk.TreeStore(str,  # subject
                                          GObject.TYPE_PYOBJECT,  # topics list
                                          int,  # Depth (in thread)
                                          GObject.TYPE_PYOBJECT,  # Message
                                          bool,  # Is Global/Generic
                                          str  # Date
                                          )
        self.tree_thread = Gtk.TreeView()
        self.tree_thread.set_model(self.model_thread)
        self.add_accelerator(self.tree_thread, '<alt>t', 'grab-focus')
        self.selinfo_thread = self.tree_thread.get_selection()
        self.selinfo_thread.connect('changed', self.select_row_thread)

        renderer = Gtk.CellRendererText()
        renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        renderer.set_property('xalign', 0.0)
        col = Gtk.TreeViewColumn('Subject', renderer, text=0)
        col.set_resizable(True)
        col.set_expand(True)
        self.tree_thread.append_column(col)

        renderer = Gtk.CellRendererText()
        renderer.set_property('xalign', 1.0)
        col = Gtk.TreeViewColumn('Date', renderer, text=5)
        self.tree_thread.append_column(col)

        renderer = Gtk.CellRendererText()
        renderer.set_property('xalign', 1.0)
        col = Gtk.TreeViewColumn('L', renderer, text=2)
        self.tree_thread.append_column(col)

        renderer = Gtk.CellRendererToggle()
        renderer.set_property('xalign', 0.0)
        col = Gtk.TreeViewColumn('G', renderer, active=4)
        self.tree_thread.append_column(col)

        sw.add(self.tree_thread)

        self.content_type = {
            'Code': builder.get_object('cb_code'),
            'Test': builder.get_object('cb_test'),
            'Class': builder.get_object('cb_class'),
            'Template': builder.get_object('cb_template'),
            'Command': builder.get_object('cb_command'),
            'Function': builder.get_object('cb_function'),
            'Fragment': builder.get_object('cb_fragment'),
            'Note': builder.get_object('cb_note'),
            'Log': builder.get_object('cb_log'),
            'Configuration': builder.get_object('cb_configuration'),
            'Diff': builder.get_object('cb_diff'),
            'Documentation': builder.get_object('cb_documentation'),
            'Data': builder.get_object('cb_data'),
            'Blog': builder.get_object('cb_blog'),
            'Non-technical': builder.get_object('cb_non_technical')
        }

        self.topology = {
            'Single': builder.get_object('rb_single'),
            'Siblings': builder.get_object('rb_siblings'),
            'Reference': builder.get_object('rb_reference'),
            'Generation': builder.get_object('rb_generation'),
            'Test': builder.get_object('rb_test'),
            'Attachment': builder.get_object('rb_attachment')
        }
        self.remark = builder.get_object('textview_remarks').get_buffer()
        # self.remark.connect('changed', self.on_remark_changed)

        self.details = builder.get_object('textview_details').get_buffer()

        self.window.add_events(Gdk.EventType.KEY_PRESS |
                               Gdk.EventType.KEY_RELEASE)
        self.window.connect('key-press-event', self.on_window_key_press)
#        self.add_accelerator(self.play_button, '<ctrl>p', 'clicked')
#        self.add_accelerator(self.play_button, '<ctrl>space', 'clicked')
#        self.add_accelerator(self.play_button, 'F5', 'clicked')

        builder.connect_signals(self)

#       threads = sorted(self.threads.keys(), key=lambda x: int(x, 16))
        self.load_model(threads)

    def load_model(self, data):
        L = list(data.items())
        L.sort()
        regex = re.compile(r'\s+')
        for subject, container in L:
            subject = regex.sub(' ', subject).strip()
            self.model.append([subject, container])
            # self.model.set_value(iter, 0, subject)
            # self.model.set_value(iter, 1, container)

    def get_message_id_by_subject(self, subject):
        if subject not in self.cache_filtered_subject:
            result = self.db.get_messages_id_by_filtered_subject(subject)
            self.cache_filtered_subject[subject] = [r for r in result]

        return self.cache_filtered_subject[subject]

    def select_row(self, selection, *data):
        model_detail, iter = selection.get_selected()
        model, storeiter = selection.get_selected()
        first_entry = True

        if not iter:
            return

        d = {
            'n_participants': 0,
            'n_messages': 0,
            'url': '',
            'dstart': 'start',
            'dend': 'end',
            'name': 'name',
            'email': 'email',
            'duration': 'duration',
            'subject': 'subject'
        }

        self.model_files.clear()
        self.model_thread.clear()

        # subject = model.get_value(storeiter, 0)
        # container = model.get_value(storeiter, 1)
        subject, container = model[storeiter][:2]

        participants = set()
        t = ThreadIterator(container)
        for (i, (c, depth)) in enumerate(t.next(), 1):
            msg = parse_message(c.message)
            is_generic, topic = check_subject(msg['subject'])

            treeiter = self.model_thread.append(None)
            self.model_thread[treeiter][0] = depth * ' ' + msg['subject']
            # Previously: ' '.join(topic) if topic else ''
            self.model_thread[treeiter][1] = topic
            self.model_thread[treeiter][2] = depth
            self.model_thread[treeiter][3] = msg
            self.model_thread[treeiter][4] = is_generic
            self.model_thread[treeiter][5] = msg['date'].strftime('%x')
            participants.add(msg['from'][0])

            if i == 1:
                d['name'], d['email'] = msg['from'][0]
                min_date, max_date = msg['date'], msg['date']

            min_date = msg['date'] if msg['date'] < min_date else min_date
            max_date = msg['date'] if msg['date'] > max_date else max_date

            print(topic)

        d['n_participants'] = len(participants)
        d['n_messages'] = len(self.model_thread)
        # d['subject'] = subject
        d['dstart'] = min_date
        d['dend'] = max_date
        d['duration'] = max_date - min_date

        print([x[1] for x in participants])

        text = 'From {} to {}\n{}\n' \
               'Started by: {} <{}>\n' \
               'Msgs: {}, Participants: {}\n' \
               '{}\n{}'
        text = text.format(d['dstart'], d['dend'], d['duration'],
                           d['name'], d['email'],
                           d['n_messages'], d['n_participants'],
                           d['subject'], d['url'])
        start, end = self.details.get_bounds()
        self.details.delete(start, end)
        end = self.details.get_end_iter()
        self.details.insert(end, text)

        return
        ''' DELETE from here to the end of the method '''
        thread_id = model_detail.get_value(iter, 0)

        d = self.threads[thread_id]
        print(d['topics'])
        for message_id in self.get_message_id_by_subject(d['subject']):
            if len(message_id) > 1:
                print('Error: ', message_id)
                continue

            msg_id = message_id[0]

            metadata = [m for m in self.db.get_metadata(msg_id)]
#            if len(metadata) > 1:
#                print('Error: TOO_MANY_FROM', msg_id)
#                continue
            # Results have the format: (type_of_recipient, email_address)
            # type can be: From, To, Cc
            mail_from = metadata[0][1] if 'From' in metadata[0] else None
            mail_date = metadata[0][2] if 'From' in metadata[0] else None
            print(mail_date.isoformat())
            # ','.join([m[1] for m in metadata if 'From' in m[0]])
            # mail_to = ','.join([m[1] for m in metadata if 'To' in m[0]])
            # mail_cc = ','.join([m[1] for m in metadata if 'Cc' in m[0]])

            # self.check_subject(d['subject'])

            iter = self.model_files.append()
            # self.model_files.set_value(iter, 0, msg_id)
            self.model_files.set_value(iter, 0, mail_from)
            # 1 is to store any data not shown, but eventualy used
            # self.model_files.set_value(iter, 1, d['duration'])
            self.model_files.set_value(iter, 2, mail_date.isoformat())
            self.model_files.set_value(iter, 3, d['n_messages'])
            self.model_files.set_value(iter, 4, d['n_participants'])
            self.model_files.set_value(iter, 5, thread_id)
            self.model_files.set_value(iter, 6, msg_id)

        for k in ['url', 'dstart', 'dend', 'name', 'n_participants',
                  'n_messages', 'duration', 'subject']:
            widget = self.thread_data[k]
            if k == 'url':
                widget.set_uri(d[k])
                # widget.set_label('detail')
                # continue
            elif k == 'name':
                widget.set_label('{} <{}>'.format(d[k], d['email']))
                continue

            widget.set_label(str(d[k]))

        if first_entry:
            path = Gtk.TreePath.new_from_string('0')
            self.selinfo_files.select_path(path)
            first_entry = False

#         if detail in self.index:
#             self.set_content_type(detail)

#            for fname in self.index[detail]:
#                short_name = os.path.basename(fname)
#                short_name = short_name.replace('{}_'.format(detail), '', 1)
#
#                files = self.metadata[detail]['files']
#                try:
#                    lang, size, lines = files[short_name][0:3]
#                except KeyError:
#                    print('{}: {} not found'.format(detail, files),
#                          file=sys.stderr)
#                    lang, size, lines = ('', 0, 0)
#
#                iter = self.model_files.append()
#                self.model_files.set_value(iter, 0, short_name)
#                self.model_files.set_value(iter, 1, fname)
#                self.model_files.set_value(iter, 2, lang or '---')
#                self.model_files.set_value(iter, 3, size)
#                self.model_files.set_value(iter, 4, lines)
#                self.model_files.set_value(iter, 5, detail)
#
#                if first_entry:
#                    path = Gtk.TreePath.new_from_string('0')
#                    self.selinfo_files.select_path(path)
#                    fist_entry = False
#
#        data = self.metadata[detail]['data']
#        for k, v in data.items():
#            if k not in self.thread_data:
#                print('{} not in thread_data'.format(k))
#                continue
#
#            widget = self.threaddata[k]
#
#            if k == 'url':
#                widget.set_label('detail')
#                widget.set_uri(v)
#                continue
#
#            widget.set_label(str(v))

    def set_content_type(self, gistid):
        self.in_progress = True
        detail = self.threads[gistid]
        for w in self.content_type.values():
            w.set_active(False)

        if detail['label']:
            for label in detail['label'].split(';'):
                widget = self.content_type[label.capitalize()]
                try:
                    widget.set_active(True)
                except KeyError:
                    print(label, file=sys.stderr)
                    print(widget, file=sys.stderr)

        start, end = self.remark.get_bounds()
        self.remark.delete(start, end)
        end = self.remark.get_end_iter()
        self.remark.insert(end, detail['remark'])

        relation = detail['relation'] or 'Single'
        self.topology[relation].set_active(True)

        self.in_progress = False

    def select_row_thread(self, selection, *data):
        model, treeiter = selection.get_selected()

        if not treeiter:
            return

        subject, topic, depth, message = model[treeiter][:4]
        body = message['body']

        start, end = self.textbuffer.get_bounds()
        self.textbuffer.delete(start, end)
        end = self.textbuffer.get_end_iter()
        self.textbuffer.insert(end, body)

    def select_row_files(self, selection, *data):
        ''' DELETE '''
        model, iter = selection.get_selected()

        if not iter:
            return

        message_id = model.get_value(iter, 6)
        body = [b for b in self.db.get_body(message_id)]

        if len(body) == 0:
            print('Error (NO BODY):', message_id)
            return

        if len(body) > 1:
            print('Error (REPEATED MESSAGE ID):', message_id, body)

        body = body[0][0]

        start, end = self.textbuffer.get_bounds()
        self.textbuffer.delete(start, end)
        end = self.textbuffer.get_end_iter()
        self.textbuffer.insert(end, body)

        # fname = model.get_value(iter, 1)
        # lang = model.get_value(iter, 2).replace('---', '')
        # self.load_file(fname, lang)

    def load_file(self, fname, lang):
        ext = os.path.splitext(fname)[1][1:].lower()
        lang = lang.lower() or ext
        lang = lang if lang not in ('javascript', 'shell') else ext
        lang = lang if lang not in ('C#') else 'c-sharp'
        self.textbuffer.set_language(self.lm.get_language(lang))

        try:
            with codecs.open(fname, 'rU', 'utf-8') as f:
                start, end = self.textbuffer.get_bounds()
                self.textbuffer.delete(start, end)
                end = self.textbuffer.get_end_iter()
                self.textbuffer.insert(end, f.read())
        except IOError:
            print('Error loading {}'.format(fname), file=sys.stderr)

    def on_content_type_toggled(self, widget, *args):
        # Do something only if the user toggled the check box,
        # not the program
        if self.in_progress:
            return

        values = []

        model_detail, iter = self.selinfo.get_selected()
        thread_id = model_detail.get_value(iter, 0)

        for label, w in self.content_type.items():
            if w.get_active():
                values.append(label)

        self.threads[thread_id]['label'] = ';'.join(values)
        self.is_modified = True

    def on_remark_changed(self, widget, *args):
        if self.in_progress:
            return

        start, end = self.remark.get_bounds()
        text = self.remark.get_text(start, end, False)

        model_detail, iter = self.selinfo.get_selected()
        thread_id = model_detail.get_value(iter, 0)

        self.threads[thread_id]['remark'] = text
        self.is_modified = True

    def on_topology_toggled(self, widget, *args):
        if self.in_progress:
            return

        model_detail, iter = self.selinfo.get_selected()
        thread_id = model_detail.get_value(iter, 0)

        if widget.get_active():
            self.threads[thread_id]['relation'] = widget.get_label().capitalize()
            self.is_modified = True

    def on_window_delete_event(self, *args):
        """Release resources and quit the application."""

        msg = 'Do you really want to close the application?'

        dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.INFO,
                                   Gtk.ButtonsType.YES_NO,
                                   'There are pending changes.')
        dialog.format_secondary_text(msg)

        if self.is_modified:
            response = dialog.run()
            dialog.destroy()

            if response != Gtk.ResponseType.YES:
                # Don't close the window, go back to the application
                return True

        Gtk.main_quit(*args)

    def on_window_key_press(self, window, event, *args):
        """Handle global keystrokes to move the sliders"""

        # We handle Ctrl
        if event.state != 0 and (event.state & Gdk.ModifierType.CONTROL_MASK):
            if event.keyval == Gdk.KEY_s:
                self.save()
            else:
                return False
            return True

        return False

    def add_accelerator(self, widget, accelerator, signal='activate'):
        """Adds a keyboard shortcut to widget for a given signal."""

        if accelerator:
            key, mod = Gtk.accelerator_parse(accelerator)
            widget.add_accelerator(signal, self.accelerators, key, mod,
                                   Gtk.AccelFlags.VISIBLE)

    def save(self):
        if not self.is_modified:
            return

        with open(self.output_file, 'w') as fd:
            writer = csv.writer(fd, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['id', 'Labels', 'Num_of_Files',
                             'Relationship between files', 'Content',
                             'Remark', 'Source'])

            detail = sorted(self.threads.keys(), key=lambda x: int(x, 16))

            for thread_id in detail:
                data = self.threads[thread_id]
                writer.writerow([thread_id, data['label'],
                                 self.metadata[thread_id]['data']['fcount'],
                                 data['relation'], data['content'],
                                 data['remark'], data['source']])

            self.is_modified = False

    def main(self):
        self.window.show_all()
        Gtk.main()
