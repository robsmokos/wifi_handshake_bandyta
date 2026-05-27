"""
Resetuje licznik sqlite_sequence dla tabeli handshakes
tak żeby nowe ID szły po kolei za aktualnym MAX(id).
"""
import sqlite3

db_path = '/home/kali/skanerb/handshakes.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT MAX(id) FROM handshakes")
max_id = c.fetchone()[0] or 0

c.execute("SELECT COUNT(*) FROM sqlite_sequence WHERE name='handshakes'")
exists = c.fetchone()[0]

if exists:
    c.execute("UPDATE sqlite_sequence SET seq=? WHERE name='handshakes'", (max_id,))
    print(f"Zresetowano sqlite_sequence do {max_id}")
else:
    c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('handshakes', ?)", (max_id,))
    print(f"Wstawiono sqlite_sequence z wartoscią {max_id}")

conn.commit()

# Weryfikacja
c.execute("SELECT seq FROM sqlite_sequence WHERE name='handshakes'")
seq = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM handshakes")
total = c.fetchone()[0]
c.execute("SELECT MAX(id) FROM handshakes")
max_after = c.fetchone()[0]

print(f"Rekordow w bazie : {total}")
print(f"Max ID           : {max_after}")
print(f"Nowy seq counter : {seq}")
print("OK - nastepny nowy wpis dostanie ID", seq + 1)

conn.close()
