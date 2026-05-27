import asyncio
from core.database import Database
from core.bettercap_api import BettercapAPI
from core.brain import Brain
from core.executor import Executor
import sys
import time
from aiohttp import web
from web import WebServer

async def status_bar(db, event_queue, attack_queue, state):
    """Odświeża statystyki i rysuje TUI (Text User Interface) w dolnej części ekranu."""
    last_db_query = 0
    aps = []
    total, captured = 0, 0
    
    # Ukryj kursor i wyczyść ekran na starcie
    sys.stdout.write("\033[?25l\033[2J\033[H")
    sys.stdout.flush()
    
    while True:
        try:
            if state.get('pause_ui', False):
                await asyncio.sleep(0.2)
                continue
                
            
            now = time.time()
            if now - last_db_query > 2.0:
                total, captured = await db.get_stats()
                aps = await db.get_top_aps(limit=8)
                last_db_query = now
                
            # Powrót do pozycji home
            lines = ["\033[H\033[1mBSSID             | ESSID                | ATK | STATUS\033[0m"]
            
            for ap in aps:
                atk_str = f"{ap.get('liczba_atakow_deauth', 0)}/{ap.get('liczba_atakow_pmkid', 0)}"
                essid = str(ap.get('essid') or '<ukryte>')[:20]
                status = ap.get('status', 'nowy')
                color = "\033[92m" if 'przechwycono' in status else ""
                reset = "\033[0m" if color else ""
                lines.append(f"\033[K{color}{ap['bssid']:17} | {essid:20} | {atk_str:3} | {status[:15]}{reset}")
            
            # Wypełnienie pustych linii by ramka nie skakała na starcie
            for _ in range(8 - len(aps)):
                lines.append("\033[K")
                
            action = state.get('action', 'Skanowanie eteru...')
            lines.append(f"\033[K{action}")
            lines.append(f"\033[K\033[1mAP:\033[0m {total} | \033[1mPrzechwycone:\033[0m {captured} | \033[1mQ(Ev/Atk):\033[0m {event_queue.qsize()}/{attack_queue.qsize()}")
            
            # Wyczyść pozostałość pod panelem
            lines.append("\033[J")
            output = "\n".join(lines)
            sys.stdout.write(output)
            sys.stdout.flush()
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            break
        except Exception as e:
            with open("/home/kali/skanerb/core/error.log", "a") as f:
                f.write(f"UI Error: {e}\n")
            await asyncio.sleep(1)

async def start_web_server(db, shared_state):
    """Asynchronicznie uruchamia serwer WWW na porcie 8080."""
    ws = WebServer(db, shared_state)
    app = web.Application()
    app.router.add_get('/', ws.get_index)
    app.router.add_get('/api/stats', ws.get_stats)
    app.router.add_get('/api/aps', ws.get_aps)
    app.router.add_get('/api/ap', ws.get_ap_details)
    app.router.add_get('/api/dashboard_stats', ws.get_dashboard_stats)
    # Obsługa statycznego pobierania handshake'ów z folderu handshakes
    app.router.add_static('/handshakes/', path='handshakes', name='handshakes')
    
    # access_log=None wycisza logi HTTP, zapobiegając rozbijaniu dolnego panelu TUI w tmuxie
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

async def main():
    # Inicjalizacja komponentów
    db = Database("handshakes.db")
    await db.init_db()

    # Zabezpieczenia: maxsize zapobiega OOM (brak pamięci na Raspberry Pi)
    event_queue = asyncio.Queue(maxsize=500)
    attack_queue = asyncio.Queue(maxsize=50)
    shared_state = {'action': 'Skanowanie eteru...'}

    api = BettercapAPI(event_queue, username="kali", password="kali")
    brain = Brain(db, event_queue, attack_queue)
    executor = Executor(db, api, attack_queue, brain, shared_state)

    # Uruchomienie serwera WWW w tej samej pętli asyncio
    await start_web_server(db, shared_state)

    # Uruchomienie zadań współbieżnych
    tasks = [
        asyncio.create_task(api.event_stream_listener()),
        asyncio.create_task(brain.process_events()),
        asyncio.create_task(executor.run()),
        asyncio.create_task(status_bar(db, event_queue, attack_queue, shared_state))
    ]

    # Zatrzymanie głównego wątku, aż zadania (nigdy) nie wygasną
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nZamykanie programu...")
