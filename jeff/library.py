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
import math
import os
import random
import sqlite3
import time

import mutagen

from gi.repository import GLib

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

EXTENSIONS = ['flac', 'm4a', 'mp3', 'ogg', 'wav', 'wma']

base_time = time.time()


def print_debug(function, msg):
	print('DEBUG: {:>20} {:12.3f} {}'.format(function, time.time() - base_time, msg))

def update_rating(score, rating, deviation, opponent_rating, opponent_deviation):
	q = math.log(10) / 400
	g = 1 / math.sqrt(1 + 3 * (q ** 2) * (opponent_deviation ** 2) / (math.pi ** 2))
	e = 1 / (1 + 10 ** (-1 * g * (rating - opponent_rating) / 400))
	d = ((q ** 2) * (g ** 2) * (e * (1 - e))) ** -1

	r = rating + (q / (1 / (deviation ** 2) + 1 / d)) * g * (score - e)
	rd = math.sqrt(((1 / (deviation ** 2)) + (1 / d)) ** -1)

	return (r, rd)


#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class Track(object):
	def __init__(self, db, row):
		self._db = db
		self._id = row['id']
		self._mbid = row['mbid']
		self._rating = row['rating']
		self._select_file()

	@property
	def description(self):
		if self.tags and 'title' in self.tags:
				if 'artist' in self.tags:
					if 'album' in self.tags:
						return '{} - {} ({}) [{:0.3f}]'.format(self.tags['artist'][0], self.tags['title'][0], self.tags['album'][0], self.rating)
					else:
						return '{} - {} [{:0.3f}]'.format(self.tags['artist'][0], self.tags['title'][0], self.rating)
				else:
					return 'Unknown Artist - {} [{:0.3f}]'.format(self.tags['title'][0], self.rating)
		else:
			return os.path.split(self._path)[1]

	@property
	def title(self):
		if self.tags and 'title' in self.tags:
			return self.tags['title'][0]
		else:
			return os.path.split(self._path)[1]

	@property
	def id(self):
		return self._id

	@property
	def mbid(self):
		return self._mbid

	@property
	def rating(self):
		return self._rating

	@property
	def path(self):
		return self._path

	@property
	def tags(self):
		if not self._tags:
			self._tags = mutagen.File(self._path, easy=True)

		return self._tags

	@property
	def uri(self):
		return GLib.filename_to_uri(self._path, None)

	def __hash__(self):
		return hash(self._id)

	def _select_file(self):
		result = self._db.execute('SELECT * FROM files WHERE track_id = ? LIMIT 1;', (self._id,)).fetchone()
		self._path = result['path']
		self._tags = None


class Library(object):
	def __init__(self, path):
		self._db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
		self._db.row_factory = sqlite3.Row

		self._tracks = None

		self._initialize_db()

	#---------------------------------------------------------------------------
	# Properties
	#---------------------------------------------------------------------------

	@property
	def tracks(self):
		#if not self._tracks:
		#self._tracks = {x['id']: Track(self._db, x) for x in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY t.id;')}

		return {x['id']: Track(self._db, x) for x in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY t.id;')}

		#return self._tracks

	def get_error(self, ratings, scores):
		error = 0.0
		count = 1

		for (a, b), score in scores.items():
			if ratings[a] == 1.0 and ratings[b] == 1.0:
				predicted = 0.5
			elif ratings[a] == 0.0 and ratings[b] == 0.0:
				predicted = 0.5
			else:
				predicted = (ratings[a] - (ratings[a] * ratings[b])) / (ratings[a] + ratings[b] - 2 * ratings[a] * ratings[b])
			error += (score - predicted) ** 2
			count += 1

		return error ** (1 / count)

	@property
	def ranked_tracks_asm(self):
		base_data = {}
		data = {}
		scores = {x: 0.0 for x in self.tracks}

		for row in self._db.execute('SELECT * FROM comparisons ORDER BY timestamp ASC'):
			first = row['first_track_id']
			second = row['second_track_id']
			score = row['score']

			if first not in data:
				data[first] = {}
				base_data[first] = {'for': 0, 'against': 0, 'count': 0}

			if second not in data:
				data[second] = {}
				base_data[second] = {'for': 0, 'against': 0, 'count': 0}

			if second not in data[first]:
				data[first][second] = {'for': 0, 'against': 0, 'count': 0}

			if first not in data[second]:
				data[second][first] = {'for': 0, 'against': 0, 'count': 0}

			data[first][second]['for'] += score
			data[second][first]['for'] += 1 - score

			data[first][second]['against'] += 1 - score
			data[second][first]['for'] += score

			data[first][second]['count'] += 1
			data[second][first]['count'] += 1

			base_data[first]['for'] += score
			base_data[first]['against'] += 1 - score
			base_data[first]['count'] += 1
			base_data[second]['for'] += 1 - score
			base_data[second]['against'] += score
			base_data[second]['count'] += 1

		asm_data = {}

		for row in self._db.execute('SELECT * FROM comparisons ORDER BY timestamp ASC'):
			first = row['first_track_id']
			second = row['second_track_id']
			score = row['score']

			if first not in asm_data:
				asm_data[first] = {'for': 0, 'against': 0}

			if second not in asm_data:
				asm_data[second] = {'for': 0, 'against': 0}

			if base_data[first]['count'] == data[first][second]['count']:
				continue

			if base_data[second]['count'] == data[second][first]['count']:
				continue

			first_against = (base_data[first]['against'] - data[first][second]['against']) / (base_data[first]['count'] - data[first][second]['count'])
			second_against = (base_data[second]['against'] - data[second][first]['against']) / (base_data[second]['count'] - data[second][first]['count'])

			asm_data[first]['for'] += score - second_against
			asm_data[second]['for'] += (1 - score) - first_against

		for id in asm_data:
			scores[id] = asm_data[id]['for'] / base_data[id]['count']

		tracks = self.tracks

		return [(x[1], tracks[x[0]]) for x in sorted(scores.items(), key=lambda x: x[1], reverse=True)]

	@property
	def ranked_tracks_best_fit(self):
		scores = {}
		ratings = {}

		for row in self._db.execute('SELECT * FROM comparisons ORDER BY timestamp ASC'):
			key = row['first_track_id'], row['second_track_id']

			if key not in scores:
				scores[key] = 0.5 * 0.9 + row['score'] * 0.1
				ratings[row['first_track_id']] = 0.5
				ratings[row['second_track_id']] = 0.5
			else:
				scores[key] = scores[key] * 0.9 + row['score'] * 0.1

		tracks = self.tracks

		error = self.get_error(ratings, scores)
		old_error = None

		while error > 0.1 and (not old_error or old_error != error):
			old_error = error
			for track in ratings:
				base = 0.0

				for divisor in [10, 100, 1000]:
					best = (None, None)
					second = (None, None)

					for i in range(11):
						ratings[track] = base + i / divisor
						new_error = self.get_error(ratings, scores)

						if not best[0] or new_error < best[0]:
							second = best
							best = (new_error, i)
						elif not second[0] or new_error < second[0]:
							second = (new_error, i)

					base += min(best[1], second[1]) / divisor

				ratings[track] = base

		return [(x[1], tracks[x[0]]) for x in sorted(ratings.items(), key=lambda x: x[1], reverse=True)]

	@property
	def ranked_tracks(self):
		return list(sorted(self.tracks.values(), key=lambda x: x.rating, reverse=True))

	#---------------------------------------------------------------------------
	# Public Methods
	#---------------------------------------------------------------------------

	def add_directory(self, path):
		path = os.path.abspath(path)

		if os.path.exists(path):
			try:
				self._db.execute('INSERT INTO directories (path) VALUES (?);', (path,))
			except sqlite3.IntegrityError:
				return

			self._db.commit()

	def remove_directory(self, path):
		path = os.path.abspath(path)

		self._db.execute('DELETE FROM directories WHERE path = ?;', (path,))
		self._db.commit()

	def scan_directories(self):
		self._add_new_files()
		self._remove_missing_files()
		self._tracks = None

	def get_next_tracks(self):
		# TODO: Add support for other selection algorithms. True random at least.
		count = self._db.execute('SELECT COUNT(*) AS count FROM tracks').fetchone()['count']

		if count >= 2:
			first = Track(self._db, self._db.execute('SELECT * FROM tracks WHERE comparisons = (SELECT MIN(comparisons) FROM tracks) ORDER BY RANDOM() LIMIT 1;').fetchone())
			second = Track(self._db, self._db.execute('SELECT * FROM tracks WHERE id != ? ORDER BY RANDOM() LIMIT 1;', (first.id,)).fetchone())

			return [first, second]
		else:
			return []

	def update_playing(self, track, losing_tracks):
		for losing_track in losing_tracks:
			if track.id < losing_track.id:
				first_track_id, second_track_id = track.id, losing_track.id
				first_track_score = 1.0
				second_track_score = 0.0
			else:
				first_track_id, second_track_id = losing_track.id, track.id
				first_track_score = 0.0
				second_track_score = 1.0

			self._db.execute('INSERT INTO comparisons (first_track_id, second_track_id, score, timestamp) VALUES (?, ?, ?, ?);', (first_track_id, second_track_id, first_track_score, datetime.datetime.now()))

			first_track = self._db.execute('SELECT * FROM tracks WHERE id = ?;', (first_track_id,)).fetchone()
			second_track = self._db.execute('SELECT * FROM tracks WHERE id = ?;', (second_track_id,)).fetchone()

			first_since = (datetime.datetime.now() - first_track['last_update']).days if first_track['last_update'] else 364
			second_since = (datetime.datetime.now() - second_track['last_update']).days if second_track['last_update'] else 364

			first_deviation = min(math.sqrt(first_track['deviation'] ** 2 + (18.15682598 ** 2) * first_since), 350)
			second_deviation = min(math.sqrt(second_track['deviation'] ** 2 + (18.15682598 ** 2) * second_since), 350)

			first_new_rating, first_new_deviation = update_rating(first_track_score, first_track['rating'], first_deviation, second_track['rating'], second_deviation)
			second_new_rating, second_new_deviation = update_rating(second_track_score, second_track['rating'], second_deviation, first_track['rating'], first_deviation)

			self._db.execute('UPDATE tracks SET comparisons = comparisons + 1, rating = ?, deviation = ?, last_update = ? WHERE id = ?', (first_new_rating, first_new_deviation, datetime.datetime.now(), first_track['id']))
			self._db.execute('UPDATE tracks SET comparisons = comparisons + 1, rating = ?, deviation = ?, last_update = ? WHERE id = ?', (second_new_rating, second_new_deviation, datetime.datetime.now(), second_track['id']))

		self._db.commit()

	#---------------------------------------------------------------------------
	# Private Methods
	#---------------------------------------------------------------------------

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

	def _initialize_db(self):
		self._db.execute('PRAGMA foreign_keys = ON;')

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
				mbid TEXT UNIQUE,
				comparisons INTEGER DEFAULT 0,
				rating REAL DEFAULT 1500,
				deviation REAL DEFAULT 350,
				last_update TIMESTAMP
			);
		''')

		self._db.execute('''
			CREATE TABLE IF NOT EXISTS comparisons (
				id INTEGER PRIMARY KEY,
				first_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
				second_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
				score REAL,
				timestamp TIMESTAMP
			);
		''')

		self._update_tables()
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

	def _update_file(self, row):
		track = self._db.execute('SELECT * FROM tracks WHERE id = ?;', (row['track_id'],)).fetchone()
		tags = mutagen.File(row['path'], easy=True)

		if tags and 'musicbrainz_trackid' in tags:
			mbid = tags['musicbrainz_trackid'][0]
		else:
			mbid = None

		if mbid != track['mbid']:
			print_debug('_update_file', 'Musicbrainz ID for {} has changed'.format(row['path']))

			# Determine if the current track has files other than this one.
			files_left = self._db.execute('SELECT COUNT(*) AS count FROM files WHERE track_id = ? AND id != ?;', (track['id'], row['id'])).fetchone()['count'] > 0

			# Determine if the new MBID already exists in the database.
			new_track = self._db.execute('SELECT * FROM tracks WHERE mbid = ?;', (mbid,)).fetchone() if mbid else None

			if not files_left and not new_track:
				print_debug('_update_file', 'Updating MBID on existing track')
				self._db.execute('UPDATE tracks SET mbid = ? WHERE id = ?', (mbid, track['id']))
			elif not files_left and new_track:
				if track['comparisons'] > new_track['comparisons']:
					print_debug('_update_file', 'Deleting new track and transferring its files to old track.')
					self._db.execute('UPDATE files SET track_id = ? WHERE track_id = ?;', (track['id'], new_track['id']))
					self._db.execute('DELETE FROM tracks WHERE id = ?;', (new_track['id'],))
					self._db.execute('UPDATE tracks SET mbid = ? WHERE id = ?', (mbid, track['id']))
				else:
					print_debug('_update_file', 'Deleting old track and its data. New track has better data.')
					self._db.execute('DELETE FROM tracks WHERE id = ?;', (track['id'],))
			else:
				print_debug('_update_file', 'Files remain on old track. New track will start with fresh data.')

			self._db.commit()

	def _update_tables(self):
		version = self._db.execute('SELECT * FROM config WHERE key = ?;', ('database_version',)).fetchone()

		if not version:
			version = 2
			self._db.execute('INSERT INTO config (key, value) VALUES (?, ?);', ('database_version', version))

		if version == 1:
			version = 2
			self._db.execute('ALTER TABLE tracks ADD comparisons INTEGER DEFAULT 0;')
			self._db.execute('ALTER TABLE tracks ADD rating REAL DEFAULT 1500;')
			self._db.execute('ALTER TABLE tracks ADD deviation REAL DEFAULT 350;')
			self._db.execute('ALTER TABLE tracks ADD last_update TIMESTAMP;')
			self._db.execute('DROP TABLE pairs;')
			self._db.execute('UPDATE config SET value = ? WHERE key = ?;', (version, 'database_version'))
