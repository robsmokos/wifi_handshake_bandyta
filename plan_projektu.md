# Projekt: Zbieracz Handshake'ów Wi-Fi (Bettercap + SQLite)

Aplikacja służąca do automatycznego przechwytywania handshake'ów WPA/WPA2 z sieci Wi-Fi przy wykorzystaniu narzędzia `bettercap` oraz bazy danych `SQLite`.

## Założenia Projektowe i Środowisko
1. **Platforma Sprzętowa**: **Raspberry Pi Zero 2W** z systemem **Kali Linux**. Kod będzie maksymalnie zoptymalizowany pod kątem oszczędności CPU (dłuższe uśpienia, asyncio) i żywotności karty SD (brak plików tymczasowych).
2. **Architektura Asynchroniczna (Asyncio)**: Cała aplikacja zostanie zbudowana w oparciu o asynchroniczną pętlę zdarzeń `asyncio`. Użycie bibliotek takich jak `aiohttp` do komunikacji z API oraz `aiosqlite` do bazy danych pozwoli na równoległe skanowanie, nasłuchiwanie oraz walidację bez blokowania (zamrażania) programu głównego, co niesamowicie odciąży Pi Zero.
3. **Projekt Akademicki**: Aplikacja przeznaczona do użytku w kontrolowanym środowisku laboratoryjnym na własnych punktach dostępowych (AP).
4. **Pełna Automatyzacja**: Program działa w pełni automatycznie.
5. **Podgląd na żywo (tmux)**: Ekran podzielony w poziomie (góra logi Bettercap, dół skrypt Python ze statystykami `AP: 125 | Przechwycone: 10`).
6. **Karty Wi-Fi (Tryby Uruchamiania)**: Oprogramowanie pozwoli na wybór trybu działania podczas startu za pomocą flag w `skrypt_startowy.sh` (np. `-i wlan0` lub `-i wlan0 -a wlan1`).
   - *Tryb 1 Karty (Domyślny)*: Bettercap sam wstrzymuje skanowanie na ułamek sekundy, rzuca deauth i wraca. Najbardziej optymalne dla Pi Zero ze względu na oszczędność zasilania.
   - *Tryb 2 Kart (Skaner + Strzelec)*: System uruchomi **dwie osobne sesje Bettercap** w tle na różnych portach API. Karta A (np. `wlan0`) będzie skakać po kanałach bez żadnych przerw, dostarczając dane do bazy. Karta B (np. `wlan1`) będzie czekać w ukryciu, aż Python wyda jej rozkaz przeskoczenia na konkretny kanał i ataku (Deauth). Zapewnia to absolutną płynność procesu.

## Etapy Wdrożenia i Walidacji (Roadmap)

Projekt zostanie zaprogramowany w **5 odrębnych blokach**. Po ukończeniu każdego bloku nastąpi pauza na weryfikację jego działania, zanim przejdziemy do pisania kolejnego modułu.

### BLOK 1: Baza Danych i Podstawy Asynchroniczności
- **Co zrobimy**: Napiszemy asynchronicznego menedżera bazy danych (`core/database.py`) z wykorzystaniem `aiosqlite`, mechanizmem WAL i zrzutami (flush) co 15s.
- **Jak zwalidujemy**: Uruchomimy prosty skrypt testowy dodający fikcyjne sieci do bazy. Sprawdzimy, czy plik `handshakes.db` powstaje prawidłowo, czy RAM cache działa i czy dane zapisują się na dysku po 15 sekundach bez blokowania procesu.

### BLOK 2: Komunikacja ze Strumieniem Bettercap (Event Stream)
- **Co zrobimy**: Zbudujemy `core/bettercap_api.py`. Moduł połączy się przez `aiohttp` z endpointem `/api/events` (SSE), zaimplementuje *Exponential Backoff* na wypadek zerwania i będzie wypychał zdekodowane JSON-y do `Event Queue`.
- **Jak zwalidujemy**: Odpalimy ręcznie samego Bettercapa. Uruchomimy nasz skrypt, który będzie jedynie "drukował" na ekranie (print) to, co wpada do kolejki. Sprawdzimy, czy widzi pojawiające się nowe sieci i stacje w powietrzu.

### BLOK 3: Brain, Scoring i Integracja z Bazą
- **Co zrobimy**: Napiszemy `core/brain.py`. Moduł ten stanie się "Konsumentem", który pobiera dane z `Event Queue`, zapisuje informacje (w tym vendora, GPS) do bazy (Blok 1) i przelicza skomplikowany wzór punktacji.
- **Jak zwalidujemy**: Skrypt wyłapie sieci z powietrza (Blok 2), wrzuci je do bazy (Blok 1), i zacznie na żywo w konsoli listować "TOP 3 Cele" sortując je według naszego wzoru punktowego. Zobaczymy czy omija WPA3 i czy prawidłowo ocenia siłę sygnału.

### BLOK 4: Attack Queue i Executor (Egzekucja)
- **Co zrobimy**: Stworzymy proces wykonawczy. Najlepsze cele z Bloku 3 wpadną do `Attack Queue`. Executor zablokuje kanał (`wifi.recon.channel`), wyśle 3 serie pakietów z pauzami, poczeka na efekt i odblokuje kanał.
- **Jak zwalidujemy**: Skonfigurujemy specjalny telefon testowy połączony z ruterem testowym. Sprawdzimy, czy nasz Python samodzielnie rozłącza ten telefon, i czy po chwili Bettercap wypluwa plik `.pcap` na dysk.

### BLOK 5: Walidator hcxtools i Finisz (tmux)
- **Co zrobimy**: Napiszemy `core/validator.py` analizujący pliki pcap za pomocą `hcxpcapngtool`. Dodamy dynamiczny pasek statusu w konsoli i zepniemy to ze skryptem `start.sh` dla `tmuxa`.
- **Jak zwalidujemy**: Ostateczny "field test". Uruchomienie całości z jednego skryptu `.sh`. Ekran powinien się podzielić, system powinien sam atakować i weryfikować ułomne pcapy, aktualizując statystyki na samym dole.

---
## Korekty Wdrożeniowe (Post-Execution)
Podczas przenoszenia kodu do fizycznego środowiska na Raspberry Pi zidentyfikowano i zlikwidowano kilka poważnych błędów z logiką środowiska i bibliotek. Zmiany te są już wdrożone w skryptach na dysku:
1. **Aktywny REST Polling (Zamiast SSE)**: Dokumentacja Bettercapa w zakresie `events.stream` okazała się niespójna w najnowszej wersji dla ARM. Endpoint `/api/events` generował statyczną tablicę JSON zamiast ciągłego strumienia. Zmodyfikowano plik `bettercap_api.py`, by wymuszał standardowe pule zapytań asynchronicznych (REST Polling co 1s) i aktywnie zmuszał Bettercap do czyszczenia zapychającego się bufora komendą `events.clear`.
2. **Eliminacja Zakleszczenia (Deadlock) Bazy Danych**: Moduł `database.py` operujący na zabezpieczeniach pamięci ( `asyncio.Lock`) został przepisany by nie zamykał na kłódkę dostępu do metod, które korzystają z zagnieżdżonych wywołań wewnątrz tego samego wątku. Zapobiegło to całkowitemu zamrożeniu sztucznej inteligencji skanera.
3. **Konfiguracja API wewnątrz Capletu**: Od wersji Bettercap v2.41 przekazywanie argumentu `--api.rest.port` w komendzie bash nie jest obsługiwane. Konfigurację oraz bezpieczne poświadczenia (`kali:kali`) wpisano na twardo za pomocą komend `set` w procedurze generowania wielolinijkowego pliku `.cap`.
4. **Dynamiczny Interfejs Użytkownika (shared_state)**: W dolnym panelu `tmux` zamiast statycznego paska zadbano o mechanizm asynchronicznego wymieniania się zmienną ze statusem operacji. Pasek reaguje i wyświetla teksty takie jak `[ATAK DEAUTH na XX:YY...]` czy `[SUKCES! Złapano handshake]`, powiadamiając użytkownika o pracującym w tle skrypcie walidatora.

---
## Dane do Wdrożenia na Kali Linux (Raspberry Pi Zero)
W celu przerzucenia gotowego kodu na maszynę docelową, wykorzystany zostanie protokół SCP / SSH na poniższe dane dostępowe:
- **IP Urządzenia**: `192.168.2.108`
- **Login SSH**: `kali`
- **Hasło SSH**: `kali`
- **Katalog Docelowy**: `/home/kali/skanerb`

Do projektu dołączony został skrypt `deploy.ps1` (w Powershellu dla środowiska Windows), który po uruchomieniu automatycznie podłączy się do Malinki, stworzy folder `skanerb` i skopiuje tam wszystkie pliki pythona, zachowując bezpieczną strukturę katalogów.

## Architektura Rozwiązania

Skrypt komunikuje się asynchronicznie z procesem `bettercap` przez HTTP REST API.

### Architektura Potokowa (Producer-Consumer Pipeline):
Zamiast jednej chaotycznej pętli, aplikacja zostanie zbudowana jako elegancki potok (pipeline) oparty na asynchronicznych kolejkach (`asyncio.Queue`):

1. **Event Stream (Producent 1)**: `core/bettercap_api.py` utrzymuje połączenie ze strumieniem `/api/events`. Wdrożono **Exponential Backoff z Jitterem** – jeśli Bettercap się zrestartuje, skrypt ponawia połączenia asynchronicznie, unikając blokady pipeline'u.
   > **Żelazna zasada Timeoutów**: Każde zapytanie (I/O, bazy danych, API, walidator, `Queue.put`/`Queue.get`) w całym programie musi być obowiązkowo owinięte w `await asyncio.wait_for(task, timeout=X)`. Zapobiega to jakimkolwiek martwym punktom (deadlock) w aplikacji.
2. **Event Queue**: Bufor z limitem rozmiaru (`asyncio.Queue(maxsize=500)`). Chroni 512MB RAM Pi Zero przed wyczerpaniem (OOM) w bardzo zatłoczonym środowisku. Gdy kolejka jest pełna, najstarsze lub najmniej istotne eventy są zrzucane.
3. **Brain / Scoring (Konsument 1 / Producent 2)**: Logika `core/brain.py` pobiera dane z `Event Queue`. 
   - Wykonuje batch updates do `aiosqlite` (dbając o kartę SD w trybie WAL).
   - Odrzuca bezużyteczne sieci (WPA3, już złapane, słaby sygnał).
   - Wylicza **Score** dla celów: `score = klienci*5 + RSSI + bonus_nowej_sieci - porażki*10 - kara_za_ostatni_atak(time_since_last_attack)`. Kara maleje z czasem, zapobiegając obsesyjnemu atakowaniu w kółko najsilniejszego AP (wymusza rotację celów, "cooldown" naturalnie spada).
   - Najlepiej oceniony cel trafia do kolejki `Attack Queue`. Zaimplementowano **Deduplikację i TTL (Time-To-Live)**. Brain utrzymuje w RAM zbiór (Set) celów aktualnie czekających na atak, by uniknąć podwójnego wrzucania tego samego BSSID. Zlecenia starsze niż np. 60 sekund wygasają automatycznie (cel mógł zniknąć z zasięgu).
4. **Attack Queue**: Asynchroniczna kolejka (z `maxsize`) oczekujących "wyroków".
5. **Executor (Konsument 2)**: Niezależny proces pobierający cel:
   - **Blokada Kanału**: Wysyła `wifi.recon.channel X` i odczekuje moment.
   - **Atak**: Wysyła 3 serie po 5 pakietów `wifi.deauth` (lub 2-3 żądania `wifi.assoc`).
   - **Pauza**: Czeka na przechwycenie pliku, przywraca `wifi.recon.channel clear`.
6. **Bezwzględna Walidacja (hcxtools) i Race Condition**: Po zgłoszeniu utworzenia pcapa, Walidator włącza **Polling rozmiaru pliku (lub używa inotify)**. Upewnia się, że Bettercap całkowicie zamknął strumień zapisu pliku pcap. Dopiero gdy plik przestanie rosnąć, asynchronicznie odpala `hcxpcapngtool` filtrując fałszywe PMKID i M1/M2. W razie porażki cofa status w bazie.

## Struktura Bazy Danych
Zarządzana asynchronicznie z użyciem optymalizacji dla Pi (WAL, batch updates).
- `bssid` (PRIMARY KEY)
- `essid`
- `vendor` (Nazwa producenta sprzętu, pozyskana automatycznie przez Bettercap na podstawie MAC)
- `first_seen`
- `last_seen`
- `gps_lat` / `gps_lon`
- `sciezka_do_pliku`
- `czas_przechwycenia`
- `last_attacked_at` (Timestamp ostatniego ataku - rozwiązuje problem "świeżego startu" i pozwala na wyliczanie kary czasowej w Scoringu)
- `liczba_atakow_deauth`
- `liczba_atakow_pmkid`
- `status` ('nowy', 'niekompletny', 'przechwycono', 'pmkid_przechwycono')

## Proponowana Struktura Plików (Pełny Async)
#### `skrypt_startowy.sh`
Tworzy sesję tmux i w zależności od argumentów uruchamia procesy.
- Tryb 1 karty (`./start.sh -i wlan0`): Góra to logi jednej sesji Bettercap, dół to Python.
- Tryb 2 kart (`./start.sh -i wlan0 -a wlan1`): Góra to dwie zminiaturyzowane instancje Bettercap (skaner na API port 8081, strzelec na API port 8082), dół to Python zasilający oba porty.
#### `core/database.py`
Wykorzystuje `aiosqlite`. Cacheuje zapytania w pamięci RAM i zrzuca je asynchronicznie (np. co 15 sekund).
#### `core/bettercap_api.py`
Wykorzystuje `aiohttp` do nieblokujących zapytań REST oraz utrzymuje bezustanne połączenie nasłuchujące ze strumieniem `/api/events`.
#### `core/brain.py`
Asynchroniczna logika scoringu i decyzyjności.
#### `core/validator.py`
Używa `asyncio.create_subprocess_exec` do odpalania i czytania wyjścia `hcxpcapngtool` w tle, nie paraliżując w tym czasie głównej pętli odświeżającej. Zapewnia błyskawiczną walidację EAPOL (M1/M2) oraz PMKID.
#### `main.py`
Główna pętla `async def main()` sterująca współbieżnie zadaniami (odświeżanie statystyk, skanowanie, ataki).


### do projektu dodaj atak typu Pixie Dust attack, jesli niemasz kodu zkopiuj z wifite, ataki beda przeprowadzanie tylko i wyłącznie na mją sieć testoą


https://github.com/robsmokos/wifi_handshake_bandyta.git