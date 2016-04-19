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
        self.subject = builder.get_object('lbl_subject')

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
        model, storeiter = selection.get_selected()
        first_entry = True

        if not storeiter:
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

        self.model_thread.clear()

        # subject = model.get_value(storeiter, 0)
        # container = model.get_value(storeiter, 1)
        subject, container = model[storeiter][:2]
        self.subject.set_text(subject)

        participants = {}
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
            sender_name, sender_email,  = msg['from'][0]
            participants.setdefault(sender_email, {'name': sender_name,
                                                   'count': 0})
            participants[sender_email]['count'] += 1

            if i == 1:
                d['name'], d['email'] = sender_name, sender_email
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

        print({x: participants[x]['count'] for x in participants})

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
