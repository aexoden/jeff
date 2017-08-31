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

import bisect
import copy
import datetime
import os
import random
import sqlite3
import time

from collections import deque
from heapq import merge

import mutagen

from gi.repository import GLib

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

EXTENSIONS = ['flac', 'm4a', 'mp3', 'ogg', 'wav', 'wma']

base = time.time()


def dprint(msg):
    print('DEBUG: {:12.3f} {}'.format(time.time() - base, msg))


#-------------------------------------------------------------------------------
# Functions
#-------------------------------------------------------------------------------

def merge_sort(m):
    if len(m) <= 1:
        return m

    middle = len(m) // 2
    left = m[:middle]
    right = m[middle:]

    left = merge_sort(left)
    right = merge_sort(right)
    return list(merge(left, right))


def insertion_sort(m):
    for i in range(1, len(m)):
        bisect.insort(m, m.pop(i), 0, i)


#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class SortError(BaseException):
    def __init__(self, x, y):
        self.x = x
        self.y = y


class DirectedAcyclicGraph(object):
    def __init__(self):
        self._graph = {}

    #---------------------------------------------------------------------------
    # Public Methods
    #---------------------------------------------------------------------------

    def add_edge(self, first_id, second_id, score):
        if score > 0.5:
            winning_id, losing_id = first_id, second_id
        elif score < 0.5:
            winning_id, losing_id = second_id, first_id
        else:
            return False

        if not self.has_path(winning_id, losing_id):
            if losing_id not in self._graph:
                self._graph[losing_id] = set()

            self._graph[losing_id].add(winning_id)

            return True

        return False

    def add_vertex(self, vertex_id):
        if vertex_id not in self._graph:
            self._graph[vertex_id] = set()

    def topological_sort(self):
        graph = copy.deepcopy(self._graph)

        for key in set().union(*graph.values()) - set(graph.keys()):
            graph[key] = set()

        while True:
            leaders = set(
                item
                for item, dependencies in graph.items()
                if not dependencies
            )

            if not leaders:
                break

            yield leaders

            graph = {
                item: (dependencies - leaders)
                for item, dependencies in graph.items()
                if item not in leaders
            }

        if graph:
            print('Cycles: {}'.format(', '.join(repr(x) for x in graph.items())))

    def has_path(self, first_id, second_id):
        q = deque()
        q.append(first_id)
        discovered = set([first_id])

        while len(q) > 0:
            element = q.popleft()

            for target in self._graph[element]:
                if target == second_id:
                    return True

                if target not in discovered:
                    q.append(target)
                    discovered.add(target)

        return False

    def __len__(self):
        return len(self._graph)


class Track(object):
    def __init__(self, db, row, graph=None):
        self._db = db
        self._id = row['id']
        self._graph = graph
        self._select_file()

    @property
    def description(self):
        if self.tags and 'title' in self.tags:
                if 'artist' in self.tags:
                    if 'album' in self.tags:
                        return '{} - {} ({})'.format(self.tags['artist'][0], self.tags['title'][0], self.tags['album'][0])
                    else:
                        return '{} - {}'.format(self.tags['artist'][0], self.tags['title'][0])
                else:
                    return 'Unknown Artist - {}'.format(self.tags['title'][0])
        else:
            return os.path.split(self._path)[1]

    @property
    def id(self):
        return self._id

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

    def __lt__(self, other):
        if self._graph.has_path(other._id, self._id):
            return True
        elif self._graph.has_path(self._id, other._id):
            return False
        else:
            dprint('   Sort Error')
            raise SortError(self, other)

    def __le__(self, other):
        self._unimplemented(other)

    def __eq__(self, other):
        return self._id == other._id

    def __ne__(self, other):
        return not (self == other)

    def __gt__(self, other):
        self._unimplemented(other)

    def __ge__(self, other):
        self._unimplemented(other)

    def _unimplemented(self, other):
        raise NotImplemented()

    def _select_file(self):
        result = self._db.execute('SELECT * FROM files WHERE track_id = ? LIMIT 1;', (self._id,)).fetchone()
        self._path = result['path']
        self._tags = None


class Library(object):
    def __init__(self, path):
        self._db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._db.row_factory = sqlite3.Row

        self._initialize_tables()
        self._graph = None

        self._current = set()
        self._dirty = True
        self._clean_count = 0
        self._random_count = 0
        self._random_list = None

    #---------------------------------------------------------------------------
    # Properties
    #---------------------------------------------------------------------------

    @property
    def graph(self):
        if not self._graph:
            self._initialize_graph()

        return self._graph

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

    def get_ranked_tracks(self, full_graph=False):
        return self.graph if full_graph else self.graph.topological_sort()

    def get_next_tracks(self, true_random=True):
        dprint('get_next_tracks({})'.format(true_random))

        if true_random or (not self._dirty and self._clean_count < 10):
            #self._clean_count += 1
            return [Track(self._db, row) for row in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY RANDOM() LIMIT 2;').fetchall()]

            if self._random_count > 10 or not self._random_list:
                graph = self.get_ranked_tracks(True)
                ts = graph.topological_sort()
                self._random_list = []
                self._random_count = 0

                if len(graph) == 0:
                    return []

                tracks = {x['id']: x for x in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY t.id;')}

                for group in ts:
                    for entry in group:
                        self._random_list.append(Track(self._db, tracks[entry], graph))

            first = random.randint(0, len(self._random_list) - 300)
            second = first + random.randint(1, 299)

            self._random_count += 1

            print(self._random_count, first, second)

            return [self._random_list[first], self._random_list[second]]
        else:
            try:
                if len(self._current) == 0:
                    dprint('Generating graph')
                    graph = self.get_ranked_tracks(True)
                    dprint('Getting topological sort')
                    ts = graph.topological_sort()

                    if len(graph) == 0:
                        return []

                    dprint('Executing query')
                    tracks = {x['id']: x for x in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY t.id;')}

                    dprint('Building current')
                    for group in ts:
                        if len(group) > 1:
                            for entry in group:
                                if len(self._current) < 20:
                                    self._current.add(Track(self._db, tracks[entry], graph))

                    if len(self._current) == 0:
                        if len(tracks) == 0:
                            return []
                        else:
                            self._dirty = False
                            self._clean_count = 0
                            return self.get_next_tracks(True)

                    self._current.update([Track(self._db, x, graph) for x in random.sample(list(tracks.values()), max(5, min(50 - len(self._current), min(100, len(tracks)))))])

                random.sample(sorted(self._current), 2)

                self._current = set()
                return self.get_next_tracks(False)
            except SortError as e:
                return [e.x, e.y]

    def remove_directory(self, path):
        path = os.path.abspath(path)

        self._db.execute('DELETE FROM directories WHERE path = ?;', (path,))
        self._db.commit()

    def scan_directories(self):
        self._add_new_files()
        self._remove_missing_files()
        self._dirty = True
        self._current = set()
        self._graph = None

    def update_playing(self, track, losing_tracks):
        for losing_track in losing_tracks:
            if track.id < losing_track.id:
                first_track_id, second_track_id = track.id, losing_track.id
                score = 0.1
            else:
                first_track_id, second_track_id = losing_track.id, track.id
                score = 0

            try:
                self._db.execute('INSERT INTO pairs (first_track_id, second_track_id, score, count, last_update) VALUES (?, ?, ?, ?, ?);', (first_track_id, second_track_id, (0.5 * 0.9) + score, 1, datetime.datetime.now()))
                if not self.graph.add_edge(first_track_id, second_track_id, (0.5 * 0.9) + score):
                    self._graph = None
            except sqlite3.Error:
                self._db.execute('UPDATE pairs SET score = (score * 0.9) + ?, count = count + 1, last_update = ? WHERE first_track_id = ? and second_track_id = ?;', (score, datetime.datetime.now(), first_track_id, second_track_id))

        self._db.commit()
        self._dirty = True

    #---------------------------------------------------------------------------
    # Private Methods
    #---------------------------------------------------------------------------

    def _initialize_graph(self):
        self._graph = DirectedAcyclicGraph()

        for row in self._db.execute('SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0'):
            self._graph.add_vertex(row['id'])

        for pair in self._db.execute('SELECT p.* FROM pairs p, files f1, files f2 WHERE p.first_track_id = f1.track_id AND p.second_track_id = f2.track_id GROUP BY f1.track_id, f2.track_id ORDER BY score DESC, p.last_update DESC;').fetchall():
            self._graph.add_edge(pair['first_track_id'], pair['second_track_id'], pair['score'])

    def _initialize_tables(self):
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
                mbid TEXT UNIQUE
            );
        ''')

        self._db.execute('''
            CREATE TABLE IF NOT EXISTS pairs (
                first_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
                second_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
                score REAL,
                count INTEGER,
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
                    # TODO: Pairs need to be merged, not merely modified.
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
