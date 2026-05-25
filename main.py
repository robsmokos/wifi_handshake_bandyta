import asyncio
from core.database import Database
from core.bettercap_api import BettercapAPI
from core.brain import Brain
from core.executor import Executor
import sys
import time

async def status_bar(db, event_queue, attack_queue, state):
    """Odświeża statystyki i rysuje TUI (Text User Interface) w dolnej części ekranu."""
    last_db_query = 0
    aps = []
    total, captured = 0, 0
    
    # Ukryj kursor terminala by nie mrugał
    sys.stdout.write("\033[?25l")
    
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
                
            # Zamiast czyścić ekran, po prostu jedziemy karetką do góry by nadpisać poprzednie linie TUI
            lines = ["\033[H\033[K\033[1mBSSID             | ESSID                | ATK | STATUS\033[0m"]
            
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
