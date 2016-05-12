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
import csv
import re
import collections
import gi

gi.require_version('GtkSource', '3.0')
gi.require_version('Gtk', '3.0')

from gi.repository import GObject, Gtk, Gdk, GtkSource, Pango

from .filter import ThreadIterator, parse_message, check_subject
import utils


class UI:
    APP_NAME = 'Discussions\' Classifier'

    def __init__(self, threads, output_file, ui='qstats.ui', *args):
        self.threads = threads
        self.ithread = collections.OrderedDict()  # Internal dict of threads
        self.csv_file = output_file
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
        # self.sourceview.set_show_line_marks(True)
        self.add_accelerator(self.sourceview, '<alt>o', 'grab-focus')
        sw.add(self.sourceview)

        self.model = Gtk.ListStore(str,  # subject
                                   GObject.TYPE_PYOBJECT,  # container
                                   int,  # index
                                   bool,  # is a general topic
                                   bool  # is 'openstack' topic
                                   )
        self.model_filter = self.model.filter_new()
        self.model_filter.set_visible_func(self.model_filter_func)

        self.list_threads = builder.get_object('treeview_list_threads')
        self.list_threads.set_model(self.model_filter)
        self.add_accelerator(self.list_threads, '<alt>g', 'grab-focus')

        # Renderers for Threads
        # renderer = Gtk.CellRendererText()
        # renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
        # # renderer.set_property('xalign', 1.0)
        # col = Gtk.TreeViewColumn('Thread id', renderer, text=0)
        # col.set_resizable(True)
        # self.list_threads.append_column(col)

        renderer = Gtk.CellRendererText()
        renderer.set_property('xalign', 1.0)
        col = Gtk.TreeViewColumn('Index', renderer, text=2)
        col.set_resizable(True)
        col.set_expand(True)
        self.list_threads.append_column(col)

        renderer = Gtk.CellRendererToggle()
        # renderer.set_property('xalign', 0.0)
        col = Gtk.TreeViewColumn('OpenStack?', renderer, active=4)
        self.list_threads.append_column(col)
        renderer.connect("toggled", self.on_list_thread_cell_toggled)

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

        self.category = builder.get_object('entry_topic')
        category_completion = builder.get_object('entrycompletion_topic')
        self.category_model = Gtk.ListStore(str)
        category_completion.set_model(self.category_model)
        category_completion.set_text_column(0)
        candidates = [
                      'Announcement',
                      'Expertise seeking',
                      'Events',
                      'Knowledge seeking',
                      'Out of scope',
                      'Proposals & discussions',
                      'Reminders',
                      'Request for comments',
                      'Request for decision',
                      'Other'
                      ]
        for word in candidates:
            self.category_model.append([word])

        self.treeview_categories = builder.get_object('treeview_categories')
        self.treeview_categories.set_model(self.category_model)
        # self.add_accelerator(self.tree_thread, '<alt>t', 'grab-focus')
        # self.selinfo_thread = self.tree_thread.get_selection()
        # self.selinfo_thread.connect('changed', self.select_row_thread)
        renderer = Gtk.CellRendererText()
        # renderer.set_property('xalign', 1.0)
        col = Gtk.TreeViewColumn('Category', renderer, text=0)
        self.treeview_categories.append_column(col)

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
        self.ithread = self.load_threads_data_from_csv()
        self.load_model(threads)

    def load_threads_data_from_csv(self, input_file=None):
        filename = input_file or self.csv_file
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

    def load_model(self, data):
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
                self.ithread[cid] = {'container': container,
                                     'generic': False,
                                     '# participants': 0,
                                     '# messages': 0,
                                     'start': '',
                                     'end': '',
                                     'email': '',
                                     'duration': '',
                                     'index': index,
                                     'category': ''
                                     }

            self.model.append([subject, container, index,
                               self.ithread[cid]['generic'], False])
            # self.model.set_value(iter, 0, subject)
            # self.model.set_value(iter, 1, container)

    def get_message_id_by_subject(self, subject):
        if subject not in self.cache_filtered_subject:
            result = self.db.get_messages_id_by_filtered_subject(subject)
            self.cache_filtered_subject[subject] = [r for r in result]

        return self.cache_filtered_subject[subject]

    def on_entry_topic_changed(self, entry, *data):
        selection = self.list_threads.get_selection()
        model, treeiter = selection.get_selected()

        if not treeiter:
            return

        subject, container = model[treeiter][:2]
        msgid = 'None' if not container.message else container.message.message_id
        cid = '{}-{}'.format(msgid, subject)

        self.ithread[cid]['category'] = entry.get_text()

        self.is_modified = True

    def select_category(self, selection, *data):
        model, treeiter = selection.get_selected()

        if not treeiter:
            return

        if model[treeiter][0] != self.category.get_text():
            self.category.set_text(model[treeiter][0])
            self.is_modified = True

    def model_filter_func(self, model, iter, data):
        '''Tests if the language in the row is the one in the filter'''
        return model[iter][3]

    def find_category_iter(self, category):
        for row in self.category_model:
            if category == row[0]:
                return row.iter

        return None

    def on_list_threads_select_row(self, selection, *data):
        def update_category(category):
            '''
               Set the text for entry and select/unselect the category
               from the listview depending on the category given
            '''
            self.category.set_text(category)

            selection = self.treeview_categories.get_selection()
            model, category_iter = selection.get_selected()

            if len(self.ithread[cid]['category']) == 0 and category_iter:
                selection.unselect_iter(category_iter)
                return

            selected_category_iter = self.find_category_iter(category)
            if selected_category_iter:
                selection.select_iter(selected_category_iter)

        model, storeiter = selection.get_selected()

        if not storeiter:
            return

        d = {
            '# participants': 0,
            '# messages': 0,
            'start': 'start',
            'end': 'end',
            'name': 'name',
            'email': 'email',
            'duration': 'duration'
        }

        self.model_thread.clear()

        subject, container = model[storeiter][:2]
        self.subject.set_text(subject)
        msgid = 'None' if not container.message else container.message.message_id
        cid = '{}-{}'.format(msgid, subject)

        update_category(self.ithread[cid]['category'])

        participants = {}
        is_generic = False
        topics = set()
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

            if i == 1:  # First entry
                d['name'], d['email'] = sender_name, sender_email
                min_date, max_date = msg['date'], msg['date']

                path = Gtk.TreePath.new_from_string('0')
                self.selinfo_thread.select_path(path)

            min_date = msg['date'] if msg['date'] < min_date else min_date
            max_date = msg['date'] if msg['date'] > max_date else max_date

            if topic is not None:
                for t in topic:
                    topics.add(t)

        d['# participants'] = len(participants)
        d['# messages'] = len(self.model_thread)
        d['start'] = min_date.strftime('%d-%m-%Y')
        d['end'] = max_date.strftime('%d-%m-%Y')
        d['duration'] = max_date - min_date

        # Check if any message in the thread is 'general'
        model[storeiter][4] = 'openstack' in topics
        # is_generic_thread = len([x[4] for x in self.model_thread if x[4]]) > 0
        is_generic_thread = 'openstack' in topics or len(topics) > 1
        model[storeiter][3] = is_generic_thread

        self.ithread[cid]['generic'] = is_generic_thread
        self.ithread[cid].update(d)

        # print({x: participants[x]['count'] for x in participants})
        try:
            theme = ', '.join(topics)
        except:
            print(topics)

        text = u'{} to {}\n{}\n' \
               '{} <{}>\n' \
               'Msgs: {}, Participants: {}\n' \
               '{}'
        text = text.format(d['start'], d['end'], d['duration'],
                           d['name'], d['email'],
                           d['# messages'], d['# participants'],
                           theme)
        start, end = self.details.get_bounds()
        self.details.delete(start, end)
        end = self.details.get_end_iter()
        self.details.insert(end, text)

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

    def on_list_thread_cell_toggled(self, *args):
        '''
        Manual change of a thread as general or not. Any change done
        manually must overrule the automatic filter.

        Not Implemented yet.
        '''
        pass

    def on_remark_changed(self, widget, *args):
        if self.in_progress:
            return

        start, end = self.remark.get_bounds()
        text = self.remark.get_text(start, end, False)

        model_detail, iter = self.selinfo.get_selected()
        thread_id = model_detail.get_value(iter, 0)

        self.threads[thread_id]['remark'] = text
        self.is_modified = True

    def on_window_delete(self, *args):
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
        """Handle global keystrokes"""

        # We handle Ctrl
        if event.state != 0 and (event.state & Gdk.ModifierType.CONTROL_MASK):
            if event.keyval == Gdk.KEY_s:
                self.save(self.ithread)
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

    def save(self, ithread, output_file=None):
        if not self.is_modified:
            return

        filename = output_file or self.csv_file
        utils.backup_file(filename)

        try:
            with open(filename, 'w') as fd:
                fieldnames = ['index', 'id', 'generic', '# participants',
                              '# messages', 'start', 'end', 'duration',
                              'email', 'category']
                writer = csv.DictWriter(fd, quoting=csv.QUOTE_MINIMAL,
                                        fieldnames=fieldnames)
                writer.writeheader()

                for key, d in ithread.iteritems():
                    o = dict(d)
                    o['id'] = key
                    # Remove fields that we don't want printed
                    o.pop('container', None)
                    o.pop('name', None)
                    try:
                        writer.writerow(o)
                    except csv.Error as e:
                        print('Error on writing %s:\n%s' % (key, e))

                self.is_modified = False
        except csv.Error as e:
            print('Error writing file: %s' % e)

    def main(self):
        self.window.show_all()
        Gtk.main()
