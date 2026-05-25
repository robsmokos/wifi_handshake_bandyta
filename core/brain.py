import asyncio
import time
import logging

class Brain:
    def __init__(self, db, event_queue, attack_queue):
        self.db = db
        self.event_queue = event_queue
        self.attack_queue = attack_queue
        
        # Zabezpieczenie przed dublowaniem celów w Attack Queue
        self.in_attack_queue = set()
        self.running = True

    def is_wpa3(self, ap_data):
        enc = str(ap_data.get('encryption', '')).upper()
        return 'WPA3' in enc or 'SAE' in enc

    async def process_events(self):
        """Konsument zdejmujący wydarzenia ze stosu Event Queue"""
        while self.running:
            try:
                # Obowiązkowy Timeout na czekanie w Queue!
                event = await asyncio.wait_for(self.event_queue.get(), timeout=5)
                await self.handle_event(event)
                self.event_queue.task_done()
            except asyncio.TimeoutError:
                # Jeśli po 5 sekundach nic nie wpadło, flushujemy baze dla bezpieczeństwa
                await self.db.flush()
            except Exception as e:
                logging.error(f"Brain Error: {e}")

    async def handle_event(self, event):
        data = event.get('data', {})
        if not data: return
        
        ap = data.get('ap', data) if isinstance(data, dict) else data
        if not isinstance(ap, dict): return
        
        bssid = ap.get('mac')
        if not bssid: return
        
        essid = ap.get('hostname', '<ukryty>')
        vendor = ap.get('vendor', '')
        rssi = ap.get('rssi', -100)
        channel = ap.get('channel', 1)
        
        # 1. Zapis do DB (async)
        await self.db.update_ap(bssid, essid=essid, vendor=vendor)
        
        # 2. Pobranie najnowszych danych by przeliczyć Scoring
        db_info = await self.db.get_ap(bssid)
        if not db_info: return
        
        status = db_info.get('status')
        if status in ['przechwycono', 'pmkid_przechwycono']: return
        if self.is_wpa3(ap): return
        
        # Deduplikacja
        if bssid in self.in_attack_queue: return
        
        # 3. SCORING SYSTEM z Historią i Karami (Penalty)
        clients = ap.get('clients', [])
        client_count = len(clients) if isinstance(clients, (list, dict)) else 0
        
        failures = db_info.get('liczba_atakow_deauth', 0) + db_info.get('liczba_atakow_pmkid', 0)
        bonus_nowej_sieci = 20 if failures == 0 else 0
        
        last_attack = db_info.get('last_attacked_at', 0)
        time_since_attack = time.time() - last_attack
        cooldown_penalty = 0
        
        if last_attack > 0:
            if time_since_attack < 180:
                # Kara za obsesyjne atakowanie: max do -180 punktów
                cooldown_penalty = (180 - time_since_attack)
                
        # Główny algorytm (RSSI jest ujemne!)
        score = (client_count * 5) + rssi + bonus_nowej_sieci - (failures * 10) - cooldown_penalty
        
        # Ignoruj kompletnie tragiczne wyniki (wypadnie z obiegu na dłuższą chwilę)
        if score < -150: return

        attack_type = None
        target_client = None
        
        if client_count > 0:
            attack_type = "deauth"
            if isinstance(clients, dict): target_client = list(clients.keys())[0]
            elif isinstance(clients, list) and isinstance(clients[0], dict): target_client = clients[0].get('mac')
            elif isinstance(clients, list): target_client = str(clients[0])
        else:
            if db_info.get('liczba_atakow_pmkid', 0) < 3:
                attack_type = "pmkid"
                
        if attack_type:
            # Budowa "Wyroku" dla Executora
            attack_payload = {
                'bssid': bssid,
                'essid': essid,
                'rssi': rssi,
                'channel': channel,
                'type': attack_type,
                'client_mac': target_client,
                'timestamp': time.time() # Do obsługi TTL w Attack Queue
            }
            try:
                # Kolejny obowiązkowy timeout!
                await asyncio.wait_for(self.attack_queue.put(attack_payload), timeout=2)
                self.in_attack_queue.add(bssid)
            except asyncio.TimeoutError:
                pass
