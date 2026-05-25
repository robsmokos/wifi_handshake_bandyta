import asyncio
import aiosqlite
import time
from datetime import datetime

class Database:
    def __init__(self, db_path="handshakes.db"):
        self.db_path = db_path
        self.pending_updates = {}
        self.last_flush = time.time()
        self.flush_interval = 15
        self.lock = asyncio.Lock()

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as conn:
            # WAL dla lepszej wydajności zapytań na karcie SD
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS handshakes (
                    bssid TEXT PRIMARY KEY,
                    essid TEXT,
                    vendor TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    gps_lat REAL,
                    gps_lon REAL,
                    sciezka_do_pliku TEXT,
                    czas_przechwycenia TEXT,
                    last_attacked_at REAL DEFAULT 0,
                    liczba_atakow_deauth INTEGER DEFAULT 0,
                    liczba_atakow_pmkid INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'nowy'
                )
            ''')
            await conn.commit()

    async def get_ap(self, bssid):
        async with self.lock:
            if bssid in self.pending_updates:
                return self.pending_updates[bssid]
                
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM handshakes WHERE bssid = ?", (bssid,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None

    async def update_ap(self, bssid, essid=None, vendor=None, gps_lat=None, gps_lon=None):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Pobranie rekordu BEZ użycia locka (zapobiega to zakleszczeniu reentrant asyncio.Lock)
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing:
                    self.pending_updates[bssid] = existing
                else:
                    self.pending_updates[bssid] = {
                        'bssid': bssid, 'essid': essid, 'vendor': vendor,
                        'first_seen': now_str, 'last_seen': now_str,
                        'gps_lat': gps_lat, 'gps_lon': gps_lon,
                        'sciezka_do_pliku': None, 'czas_przechwycenia': None,
                        'last_attacked_at': 0.0,
                        'liczba_atakow_deauth': 0, 'liczba_atakow_pmkid': 0,
                        'status': 'nowy'
                    }
                    
            ap = self.pending_updates[bssid]
            ap['last_seen'] = now_str
            if essid and ap['essid'] != essid: ap['essid'] = essid
            if vendor and ap['vendor'] != vendor: ap['vendor'] = vendor
            if gps_lat is not None: ap['gps_lat'] = gps_lat
            if gps_lon is not None: ap['gps_lon'] = gps_lon
            
        await self.check_flush()

    async def mark_attack(self, bssid, attack_type="deauth"):
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing: self.pending_updates[bssid] = existing
                
            if bssid in self.pending_updates:
                ap = self.pending_updates[bssid]
                ap['last_attacked_at'] = time.time()
                if attack_type == "deauth":
                    ap['liczba_atakow_deauth'] += 1
                elif attack_type == "pmkid":
                    ap['liczba_atakow_pmkid'] += 1
                    
        await self.check_flush()

    async def update_status(self, bssid, status, pcap_path=None):
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing: self.pending_updates[bssid] = existing
                
            if bssid in self.pending_updates:
                ap = self.pending_updates[bssid]
                ap['status'] = status
                if status in ['przechwycono', 'pmkid_przechwycono']:
                    ap['czas_przechwycenia'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if pcap_path: ap['sciezka_do_pliku'] = pcap_path
                    
        await self.check_flush()

    async def check_flush(self):
        if time.time() - self.last_flush >= self.flush_interval:
            await self.flush()

    async def flush(self):
        """Asynchroniczny zrzut z pamięci RAM do pamięci dyskowej."""
        async with self.lock:
            if not self.pending_updates:
                return
            updates = list(self.pending_updates.values())
            self.pending_updates.clear()
            self.last_flush = time.time()

        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
                
                for data in updates:
                    await conn.execute('''
                        INSERT INTO handshakes (
                            bssid, essid, vendor, first_seen, last_seen, 
                            gps_lat, gps_lon, sciezka_do_pliku, czas_przechwycenia,
                            last_attacked_at, liczba_atakow_deauth, liczba_atakow_pmkid, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(bssid) DO UPDATE SET
                            essid=excluded.essid,
                            vendor=excluded.vendor,
                            last_seen=excluded.last_seen,
                            gps_lat=excluded.gps_lat,
                            gps_lon=excluded.gps_lon,
                            sciezka_do_pliku=excluded.sciezka_do_pliku,
                            czas_przechwycenia=excluded.czas_przechwycenia,
                            last_attacked_at=excluded.last_attacked_at,
                            liczba_atakow_deauth=excluded.liczba_atakow_deauth,
                            liczba_atakow_pmkid=excluded.liczba_atakow_pmkid,
                            status=excluded.status
                    ''', (
                        data['bssid'], data['essid'], data['vendor'], data['first_seen'], data['last_seen'],
                        data['gps_lat'], data['gps_lon'], data['sciezka_do_pliku'], data['czas_przechwycenia'],
                        data['last_attacked_at'], data['liczba_atakow_deauth'], data['liczba_atakow_pmkid'], data['status']
                    ))
                await conn.commit()
        except Exception as e:
            # Prawidłowa obsługa błędów, by błąd DB nie powalił aplikacji
            print(f"\n[!] Błąd zapisu bazy: {e}")

    async def get_stats(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with conn.execute("SELECT COUNT(*) FROM handshakes") as cursor:
                    db_total = (await cursor.fetchone())[0]
                async with conn.execute("SELECT COUNT(*) FROM handshakes WHERE status IN ('przechwycono', 'pmkid_przechwycono')") as cursor:
                    db_captured = (await cursor.fetchone())[0]
            return db_total, db_captured
        except Exception:
            return 0, 0

    async def get_top_aps(self, limit=10):
        await self.check_flush()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                query = """
                    SELECT bssid, essid, liczba_atakow_deauth, liczba_atakow_pmkid, status 
                    FROM handshakes 
                    ORDER BY 
                        CASE WHEN status LIKE '%przechwycono%' THEN 1 ELSE 0 END ASC,
                        last_attacked_at DESC, 
                        last_seen DESC
                    LIMIT ?
                """
                async with db.execute(query, (limit,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception:
            return []
