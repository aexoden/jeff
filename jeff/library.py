# SPDX-FileCopyrightText: 2015-present Jason Lynch <jason@aexoden.com>
#
# SPDX-License-Identifier: MIT
"""Library for managing music tracks and their metadata."""

import datetime
import math
import os
import sqlite3
import time

from pathlib import Path

import choix

from gi.repository import GLib
from tinytag import TinyTag

#
# Constants
#

EXTENSIONS = ["flac", "m4a", "mp3", "ogg", "wav", "wma"]

base_time = time.time()


def print_debug(function: str, msg: str) -> None:
    """Print debug messages with a timestamp."""
    print(f"DEBUG: {function:>20} {time.time() - base_time:12.3f} {msg}")


def update_rating(
    score: float, rating: float, deviation: float, opponent_rating: float, opponent_deviation: float
) -> tuple[float, float]:
    """Update the rating and deviation based on the Elo rating system."""
    q = math.log(10) / 400
    g = 1 / math.sqrt(1 + 3 * (q**2) * (opponent_deviation**2) / (math.pi**2))
    e = 1 / (1 + 10 ** (-1 * g * (rating - opponent_rating) / 400))
    d = ((q**2) * (g**2) * (e * (1 - e))) ** -1

    r = rating + (q / (1 / (deviation**2) + 1 / d)) * g * (score - e)
    rd = math.sqrt(((1 / (deviation**2)) + (1 / d)) ** -1)

    return (r, rd)


#
# Classes
#


class Track:
    """Class representing a music track in the library."""

    def __init__(self, db: sqlite3.Connection, row: sqlite3.Row) -> None:
        """Initialize a Track instance with database connection and row data."""
        self._db = db
        self._id = row["id"]
        self._mbid = row["mbid"]
        self._rating = row["rating"]
        self._comparisons = row["comparisons"]
        self._select_file()

    @property
    def description(self) -> str:
        """Return a description of the track, including artist, title, album, comparisons, and rating."""
        if self.tags and self.tags.title:
            if self.tags.artist:
                if self.tags.album:
                    return f"{self.tags.artist} - {self.tags.title} ({self.tags.album}) [{self.comparisons}/{self.rating:0.3f}]"
                return f"{self.tags.artist} - {self.tags.title} [{self.comparisons}/{self.rating:0.3f}]"
            return f"Unknown Artist - {self.tags.title} [{self.comparisons}/{self.rating:0.3f}]"

        if self._path:
            return self._path.stem

        return "Unknown Track"

    @property
    def title(self) -> str:
        """Return the title of the track."""
        if self.tags and self.tags.title:
            return self.tags.title

        if self._path:
            return self._path.stem

        return "Unknown Title"

    @property
    def id(self) -> int:
        """Return the unique identifier for the track."""
        return self._id

    @property
    def mbid(self) -> str:
        """Return the MusicBrainz ID for the track, if available."""
        return self._mbid

    @property
    def rating(self) -> float:
        """Return the rating of the track."""
        result = self._db.execute("SELECT rating FROM tracks where id = ?;", (self._id,)).fetchone()
        return result["rating"]

    @property
    def comparisons(self) -> int:
        """Return the number of comparisons made for the track."""
        result = self._db.execute("SELECT comparisons FROM tracks where id = ?;", (self._id,)).fetchone()
        return result["comparisons"]

    @property
    def path(self) -> Path | None:
        """Return the file path of the track."""
        return self._path

    @property
    def tags(self) -> TinyTag:
        if not self._tags:
            print(self._id, self._path)
            self._tags = TinyTag.get(str(self._path))

        return self._tags

    @property
    def uri(self) -> str:
        """Return the URI of the track file."""
        if not self._path:
            return ""

        return GLib.filename_to_uri(str(self._path), None)

    def __hash__(self) -> int:
        """Return a hash of the track based on its ID.

        Returns:
            int: Hash value of the track ID.

        """
        return hash(self._id)

    def _select_file(self) -> None:
        result = self._db.execute(
            "SELECT * FROM files WHERE track_id = ? ORDER BY priority DESC LIMIT 1;", (self._id,)
        ).fetchone()

        if result:
            self._path = Path(result["path"])
        else:
            self._path = None

        self._tags = None


class Library:
    """Class representing a music library, managing tracks and their metadata."""

    def __init__(self, path: Path):
        """Initialize the Library with a database connection."""
        self._db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._db.row_factory = sqlite3.Row

        self._tracks = None
        self._scanning = False

        self._initialize_db()

    #
    # Properties
    #

    @property
    def tracks(self) -> dict[int, Track]:
        """Return a dictionary of all tracks in the library."""
        return {
            x["id"]: Track(self._db, x)
            for x in self._db.execute(
                "SELECT * FROM tracks t, files f WHERE t.id = f.track_id GROUP BY t.id HAVING COUNT(t.id) > 0 ORDER BY t.id;"
            )
        }

    def get_error(self, ratings: dict[int, float], scores: dict[tuple[int, int], float]) -> float:
        """Calculate the error between predicted and actual scores."""
        error = 0.0
        count = 1

        for (a, b), score in scores.items():
            if (ratings[a] == 1.0 and ratings[b] == 1.0) or (ratings[a] == 0.0 and ratings[b] == 0.0):
                predicted = 0.5
            else:
                predicted = (ratings[a] - (ratings[a] * ratings[b])) / (
                    ratings[a] + ratings[b] - 2 * ratings[a] * ratings[b]
                )
            error += (score - predicted) ** 2
            count += 1

        return error ** (1 / count)

    @property
    def ranked_tracks_asm(self):
        """Return tracks ranked by the ASM algorithm."""
        base_data = {}
        data = {}
        scores = {x: 0.0 for x in self.tracks}

        for row in self._db.execute("SELECT * FROM comparisons ORDER BY timestamp ASC"):
            first = row["first_track_id"]
            second = row["second_track_id"]
            score = row["score"]

            if first not in data:
                data[first] = {}
                base_data[first] = {"for": 0, "against": 0, "count": 0}

            if second not in data:
                data[second] = {}
                base_data[second] = {"for": 0, "against": 0, "count": 0}

            if second not in data[first]:
                data[first][second] = {"for": 0, "against": 0, "count": 0}

            if first not in data[second]:
                data[second][first] = {"for": 0, "against": 0, "count": 0}

            data[first][second]["for"] += score
            data[second][first]["for"] += 1 - score

            data[first][second]["against"] += 1 - score
            data[second][first]["for"] += score

            data[first][second]["count"] += 1
            data[second][first]["count"] += 1

            base_data[first]["for"] += score
            base_data[first]["against"] += 1 - score
            base_data[first]["count"] += 1
            base_data[second]["for"] += 1 - score
            base_data[second]["against"] += score
            base_data[second]["count"] += 1

        asm_data = {}

        for row in self._db.execute("SELECT * FROM comparisons ORDER BY timestamp ASC"):
            first = row["first_track_id"]
            second = row["second_track_id"]
            score = row["score"]

            if first not in asm_data:
                asm_data[first] = {"for": 0, "against": 0}

            if second not in asm_data:
                asm_data[second] = {"for": 0, "against": 0}

            if base_data[first]["count"] == data[first][second]["count"]:
                continue

            if base_data[second]["count"] == data[second][first]["count"]:
                continue

            first_against = (base_data[first]["against"] - data[first][second]["against"]) / (
                base_data[first]["count"] - data[first][second]["count"]
            )
            second_against = (base_data[second]["against"] - data[second][first]["against"]) / (
                base_data[second]["count"] - data[second][first]["count"]
            )

            asm_data[first]["for"] += score - second_against
            asm_data[second]["for"] += (1 - score) - first_against

        for id in asm_data:
            scores[id] = asm_data[id]["for"] / base_data[id]["count"]

        tracks = self.tracks

        return [(x[1], tracks[x[0]]) for x in sorted(scores.items(), key=lambda x: x[1], reverse=True)]

    @property
    def ranked_tracks_bt(self):
        tracks = self.tracks
        data = []

        for row in self._db.execute("SELECT * FROM comparisons ORDER BY timestamp ASC"):
            if row["score"] > 0:
                data.append((row["first_track_id"], row["second_track_id"]))
            else:
                data.append((row["second_track_id"], row["first_track_id"]))

        params = choix.ilsr_pairwise(max(tracks.keys()) + 1, data, alpha=0.0001)
        return [(params[x[0]], x[1]) for x in sorted(tracks.items(), key=lambda x: params[x[0]], reverse=True)]

    @property
    def ranked_tracks_elo(self):
        tracks = self.tracks
        ratings = {x: 1500.0 for x in tracks.keys()}

        iterations = 0
        delta = None

        while iterations < 10000 and (delta is None or delta > 0.01):
            expected = {x: 0 for x in tracks.keys()}
            actual = {x: 0 for x in tracks.keys()}

            for row in self._db.execute("SELECT * FROM comparisons ORDER BY timestamp ASC"):
                track_a, track_b = row["first_track_id"], row["second_track_id"]

                q_a = pow(10, ratings[track_a] / 400)
                q_b = pow(10, ratings[track_b] / 400)

                e_a = q_a / (q_a + q_b)
                e_b = q_b / (q_a + q_b)

                expected[track_a] += e_a
                expected[track_b] += e_b

                actual[track_a] += row["score"]
                actual[track_b] += 1 - row["score"]

            delta = 0

            for id in tracks.keys():
                adjustment = 32 * (actual[id] - expected[id])
                ratings[id] += adjustment

                delta += abs(adjustment)

            iterations += 1

            print(iterations, delta)

        return [(x[1], tracks[x[0]]) for x in sorted(ratings.items(), key=lambda x: x[1], reverse=True)]

    @property
    def ranked_tracks_best_fit(self):
        scores = {}
        ratings = {}

        for row in self._db.execute("SELECT * FROM comparisons ORDER BY timestamp ASC"):
            key = row["first_track_id"], row["second_track_id"]

            if key not in scores:
                scores[key] = 0.5 * 0.9 + row["score"] * 0.1
                ratings[row["first_track_id"]] = 0.5
                ratings[row["second_track_id"]] = 0.5
            else:
                scores[key] = scores[key] * 0.9 + row["score"] * 0.1

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
        return [(x.rating, x) for x in sorted(self.tracks.values(), key=lambda x: x.rating, reverse=True)]

    #
    # Public Methods
    #

    def add_directory(self, path: Path) -> None:
        """Add a directory to the library for scanning."""
        path = path.resolve()

        if path.exists() and path.is_dir():
            try:
                self._db.execute("INSERT INTO directories (path) VALUES (?);", (path,))
            except sqlite3.IntegrityError:
                return

            self._db.commit()

    def remove_directory(self, path: Path) -> None:
        """Remove a directory from the library."""
        path = path.resolve()

        self._db.execute("DELETE FROM directories WHERE path = ?;", (path,))
        self._db.commit()

    def scan_directories(self) -> None:
        """Scan all directories in the library for new or updated files."""
        self._scan_directories()

    def _scan_directories(self) -> None:
        print_debug("_scan_directories", "Adding new files")
        self._add_new_files()
        print_debug("_scan_directories", "Removing missing files")
        self._remove_missing_files()
        print_debug("_scan_directories", "Done")
        self._tracks = None
        self._scanning = False

    def get_rating_range(self) -> tuple[float, float]:
        """Get the minimum and maximum ratings of tracks in the library.

        Returns:
            tuple: A tuple containing the minimum and maximum ratings.

        """
        result = self._db.execute("SELECT MAX(rating) AS max, MIN(rating) AS min FROM tracks;").fetchone()
        return (float(result["min"]), float(result["max"]))

    def get_track(self, path: Path) -> Track | None:
        """Get a Track object by its file path.

        Args:
            path (Path): The file path of the track.

        Returns:
            Track: The Track object corresponding to the file path, or None if not found.

        """
        return Track(
            self._db,
            self._db.execute(
                "SELECT t.* FROM tracks t, files f WHERE t.id = f.track_id AND f.path = ?;", (path,)
            ).fetchone(),
        )

    def get_next_tracks(self) -> list[Track]:
        """Get the next two tracks for comparison.

        Returns:
            list: A list containing two Track objects for comparison, or an empty list if not enough tracks are available.

        """
        # TODO: Add support for other selection algorithms. True random at least.
        #       Fix this to only pull tracks that have files.
        count = self._db.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()["count"]

        if count >= 2:
            first = Track(
                self._db,
                self._db.execute(
                    "SELECT * FROM tracks WHERE comparisons = (SELECT MIN(comparisons) FROM tracks) ORDER BY RANDOM() LIMIT 1;"
                ).fetchone(),
            )

            secondsrc = self._db.execute(
                "SELECT * FROM tracks WHERE id != ? AND ABS(rating - ?) < 250 ORDER BY RANDOM() LIMIT 1;",
                (first.id, first.rating),
            ).fetchone()

            if not secondsrc:
                secondsrc = self._db.execute(
                    "SELECT * FROM tracks WHERE id != ? ORDER BY RANDOM() LIMIT 1;", (first.id,)
                ).fetchone()

            second = Track(self._db, secondsrc)

            return [first, second]

        return []

    def update_playing(self, track: Track, losing_tracks: list[Track]) -> None:
        """Update the ratings of the track and its losing tracks based on the comparison.

        Args:
            track (Track): The track that won the comparison.
            losing_tracks (list[Track]): A list of tracks that lost the comparison.

        """
        for losing_track in losing_tracks:
            if track.id < losing_track.id:
                first_track_id, second_track_id = track.id, losing_track.id
                first_track_score = 1.0
                second_track_score = 0.0
            else:
                first_track_id, second_track_id = losing_track.id, track.id
                first_track_score = 0.0
                second_track_score = 1.0

            self._db.execute(
                "INSERT INTO comparisons (first_track_id, second_track_id, score, timestamp) VALUES (?, ?, ?, ?);",
                (first_track_id, second_track_id, first_track_score, datetime.datetime.now(tz=datetime.UTC)),
            )

            first_track = self._db.execute("SELECT * FROM tracks WHERE id = ?;", (first_track_id,)).fetchone()
            second_track = self._db.execute("SELECT * FROM tracks WHERE id = ?;", (second_track_id,)).fetchone()

            first_since = (
                (datetime.datetime.now(tz=datetime.UTC) - first_track["last_update"].astimezone(datetime.UTC)).days
                if first_track["last_update"]
                else 364
            )
            second_since = (
                (datetime.datetime.now(tz=datetime.UTC) - second_track["last_update"].astimezone(datetime.UTC)).days
                if second_track["last_update"]
                else 364
            )

            first_deviation = min(math.sqrt(first_track["deviation"] ** 2 + (18.15682598**2) * first_since), 350)
            second_deviation = min(math.sqrt(second_track["deviation"] ** 2 + (18.15682598**2) * second_since), 350)

            first_new_rating, first_new_deviation = update_rating(
                first_track_score, first_track["rating"], first_deviation, second_track["rating"], second_deviation
            )
            second_new_rating, second_new_deviation = update_rating(
                second_track_score, second_track["rating"], second_deviation, first_track["rating"], first_deviation
            )

            self._db.execute(
                "UPDATE tracks SET comparisons = comparisons + 1, rating = ?, deviation = ?, last_update = ? WHERE id = ?",
                (first_new_rating, first_new_deviation, datetime.datetime.now(tz=datetime.UTC), first_track["id"]),
            )
            self._db.execute(
                "UPDATE tracks SET comparisons = comparisons + 1, rating = ?, deviation = ?, last_update = ? WHERE id = ?",
                (second_new_rating, second_new_deviation, datetime.datetime.now(tz=datetime.UTC), second_track["id"]),
            )

        self._db.commit()

    #
    # Private Methods
    #

    def _add_file(self, directory_id: int, path: str):
        tags = TinyTag.get(path)

        if tags and "musicbrainz_trackid" in tags.other:
            mbid = tags["musicbrainz_trackid"][0]
            result = self._db.execute("SELECT * FROM tracks WHERE mbid = ?;", (mbid,)).fetchone()

            if result:
                track_id = result["id"]
            else:
                track_id = self._db.execute("INSERT INTO tracks (mbid) VALUES (?);", (mbid,)).lastrowid
        else:
            track_id = self._db.execute("INSERT INTO tracks (mbid) VALUES (?);", (None,)).lastrowid

        self._db.execute(
            "INSERT INTO files (directory_id, track_id, path, last_update) VALUES (?, ?, ?, ?);",
            (directory_id, track_id, path, datetime.datetime.now(tz=datetime.UTC)),
        )

    def _add_new_files(self):
        for directory in self._db.execute("SELECT * FROM directories;"):
            for root, dirs, files in os.walk(directory["path"]):
                for path in sorted(files):
                    if path.split(".")[-1].lower() in EXTENSIONS:
                        result = self._db.execute(
                            "SELECT * FROM files WHERE path = ?;", (os.path.join(root, path),)
                        ).fetchone()

                        if not result:
                            self._add_file(directory["id"], os.path.join(root, path))
                        elif result["last_update"] < datetime.datetime.utcfromtimestamp(
                            os.path.getmtime(os.path.join(root, path))
                        ):
                            print_debug("_add_new_files", "Updating file")
                            print(result["path"])
                            print(result["last_update"])
                            print(datetime.datetime.utcfromtimestamp(os.path.getmtime(os.path.join(root, path))))
                            self._update_file(result)

        self._db.commit()

    def _initialize_db(self):
        self._db.execute("PRAGMA foreign_keys = ON;")

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS directories (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE
            );
        """)

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                directory_id INTEGER REFERENCES directories(id) ON UPDATE CASCADE ON DELETE CASCADE,
                track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
                path TEXT UNIQUE,
                last_update TIMESTAMP,
                priority INTEGER
            );
        """)

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY,
                mbid TEXT UNIQUE,
                comparisons INTEGER DEFAULT 0,
                rating REAL DEFAULT 1500,
                deviation REAL DEFAULT 350,
                last_update TIMESTAMP
            );
        """)

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY,
                first_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
                second_track_id INTEGER REFERENCES tracks(id) ON UPDATE CASCADE ON DELETE CASCADE,
                score REAL,
                timestamp TIMESTAMP
            );
        """)

        self._update_tables()
        self._db.commit()

    def _remove_missing_files(self):
        for row in self._db.execute("SELECT * FROM files;").fetchall():
            if not os.path.exists(row["path"]):
                track = self._db.execute("SELECT * FROM tracks WHERE id = ?;", (row["track_id"],)).fetchone()

                # if track['mbid']:
                self._db.execute("DELETE FROM files WHERE id = ?;", (row["id"],))
                # else:
                #    self._db.execute('DELETE FROM tracks WHERE id = ?;', (track['id'],))

        self._db.commit()

    def _update_file(self, row):
        track = self._db.execute("SELECT * FROM tracks WHERE id = ?;", (row["track_id"],)).fetchone()
        tags = mutagen.File(row["path"], easy=True)

        if tags and "musicbrainz_trackid" in tags:
            mbid = tags["musicbrainz_trackid"][0]
        else:
            mbid = None

        if mbid != track["mbid"]:
            print_debug("_update_file", "Musicbrainz ID for {} has changed".format(row["path"]))

            # Determine if the current track has files other than this one.
            files_left = (
                self._db.execute(
                    "SELECT COUNT(*) AS count FROM files WHERE track_id = ? AND id != ?;", (track["id"], row["id"])
                ).fetchone()["count"]
                > 0
            )

            # Determine if the new MBID already exists in the database.
            new_track = self._db.execute("SELECT * FROM tracks WHERE mbid = ?;", (mbid,)).fetchone() if mbid else None

            if not files_left and not new_track:
                print_debug("_update_file", "Updating MBID on existing track")
                self._db.execute("UPDATE tracks SET mbid = ? WHERE id = ?", (mbid, track["id"]))
            elif not files_left and new_track:
                if track["comparisons"] > new_track["comparisons"]:
                    print_debug("_update_file", "Deleting new track and transferring its files to old track.")
                    self._db.execute(
                        "UPDATE files SET track_id = ? WHERE track_id = ?;", (track["id"], new_track["id"])
                    )
                    self._db.execute("DELETE FROM tracks WHERE id = ?;", (new_track["id"],))
                    self._db.execute("UPDATE tracks SET mbid = ? WHERE id = ?", (mbid, track["id"]))
                else:
                    print_debug("_update_file", "Deleting old track and its data. New track has better data.")
                    self._db.execute("DELETE FROM tracks WHERE id = ?;", (track["id"],))
            elif not new_track:
                print_debug(
                    "_update_file",
                    "Creating new track, but files remain on old track. New track will start with fresh data.",
                )
                track_id = self._db.execute("INSERT INTO tracks (mbid) VALUES (?);", (mbid,)).lastrowid
                self._db.execute("UPDATE files SET track_id = ? WHERE id = ?;", (track_id, row["id"]))
            else:
                print_debug("_update_file", "New track exists, but files remain on old track.")
                self._db.execute("UPDATE files SET track_id = ? WHERE id = ?;", (new_track["id"], row["id"]))

        self._db.execute("UPDATE files SET last_update = ? WHERE id = ?;", (datetime.datetime.utcnow(), row["id"]))
        self._db.commit()

    def _update_tables(self):
        version = self._db.execute("SELECT * FROM config WHERE key = ?;", ("database_version",)).fetchone()

        if not version:
            print("Upgrading to database version 1...")
            version = 1
            self._db.execute("INSERT INTO config (key, value) VALUES (?, ?);", ("database_version", version))

        version = int(version["value"])

        if version == 1:
            print("Upgrading to database version 2...")
            version = 2
            self._db.execute("ALTER TABLE tracks ADD comparisons INTEGER DEFAULT 0;")
            self._db.execute("ALTER TABLE tracks ADD rating REAL DEFAULT 1500;")
            self._db.execute("ALTER TABLE tracks ADD deviation REAL DEFAULT 350;")
            self._db.execute("ALTER TABLE tracks ADD last_update TIMESTAMP;")
            self._db.execute("DROP TABLE pairs;")
            self._db.execute("UPDATE config SET value = ? WHERE key = ?;", (version, "database_version"))

        if version == 2:
            print("Upgrading to database version 3...")
            version = 3
            self._db.execute("ALTER TABLE files ADD priority INTEGER DEFAULT 0;")
            self._db.execute("UPDATE config SET value = ? WHERE key = ?;", (version, "database_version"))
