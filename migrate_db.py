import sqlite3
import os

db_path = 'handshakes.db'
if not os.path.exists(db_path):
    print("DB not found at", db_path)
    exit(0)

conn = sqlite3.connect(db_path)
c = conn.cursor()

def get_columns():
    c.execute("PRAGMA table_info(handshakes)")
    return [info[1] for info in c.fetchall()]

# --- Krok 1: Dodaj kolumnę 'id' jeśli brakuje ---
columns = get_columns()
if 'id' not in columns:
    print("Migrating database: adding 'id' column...")
    try:
        c.execute('''
            CREATE TABLE handshakes_new (
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
                status TEXT DEFAULT 'nowy'
            )
        ''')
        c.execute('''
            INSERT INTO handshakes_new (
                bssid, essid, vendor, first_seen, last_seen, gps_lat, gps_lon,
                czas_przechwycenia, last_attacked_at,
                liczba_atakow_deauth, liczba_atakow_pmkid, status
            )
            SELECT
                bssid, essid, vendor, first_seen, last_seen, gps_lat, gps_lon,
                czas_przechwycenia, last_attacked_at,
                liczba_atakow_deauth, liczba_atakow_pmkid, status
            FROM handshakes
            ORDER BY first_seen ASC
        ''')
        c.execute("DROP TABLE handshakes")
        c.execute("ALTER TABLE handshakes_new RENAME TO handshakes")
        conn.commit()
        print("Migration 'id': OK")
    except Exception as e:
        conn.rollback()
        print("Migration 'id' failed:", e)
else:
    print("Database already has 'id' column.")

# --- Krok 2: Dodaj kolumnę 'last_modified' jeśli brakuje ---
columns = get_columns()
if 'last_modified' not in columns:
    print("Migrating database: adding 'last_modified' column...")
    try:
        c.execute("ALTER TABLE handshakes ADD COLUMN last_modified TEXT")
        c.execute("UPDATE handshakes SET last_modified = last_seen")
        conn.commit()
        print("Migration 'last_modified': OK")
    except Exception as e:
        print("Migration 'last_modified' failed:", e)
else:
    print("Database already has 'last_modified' column.")

# --- Krok 3: Usuń kolumnę 'sciezka_do_pliku' jeśli istnieje ---
columns = get_columns()
if 'sciezka_do_pliku' in columns:
    print("Migrating database: removing 'sciezka_do_pliku' column...")
    try:
        c.execute("ALTER TABLE handshakes DROP COLUMN sciezka_do_pliku")
        conn.commit()
        print("Migration 'sciezka_do_pliku' (DROP): OK")
    except Exception as e:
        print("DROP COLUMN failed, attempting table rebuild...", e)
        try:
            c.execute('''
                CREATE TABLE handshakes_rebuild (
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
                )
            ''')
            c.execute('''
                INSERT INTO handshakes_rebuild (
                    id, bssid, essid, vendor, first_seen, last_seen, gps_lat, gps_lon,
                    czas_przechwycenia, last_attacked_at,
                    liczba_atakow_deauth, liczba_atakow_pmkid, status, last_modified
                )
                SELECT
                    id, bssid, essid, vendor, first_seen, last_seen, gps_lat, gps_lon,
                    czas_przechwycenia, last_attacked_at,
                    liczba_atakow_deauth, liczba_atakow_pmkid, status,
                    COALESCE(last_modified, last_seen)
                FROM handshakes
            ''')
            c.execute("DROP TABLE handshakes")
            c.execute("ALTER TABLE handshakes_rebuild RENAME TO handshakes")
            conn.commit()
            print("Migration 'sciezka_do_pliku' (rebuild): OK")
        except Exception as e2:
            conn.rollback()
            print("Migration 'sciezka_do_pliku' (rebuild) failed:", e2)
else:
    print("Column 'sciezka_do_pliku' not present (OK).")

# --- Krok 4: Dodaj kolumnę 'encryption' jeśli brakuje ---
columns = get_columns()
if 'encryption' not in columns:
    print("Migrating database: adding 'encryption' column...")
    try:
        c.execute("ALTER TABLE handshakes ADD COLUMN encryption TEXT")
        conn.commit()
        print("Migration 'encryption': OK")
    except Exception as e:
        print("Migration 'encryption' failed:", e)
else:
    print("Database already has 'encryption' column.")

# --- Krok 5: Dodaj kolumnę 'liczba_atakow_pixiedust' jeśli brakuje ---
columns = get_columns()
if 'liczba_atakow_pixiedust' not in columns:
    print("Migrating database: adding 'liczba_atakow_pixiedust' column...")
    try:
        c.execute("ALTER TABLE handshakes ADD COLUMN liczba_atakow_pixiedust INTEGER DEFAULT 0")
        c.execute("UPDATE handshakes SET liczba_atakow_pixiedust = 0 WHERE liczba_atakow_pixiedust IS NULL")
        conn.commit()
        print("Migration 'liczba_atakow_pixiedust': OK")
    except Exception as e:
        print("Migration 'liczba_atakow_pixiedust' failed:", e)
else:
    print("Database already has 'liczba_atakow_pixiedust' column.")

conn.close()
