#!/usr/bin/env python
#-------------------------------------------------------------------------------
#  Copyright (c) 2015 Jason Lynch <jason@calindora.com>
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#-------------------------------------------------------------------------------

import os
import sqlite3

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

EXTENSIONS = ['flac', 'm4a', 'mp3', 'ogg', 'wav', 'wma']

#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class Library(object):
	def __init__(self, path):
		self._db = sqlite3.connect(path)
		self._db.row_factory = sqlite3.Row

		self._initialize_tables()

	#---------------------------------------------------------------------------
	# Public Methods
	#---------------------------------------------------------------------------

	def add_directory(self, path):
		path = os.path.abspath(path)

		if os.path.exists(path):
			try:
				self._db.execute('INSERT INTO directories (path) VALUES (?);', (path,))
			except sqlite3.IntegrityError as e:
				return

			self._db.commit()

	def get_next_tracks(self, count):
		return self._db.execute('SELECT * FROM files ORDER BY RANDOM() LIMIT ?;', (count,)).fetchall()

	def remove_directory(self, path):
		path = os.path.abspath(path)

		self._db.execute('DELETE FROM directories WHERE path = ?;', (path,))
		self._db.commit()

	def scan_directories(self):
		self._add_new_files()

	#---------------------------------------------------------------------------
	# Private Methods
	#---------------------------------------------------------------------------

	def _initialize_tables(self):
		self._db.execute('PRAGMA foreign_keys = ON;');

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS directories (
				id INTEGER PRIMARY KEY,
				path TEXT UNIQUE
			);
		''')

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS files (
				id INTEGER PRIMARY KEY,
				directory_id INTEGER REFERENCES directories(id) ON UPDATE CASCADE ON DELETE CASCADE,
				path TEXT UNIQUE
			);
		''')

	def _add_new_files(self):
		for directory in self._db.execute('SELECT * FROM directories;'):
			for root, dirs, files in os.walk(directory['path']):
				for path in sorted(files):
					if path.split('.')[-1].lower() in EXTENSIONS:
						try:
							self._db.execute('INSERT INTO files (directory_id, path) VALUES (?, ?);', (directory['id'], os.path.join(root, path)))
						except sqlite3.IntegrityError as e:
							continue

		self._db.commit()
