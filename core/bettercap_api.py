import asyncio
import aiohttp
import json
import logging
import time

class BettercapAPI:
    def __init__(self, event_queue, host="127.0.0.1", port=8081, username="", password=""):
        self.url_events = f"http://{host}:{port}/api/events"
        self.url_session = f"http://{host}:{port}/api/session"
        self.auth = aiohttp.BasicAuth(username, password) if username or password else None
        self.event_queue = event_queue
        self.running = True

    async def run_command(self, cmd):
        """Wysyła pojedynczą komendę do sesji Bettercapa z wymuszonym Timeoutem."""
        payload = {"cmd": cmd}
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(auth=self.auth, timeout=timeout) as session:
                async with session.post(self.url_session, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            # W środowisku testowym może brakować podłączonego serwera, uciszamy logging
            # logging.error(f"Command error {cmd}: {e}")
            return False

    async def set_channel(self, channel):
        if channel == 'clear':
            return await self.run_command("wifi.recon.channel clear")
        return await self.run_command(f"wifi.recon.channel {channel}")

    async def send_deauth(self, bssid, client_mac):
        return await self.run_command(f"wifi.deauth {bssid} {client_mac}")

    async def send_assoc(self, bssid):
        return await self.run_command(f"wifi.assoc {bssid}")

    async def event_stream_listener(self):
        """Asynchronicznie odpytuje REST API Bettercapa i natychmiast czyści jego bufor."""
        backoff = 1
        last_session_pull = 0
        while self.running:
            try:
                now = time.time()
                # Co 10 sekund zaciągnij PEŁNĄ listę widocznych sieci, by odświeżyć ich siłę sygnału i klientów
                if now - last_session_pull > 10:
                    timeout = aiohttp.ClientTimeout(total=5)
                    async with aiohttp.ClientSession(auth=self.auth, timeout=timeout) as session:
                        async with session.get(self.url_session) as response:
                            if response.status == 200:
                                data = await response.json()
                                aps = data.get('wifi', {}).get('aps', [])
                                for ap in aps:
                                    try:
                                        await asyncio.wait_for(self.event_queue.put({'data': {'ap': ap}}), timeout=0.1)
                                    except asyncio.TimeoutError:
                                        pass
                                last_session_pull = now

                # Pobieranie szybkich eventów z bufora
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(auth=self.auth, timeout=timeout) as session:
                    async with session.get(self.url_events) as response:
                        backoff = 1
                        text = await response.text()
                        if text.strip():
                            try:
                                events = json.loads(text)
                                for event in events:
                                    tag = event.get('tag', '')
                                    if tag.startswith('wifi.ap.') or tag.startswith('wifi.client.'):
                                        try:
                                            await asyncio.wait_for(self.event_queue.put(event), timeout=2)
                                        except asyncio.TimeoutError:
                                            pass
                                # Czyść bufor tylko jeśli były jakieś eventy
                                if events:
                                    await self.run_command("events.clear")
                            except json.JSONDecodeError:
                                pass
                await asyncio.sleep(1) # Polling 1s
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                # Brak połączenia - backoff
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
