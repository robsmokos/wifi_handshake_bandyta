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
        self.current_gps = (None, None)

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
        # Bettercap woli jeden cel w wifi.deauth
        target = client_mac if client_mac else bssid
        return await self.run_command(f"wifi.deauth {target}")

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
                                gps = data.get('gps', {})
                                if gps and 'Latitude' in gps and 'Longitude' in gps:
                                    lat = gps.get('Latitude')
                                    lon = gps.get('Longitude')
                                    if lat != 0.0 and lon != 0.0:
                                        self.current_gps = (lat, lon)
                                        
                                aps = data.get('wifi', {}).get('aps', [])
                                for ap in aps:
                                    if self.current_gps[0] is not None:
                                        ap['gps_lat'] = self.current_gps[0]
                                        ap['gps_lon'] = self.current_gps[1]
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
                                        if self.current_gps[0] is not None:
                                            if 'data' not in event:
                                                event['data'] = {}
                                            if 'ap' in event['data']:
                                                event['data']['ap']['gps_lat'] = self.current_gps[0]
                                                event['data']['ap']['gps_lon'] = self.current_gps[1]
                                            else:
                                                event['data']['gps_lat'] = self.current_gps[0]
                                                event['data']['gps_lon'] = self.current_gps[1]
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
