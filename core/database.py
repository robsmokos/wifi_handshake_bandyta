import asyncio
import aiosqlite
import time
import os
from datetime import datetime

class Database:
    def __init__(self, db_path="handshakes.db"):
        self.db_path = db_path
        self.pending_updates = {}
        self.active_aps = {}
        self.last_flush = time.time()
        self.flush_interval = 30  # Większy interval by nie męczyć karty SD
        self.lock = asyncio.Lock()
        # Tracker tempa odkryć nowych sieci (timestampy first_seen, max 10 min)
        self.discovery_timestamps = []
        self.known_bssids = set()

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as conn:
            # WAL dla lepszej wydajności zapytań na karcie SD
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS handshakes (
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
                    liczba_atakow_pixiedust INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'nowy',
                    encryption TEXT,
                    last_modified TEXT
                )
            ''')
            await conn.commit()
            
            # Załaduj znane BSSIDy aby tracker odkryć wiedział co jest "nowe"
            try:
                async with conn.execute("SELECT bssid FROM handshakes") as cursor:
                    rows = await cursor.fetchall()
                    self.known_bssids = {row[0] for row in rows}
                
                # Seed discovery_timestamps z ostatnich 10 minut (przetrwa restart)
                from datetime import timedelta
                cutoff = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                async with conn.execute(
                    "SELECT first_seen FROM handshakes WHERE first_seen >= ? ORDER BY first_seen ASC",
                    (cutoff,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        try:
                            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                            self.discovery_timestamps.append(dt.timestamp())
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

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

    async def update_ap(self, bssid, essid=None, vendor=None, gps_lat=None, gps_lon=None, encryption=None):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Pobranie rekordu BEZ użycia locka (zapobiega to zakleszczeniu reentrant asyncio.Lock)
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing:
                    # Upewnij się że stare rekordy z bazy mają pole last_modified
                    if 'last_modified' not in existing or existing['last_modified'] is None:
                        existing['last_modified'] = existing.get('last_seen', now_str)
                    self.pending_updates[bssid] = existing
                else:
                    self.pending_updates[bssid] = {
                        'id': None,
                        'bssid': bssid, 'essid': essid, 'vendor': vendor,
                        'first_seen': now_str, 'last_seen': now_str,
                        'gps_lat': gps_lat, 'gps_lon': gps_lon,
                        'czas_przechwycenia': None,
                        'last_attacked_at': 0.0,
                        'liczba_atakow_deauth': 0, 'liczba_atakow_pmkid': 0,
                        'liczba_atakow_pixiedust': 0,
                        'status': 'nowy',
                        'encryption': encryption,
                        'last_modified': now_str
                    }
                    # Nowa sieć — rejestruj odkrycie
                    self.discovery_timestamps.append(time.time())
                    self.known_bssids.add(bssid)
                    
            ap = self.pending_updates[bssid]
            ap['last_seen'] = now_str
            ap['last_modified'] = now_str
            if essid and ap['essid'] != essid:
                # Nie nadpisujemy znanej nazwy sieci ogólnym znacznikiem ukrycia
                is_current_hidden = ap['essid'] in (None, "", "<ukryty>", "<ukryte>", "ukryta")
                is_new_hidden = essid in (None, "", "<ukryty>", "<ukryte>", "ukryta")
                
                # Wykrycie odzyskania ukrytego ESSID
                if is_current_hidden and not is_new_hidden:
                    old_essid = ap['essid']
                    
                    # Zmiana nazw plików handshake, jeśli istnieją
                    bssid_file_name = bssid.replace(":", "-")
                    old_essid_safe = "".join([c for c in str(old_essid or 'ukryta') if c.isalnum() or c in ('_', '-')]).strip()
                    if not old_essid_safe:
                        old_essid_safe = "ukryta"
                        
                    new_essid_safe = "".join([c for c in str(essid) if c.isalnum() or c in ('_', '-')]).strip()
                    if not new_essid_safe:
                        new_essid_safe = "ukryta"
                    
                    pcap_dir = "handshakes"
                    for ext in ['.pcap', '.hc22000']:
                        old_path = os.path.join(pcap_dir, f"{old_essid_safe}_{bssid_file_name}{ext}")
                        new_path = os.path.join(pcap_dir, f"{new_essid_safe}_{bssid_file_name}{ext}")
                        if os.path.exists(old_path):
                            try:
                                os.rename(old_path, new_path)
                                print(f"\n[Database] Zmieniono nazwe pliku po odzyskaniu ESSID: {old_path} -> {new_path}")
                            except Exception as e:
                                print(f"\n[Database] Blad podczas zmiany nazwy pliku handshake: {e}")

                if is_current_hidden or not is_new_hidden:
                    ap['essid'] = essid
            if vendor and ap['vendor'] != vendor: ap['vendor'] = vendor
            if gps_lat is not None: ap['gps_lat'] = gps_lat
            if gps_lon is not None: ap['gps_lon'] = gps_lon
            if encryption and ap.get('encryption') != encryption: ap['encryption'] = encryption
            
        await self.check_flush()

    async def mark_attack(self, bssid, attack_type="deauth"):
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing:
                    if 'last_modified' not in existing or existing['last_modified'] is None:
                        existing['last_modified'] = existing.get('last_seen', '')
                    self.pending_updates[bssid] = existing
                
            if bssid in self.pending_updates:
                ap = self.pending_updates[bssid]
                ap['last_attacked_at'] = time.time()
                ap['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if attack_type == "deauth":
                    ap['liczba_atakow_deauth'] += 1
                elif attack_type == "pmkid":
                    ap['liczba_atakow_pmkid'] += 1
                elif attack_type == "pixiedust":
                    ap['liczba_atakow_pixiedust'] = ap.get('liczba_atakow_pixiedust', 0) + 1
                    
        await self.check_flush()

    async def reset_attacks(self, bssid):
        existing = await self.get_ap(bssid)
        if not existing:
            return
            
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing:
                    if 'last_modified' not in existing or existing['last_modified'] is None:
                        existing['last_modified'] = existing.get('last_seen', '')
                    self.pending_updates[bssid] = existing
                
            if bssid in self.pending_updates:
                ap = self.pending_updates[bssid]
                ap['liczba_atakow_deauth'] = 0
                ap['liczba_atakow_pmkid'] = 0
                ap['liczba_atakow_pixiedust'] = 0
                ap['last_attacked_at'] = 0.0
                ap['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
        await self.check_flush()

    async def update_status(self, bssid, status):
        existing = await self.get_ap(bssid)
        
        async with self.lock:
            if bssid not in self.pending_updates:
                if existing:
                    if 'last_modified' not in existing or existing['last_modified'] is None:
                        existing['last_modified'] = existing.get('last_seen', '')
                    self.pending_updates[bssid] = existing
                
            if bssid in self.pending_updates:
                ap = self.pending_updates[bssid]
                ap['status'] = status
                ap['last_modified'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if status in ['przechwycono', 'pmkid_przechwycono']:
                    ap['czas_przechwycenia'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
        await self.check_flush()

    async def delete_ap(self, bssid):
        async with self.lock:
            # Usuniecie z buforow pamieci
            if bssid in self.pending_updates:
                del self.pending_updates[bssid]
            if bssid in self.active_aps:
                del self.active_aps[bssid]
            if bssid in self.known_bssids:
                self.known_bssids.discard(bssid)
                
        # Natychmiastowe usuniecie z bazy sqlite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM handshakes WHERE bssid = ?", (bssid,))
            await conn.commit()

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
                            gps_lat, gps_lon, czas_przechwycenia,
                            last_attacked_at, liczba_atakow_deauth, liczba_atakow_pmkid, liczba_atakow_pixiedust, status, encryption, last_modified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(bssid) DO UPDATE SET
                            essid=excluded.essid,
                            vendor=excluded.vendor,
                            last_seen=excluded.last_seen,
                            gps_lat=excluded.gps_lat,
                            gps_lon=excluded.gps_lon,
                            czas_przechwycenia=excluded.czas_przechwycenia,
                            last_attacked_at=excluded.last_attacked_at,
                            liczba_atakow_deauth=excluded.liczba_atakow_deauth,
                            liczba_atakow_pmkid=excluded.liczba_atakow_pmkid,
                            liczba_atakow_pixiedust=excluded.liczba_atakow_pixiedust,
                            status=excluded.status,
                            encryption=excluded.encryption,
                            last_modified=excluded.last_modified
                    ''', (
                        data['bssid'], data['essid'], data['vendor'], data['first_seen'], data['last_seen'],
                        data['gps_lat'], data['gps_lon'], data['czas_przechwycenia'],
                        data['last_attacked_at'], data['liczba_atakow_deauth'], data['liczba_atakow_pmkid'],
                        data.get('liczba_atakow_pixiedust', 0), data['status'], data.get('encryption'), data.get('last_modified')
                    ))
                await conn.commit()
        except Exception as e:
            # Prawidłowa obsługa błędów - przywróć dane do pending by nie tracić
            print(f"\n[!] Błąd zapisu bazy: {e}")
            async with self.lock:
                for item in updates:
                    bssid = item['bssid']
                    if bssid not in self.pending_updates:
                        self.pending_updates[bssid] = item

    def get_discovery_rate(self):
        """Zwraca (rate_per_min, trend_arrow, seconds_since_last).
        
        rate_per_min: ilość nowych sieci/min w ostatnich 5 minutach
        trend_arrow: '▲' jeśli ostatnie 2.5 min lepsze, '▼' jeśli gorsze, '—' jeśli stabilne
        seconds_since_last: sekundy od ostatniego odkrycia nowej sieci (None jeśli brak danych)
        """
        now = time.time()
        window = 600  # 10 minut max historia
        half = 300    # 5 minut na obliczenie rate
        quarter = 150 # 2.5 min na trend
        
        # Wyczyść stare timestampy (starsze niż 10 min)
        self.discovery_timestamps = [t for t in self.discovery_timestamps if now - t <= window]
        
        # Sekundy od ostatniego odkrycia
        if self.discovery_timestamps:
            seconds_since_last = now - self.discovery_timestamps[-1]
        elif self.known_bssids:
            # Baza istnieje ale żadnych nowych odkryć w tej sesji / ostatnich 10 min
            seconds_since_last = float('inf')
        else:
            seconds_since_last = None
        
        # Rate: nowe sieci w ostatnich 5 minutach, przeliczone na /min
        recent = [t for t in self.discovery_timestamps if now - t <= half]
        rate = (len(recent) / half) * 60 if recent else 0.0
        
        # Trend: porównanie ostatnich 2.5 min vs poprzednich 2.5 min
        recent_quarter = [t for t in self.discovery_timestamps if now - t <= quarter]
        prev_quarter = [t for t in self.discovery_timestamps if quarter < now - t <= half]
        
        if len(recent_quarter) > len(prev_quarter):
            trend = '\u25b2'  # ▲
        elif len(recent_quarter) < len(prev_quarter):
            trend = '\u25bc'  # ▼
        else:
            trend = '\u2014'  # —
        
        return round(rate, 1), trend, seconds_since_last

    async def get_stats(self):
        """Zwraca (total_ap, captured_ap) uwzględniając niezapisane dane z pamięci."""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with conn.execute("SELECT COUNT(*) FROM handshakes") as cursor:
                    db_total = (await cursor.fetchone())[0]
                async with conn.execute("SELECT COUNT(*) FROM handshakes WHERE status IN ('przechwycono', 'pmkid_przechwycono')") as cursor:
                    db_captured = (await cursor.fetchone())[0]
            
            # Dodaj pozycje z pamięci które nie trafia jeszcze do DB
            async with self.lock:
                pending_bssids = set(self.pending_updates.keys())
            
            # Pobierz bssidy które są w DB (by nie liczyć dwa razy)
            if pending_bssids:
                async with aiosqlite.connect(self.db_path) as conn:
                    placeholders = ','.join('?' * len(pending_bssids))
                    async with conn.execute(f"SELECT bssid FROM handshakes WHERE bssid IN ({placeholders})", list(pending_bssids)) as cursor:
                        existing_in_db = {row[0] for row in await cursor.fetchall()}
                new_only = pending_bssids - existing_in_db
                db_total += len(new_only)
                # Zlicz przechwycone z pending których nie ma w DB
                async with self.lock:
                    for bssid in new_only:
                        ap = self.pending_updates.get(bssid, {})
                        if ap.get('status') in ('przechwycono', 'pmkid_przechwycono'):
                            db_captured += 1
            
            return db_total, db_captured
        except Exception:
            return 0, 0

    async def get_top_aps(self, limit=10):
        """Zwraca top AP z bazy + pending_updates w pamięci."""
        try:
            # Pobierz dane z dysku
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
                    db_results = {r['bssid']: dict(r) for r in rows}

            # Scal z pending_updates (nowe lub zaktualizowane wpisy z RAM)
            async with self.lock:
                for bssid, ap in self.pending_updates.items():
                    db_results[bssid] = {
                        'bssid': bssid,
                        'essid': ap.get('essid'),
                        'liczba_atakow_deauth': ap.get('liczba_atakow_deauth', 0),
                        'liczba_atakow_pmkid': ap.get('liczba_atakow_pmkid', 0),
                        'status': ap.get('status', 'nowy'),
                        'last_attacked_at': ap.get('last_attacked_at', 0),
                    }

            # Sortuj: przechwycone na dół, potem najczęściej atakowane na górę
            sorted_aps = sorted(
                db_results.values(),
                key=lambda x: (
                    1 if 'przechwycono' in x.get('status', '') else 0,
                    -x.get('last_attacked_at', 0)
                )
            )
            return sorted_aps[:limit]
        except Exception:
            return []

    async def update_active_ap(self, bssid, essid, vendor, rssi, channel, encryption, clients, wps):
        async with self.lock:
            # Preserve existing client count if we don't have clients in this update
            if clients is None:
                existing = self.active_aps.get(bssid)
                client_count = existing['client_count'] if existing else 0
            else:
                client_count = len(clients) if isinstance(clients, (list, dict)) else 0
            
            wps_str = "NIE"
            if isinstance(wps, dict) and wps:
                version = wps.get('Version', '')
                wps_str = f"TAK ({version})" if version else "TAK"
            elif wps:
                wps_str = "TAK"
            
            enc_str = ""
            if isinstance(encryption, list):
                enc_str = ", ".join(encryption)
            else:
                enc_str = str(encryption)
                
            self.active_aps[bssid] = {
                'bssid': bssid,
                'essid': essid,
                'vendor': vendor,
                'rssi': rssi,
                'channel': channel,
                'encryption': enc_str,
                'client_count': client_count,
                'wps': wps_str,
                'last_seen_time': time.time()
            }

    async def get_active_aps(self):
        async with self.lock:
            now = time.time()
            self.active_aps = {
                bssid: ap for bssid, ap in self.active_aps.items()
                if now - ap['last_seen_time'] <= 60
            }
            return list(self.active_aps.values())

    async def get_active_aps_with_status(self):
        active_list = await self.get_active_aps()
        if not active_list:
            return []
            
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            bssids = [ap['bssid'] for ap in active_list]
            placeholders = ','.join('?' * len(bssids))
            sql = f"SELECT bssid, status, liczba_atakow_deauth, liczba_atakow_pmkid, liczba_atakow_pixiedust, last_attacked_at FROM handshakes WHERE bssid IN ({placeholders})"
            
            db_status = {}
            try:
                async with conn.execute(sql, bssids) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        db_status[row['bssid']] = dict(row)
            except Exception:
                pass
                
            for ap in active_list:
                status_info = db_status.get(ap['bssid'], {})
                ap['status'] = status_info.get('status', 'nowy')
                ap['liczba_atakow_deauth'] = status_info.get('liczba_atakow_deauth', 0)
                ap['liczba_atakow_pmkid'] = status_info.get('liczba_atakow_pmkid', 0)
                ap['liczba_atakow_pixiedust'] = status_info.get('liczba_atakow_pixiedust', 0)
                
                # Pomiń obliczanie Brain Score dla zbanowanych sieci
                if ap['status'] == 'zbanowany':
                    ap['score'] = '-'
                else:
                    # Dynamic Brain Score Calculation matching brain.py
                    failures = ap['liczba_atakow_deauth'] + ap['liczba_atakow_pmkid']
                    bonus_nowej_sieci = 20 if failures == 0 else 0
                    
                    last_attack = status_info.get('last_attacked_at', 0.0) or 0.0
                    time_since_attack = time.time() - last_attack
                    cooldown_penalty = 0.0
                    if last_attack > 0.0 and time_since_attack < 180.0:
                        cooldown_penalty = (180.0 - time_since_attack)
                    
                    score = (ap['client_count'] * 5) + ap['rssi'] + bonus_nowej_sieci - (failures * 10) - cooldown_penalty
                    ap['score'] = round(score, 1)
                
                bssid_file_name = ap['bssid'].replace(":", "-")
                essid_safe = "".join([c for c in str(ap['essid'] or '') if c.isalnum() or c in ('_', '-')]).strip()
                if not essid_safe:
                    essid_safe = "ukryta"
                
                pcap_name = f"{essid_safe}_{bssid_file_name}.pcap"
                hash_name = f"{essid_safe}_{bssid_file_name}.hc22000"
                
                ap['pcap_exists'] = os.path.exists(os.path.join('handshakes', pcap_name))
                ap['hash_exists'] = os.path.exists(os.path.join('handshakes', hash_name))
                ap['pcap_filename'] = pcap_name
                ap['hash_filename'] = hash_name
                
            active_list.sort(key=lambda x: x['rssi'], reverse=True)
            return active_list
