"""
Przebudowuje tablicę handshakes z nowym, ciagłym numerowaniem ID
zaczynajac od 1 (posortowane wg first_seen).
Tworzy backup przed operacją.
"""
import sqlite3
import shutil
import os
from datetime import datetime

db_path = '/home/kali/skanerb/handshakes.db'
backup_path = f'/home/kali/skanerb/handshakes_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

# Backup
shutil.copy2(db_path, backup_path)
print(f"Backup zapisany: {backup_path}")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Sprawdź schemat przed operacją
c.execute("SELECT COUNT(*) FROM handshakes")
total_before = c.fetchone()[0]
c.execute("SELECT MAX(id) FROM handshakes")
max_before = c.fetchone()[0]
print(f"Przed: {total_before} rekordów, MAX id={max_before}")

# Przebuduj tabelę z nowymi ID
c.executescript("""
    CREATE TABLE handshakes_renumbered (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bssid TEXT UNIQUE,
        essid TEXT,
        vendor TEXT,
        first_seen TEXT,
        last_seen TEXT,
        gps_lat REAL,
        gps_lon REAL,
        czas_przechwycenia TEXT,
        last_attacked_at REAL DEFAULT 0,
        liczba_atakow_deauth INTEGER DEFAULT 0,
        liczba_atakow_pmkid INTEGER DEFAULT 0,
        status TEXT DEFAULT 'nowy',
        last_modified TEXT
    );

    INSERT INTO handshakes_renumbered (
        bssid, essid, vendor, first_seen, last_seen,
        gps_lat, gps_lon, czas_przechwycenia,
        last_attacked_at, liczba_atakow_deauth, liczba_atakow_pmkid,
        status, last_modified
    )
    SELECT
        bssid, essid, vendor, first_seen, last_seen,
        gps_lat, gps_lon, czas_przechwycenia,
        last_attacked_at, liczba_atakow_deauth, liczba_atakow_pmkid,
        status, last_modified
    FROM handshakes
    ORDER BY first_seen ASC;

    DROP TABLE handshakes;
    ALTER TABLE handshakes_renumbered RENAME TO handshakes;
""")

conn.commit()

# Weryfikacja
c.execute("SELECT COUNT(*) FROM handshakes")
total_after = c.fetchone()[0]
c.execute("SELECT MAX(id) FROM handshakes")
max_after = c.fetchone()[0]
c.execute("SELECT MIN(id) FROM handshakes")
min_after = c.fetchone()[0]
c.execute("SELECT seq FROM sqlite_sequence WHERE name='handshakes'")
seq = c.fetchone()[0]

print(f"Po:    {total_after} rekordów, ID od {min_after} do {max_after}, seq={seq}")
print("OK! ID sa teraz ciagle i zaczynaja sie od 1.")

conn.close()
