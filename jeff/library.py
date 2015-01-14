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

import datetime
import os
import sqlite3

import mutagen

from gi.repository import GLib

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

EXTENSIONS = ['flac', 'm4a', 'mp3', 'ogg', 'wav', 'wma']

#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class Track(object):
	def __init__(self, db, row):
		self._db = db
		self._id = row['id']
		self._select_file()

	@property
	def description(self):
		if self._tags and 'title' in self._tags:
				if 'artist' in self._tags:
					return '{} - {}'.format(self._tags['artist'][0], self._tags['title'][0])
				else:
					return 'Unknown Artist - {}'.format(self._tags['title'][0])
		else:
			return os.path.split(self._path)[1]

	@property
	def id(self):
		return self._id

	@property
	def path(self):
		return self._path

	@property
	def uri(self):
		return GLib.filename_to_uri(self._path, None)

	def _select_file(self):
		result = self._db.execute('SELECT * FROM files WHERE track_id = ? LIMIT 1;', (self._id,)).fetchone()
		self._path = result['path']
		self._tags = mutagen.File(self._path, easy=True)

class Library(object):
	def __init__(self, path):
		self._db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
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
		return [Track(self._db, row) for row in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY RANDOM() LIMIT ?;', (count,)).fetchall()]

	def remove_directory(self, path):
		path = os.path.abspath(path)

		self._db.execute('DELETE FROM directories WHERE path = ?;', (path,))
		self._db.commit()

	def scan_directories(self):
		self._add_new_files()
		self._remove_missing_files()

	def update_playing(self, track, losing_tracks):
		for losing_track in losing_tracks:
			if track.id < losing_track.id:
				first_track_id, second_track_id = track.id, losing_track.id
				score = 1
			else:
				first_track_id, second_track_id = losing_track.id, track.id
				score = -1

			try:
				self._db.execute('INSERT INTO pairs (first_track_id, second_track_id, score, last_update) VALUES (?, ?, ?, ?);', (first_track_id, second_track_id, score, datetime.datetime.now()))
			except sqlite3.Error as e:
				self._db.execute('UPDATE pairs SET score = score + ?, last_update = ? WHERE first_track_id = ? and second_track_id = ?;', (score, datetime.datetime.now(), first_track_id, second_track_id))

		self._db.commit()

	#---------------------------------------------------------------------------
	# Private Methods
	#---------------------------------------------------------------------------

	def _initialize_tables(self):
		self._db.execute('PRAGMA foreign_keys = ON;');

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS config (
				key TEXT PRIMARY KEY,
				value TEXT
			);
		''')

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
				track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
				path TEXT UNIQUE,
				last_update TIMESTAMP
			);
		''')

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS tracks (
				id INTEGER PRIMARY KEY,
				mbid TEXT UNIQUE
			);
		''')

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS pairs (
				first_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
				second_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
				score INTEGER,
				last_update TIMESTAMP,
				PRIMARY KEY(first_track_id, second_track_id)
			);
		''')

		self._update_tables()
		self._db.commit()

	def _update_tables(self):
		version = self._db.execute('SELECT * FROM config WHERE key = ?;', ('database_version',)).fetchone()

		if not version:
			version = 1
			self._db.execute('INSERT INTO config (key, value) VALUES (?, ?);', ('database_version', version))

	def _add_file(self, directory_id, path):
		tags = mutagen.File(path, easy=True)

		if tags and 'musicbrainz_trackid' in tags:
			mbid = tags['musicbrainz_trackid'][0]
			result = self._db.execute('SELECT * FROM tracks WHERE mbid = ?;', (mbid,)).fetchone()

			if result:
				track_id = result['id']
			else:
				track_id = self._db.execute('INSERT INTO tracks (mbid) VALUES (?);', (mbid,)).lastrowid
		else:
			track_id = self._db.execute('INSERT INTO tracks (mbid) VALUES (?);', (None,)).lastrowid

		self._db.execute('INSERT INTO files (directory_id, track_id, path, last_update) VALUES (?, ?, ?, ?);', (directory_id, track_id, path, datetime.datetime.utcnow()))

	def _update_file(self, row):
		track = self._db.execute('SELECT * FROM tracks WHERE id = ?;', (row['track_id'],)).fetchone()
		tags = mutagen.File(row['path'], easy=True)

		if tags and 'musicbrainz_trackid' in tags:
			mbid = tags['musicbrainz_trackid'][0]
		else:
			mbid = None

		if mbid != track['mbid']:
			# The mbid has changed since the last time we read the file, so we
			# need to update the database. First, we need to determine whether
			# or not the new mbid already exists, and determine our new track
			# id.
			result = self._db.execute('SELECT * FROM tracks WHERE mbid = ?;', (mbid,)).fetchone() if mbid else None

			if result:
				new_track_id = result['id']
			else:
				new_track_id = self._db.execute('INSERT INTO tracks (mbid) VALUES (?);', (mbid,)).lastrowid

			delete = False

			# Now, there are three possibilities:
			#  1) The mbid was previously NULL, but now has a defined value. In
			#     this case, we want to merge our statistics onto the new track.
			#  2) The mbid was previously defined, but is now NULL. This seems
			#     like a regression in the tags, but it could happen. In this
			#     case, it's probably best to just create a new track and be
			#     done with it.
			#  3) The mbid was previously defined, but has changed. The most
			#     likely case here is that recordings were merged on
			#     Musicbrainz, so it's probably best to move the data, as long
			#     as the old track has no remaining files.
			if mbid:
				result = self._db.execute('SELECT COUNT(*) AS count FROM files WHERE track_id = ? AND id != ?;', (track['id'], row['id'])).fetchone()

				if result['count'] == 0:
					# Update any data that uses the old track id to use the new
					# track id.
					self._db.execute('UPDATE pairs SET first_track_id = ? WHERE first_track_id = ?;', (new_track_id, row['track_id']))
					self._db.execute('UPDATE pairs SET second_track_id = ? WHERE second_track_id = ?;', (new_track_id, row['track_id']))

					# Flag the previous track for deletion.
					delete = True

			self._db.execute('UPDATE files SET track_id = ? WHERE id = ?;', (new_track_id, row['id']))

			if delete:
				self._db.execute('DELETE FROM tracks WHERE id = ?;', (track['id'],))

	def _add_new_files(self):
		for directory in self._db.execute('SELECT * FROM directories;'):
			for root, dirs, files in os.walk(directory['path']):
				for path in sorted(files):
					if path.split('.')[-1].lower() in EXTENSIONS:
						result = self._db.execute('SELECT * FROM files WHERE path = ?;', (os.path.join(root, path),)).fetchone()

						if not result:
							self._add_file(directory['id'], os.path.join(root, path))
						elif result['last_update'] < datetime.datetime.utcfromtimestamp(os.path.getmtime(os.path.join(root, path))):
							self._update_file(result)

		self._db.commit()

	def _remove_missing_files(self):
		for row in self._db.execute('SELECT * FROM files;').fetchall():
			if not os.path.exists(row['path']):
				track = self._db.execute('SELECT * FROM tracks WHERE id = ?;', (row['track_id'],)).fetchone()

				if track['mbid']:
					self._db.execute('DELETE FROM files WHERE id = ?;', (row['id'],))
				else:
					self._db.execute('DELETE FROM tracks WHERE id = ?;', (track['id'],))

		self._db.commit()
