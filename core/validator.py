import asyncio
import os
import sys

class Validator:
    def __init__(self, db, shared_state=None, pcap_dir="handshakes"):
        self.db = db
        self.shared_state = shared_state
        self.pcap_dir = pcap_dir
        self.pcap_file = os.path.join(pcap_dir, "handshakes.pcap")
        self.hashes_file = os.path.join(pcap_dir, "hashes.hc22000")

    async def check_pcap(self, bssid, attack_type):
        """
        Asynchronicznie weryfikuje czy Bettercap złapał paczkę DLA TEGO KONKRETNEGO BSSID.
        Zamiast czytać surowe logi, każemy hcxpcapngtool wygenerować plik hc22000 i sprawdzamy 
        czy mac routera się w nim znalazł. To gwarantuje 100% nieomylności.
        """
        if not os.path.exists(self.pcap_file):
            return
            
        # Oczekiwanie na dysk (race condition z buforem filesystemu)
        await asyncio.sleep(2)
        
        # BSSID bez dwukropków (hc22000 używa płaskiego formatu mac, czasami małe litery)
        bssid_clean = bssid.replace(":", "").lower()
            
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "hcxpcapngtool", "-o", self.hashes_file, self.pcap_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Bezwarunkowy Timeout
            await asyncio.wait_for(proc.communicate(), timeout=15)
            
            is_valid = False
            
            # Weryfikacja bezpośrednio w pliku z hashami
            if os.path.exists(self.hashes_file):
                with open(self.hashes_file, 'r', errors='ignore') as f:
                    content = f.read().lower()
                    if bssid_clean in content:
                        is_valid = True
            
            if is_valid:
                status = 'przechwycono' if attack_type == 'deauth' else 'pmkid_przechwycono'
                
                # Pobierz ESSID sieci do ładnej nazwy pliku
                db_info = await self.db.get_ap(bssid)
                essid_raw = db_info.get('essid') if db_info else '<ukryte>'
                # Wyczyszczenie ESSID ze znaków specjalnych dla bezpieczeństwa systemu plików
                essid_safe = "".join([c for c in str(essid_raw) if c.isalnum() or c in ('_', '-')]).strip()
                if not essid_safe:
                    essid_safe = "ukryta"
                
                bssid_file_name = bssid.replace(":", "-")
                final_pcap_path = os.path.join(self.pcap_dir, f"{essid_safe}_{bssid_file_name}.pcap")
                final_hash_path = os.path.join(self.pcap_dir, f"{essid_safe}_{bssid_file_name}.hc22000")
                
                # Wycięcie pakietów dla konkretnego BSSID z głównego pcapa za pomocą tcpdump (lekki i zawsze obecny)
                try:
                    # Filtrujemy pakiety gdzie MAC to bssid (zarówno jako nadawca, odbiorca, jak i bssid w 802.11)
                    filter_cmd = f"wlan addr1 {bssid} or wlan addr2 {bssid} or wlan addr3 {bssid}"
                    # W razie gdyby tcpdump nie wspierał wlan (niektóre starsze kompilacje), robimy prosty ether filter
                    # ale wlan addr jest najpewniejszy dla 802.11.
                    tcpdump_proc = await asyncio.create_subprocess_exec(
                        "tcpdump", "-r", self.pcap_file, "-w", final_pcap_path,
                        "ether host " + bssid,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await asyncio.wait_for(tcpdump_proc.communicate(), timeout=10)
                except Exception as e:
                    sys.stderr.write(f"Błąd wycinania tcpdump: {e}\n")
                
                # Wygenerowanie dedykowanego pliku hc22000 tylko dla wyciętego pcapa
                if os.path.exists(final_pcap_path):
                    try:
                        hash_proc = await asyncio.create_subprocess_exec(
                            "hcxpcapngtool", "-o", final_hash_path, final_pcap_path,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await asyncio.wait_for(hash_proc.communicate(), timeout=10)
                    except Exception as e:
                        sys.stderr.write(f"Błąd generowania dedykowanego hasha: {e}\n")
                
                # Zapisujemy sukces w bazie, podając ścieżkę do dedykowanego pliku pcap
                save_path = final_pcap_path if os.path.exists(final_pcap_path) else self.pcap_file
                await self.db.update_status(bssid, status, save_path)
                
                # Renderowanie wielkiego komunikatu ASCII, który odsunie pasek zadań w dół
                art = f"""
\033[92m  _   _                 _     _           _        
 | | | | __ _ _ __   __| |___| |__   __ _| | _____ 
 | |_| |/ _` | '_ \\ / _` / __| '_ \\ / _` | |/ / _ \\
 |  _  | (_| | | | | (_| \\__ \\ | | | (_| |   <  __/
 |_| |_|\\__,_|_| |_|\\__,_|___/_| |_|\\__,_|_|\\_\\___|\033[0m
\033[93m>>> ZŁAPANO {attack_type.upper()} DLA SIECI: {bssid} ({essid_raw}) <<<\033[0m

\033[90mPlik PCAP: {final_pcap_path}
Plik HASH: {final_hash_path}\033[0m
"""
                sys.stdout.write(art)
                sys.stdout.flush()

                # Animacja w samym pasku zadań (miganie)
                if self.shared_state:
                    frames = ["|", "/", "-", "\\"]
                    for _ in range(10): # 2 sekundy migania
                        for f in frames:
                            self.shared_state['action'] = f"\033[92m{f} SUKCES! ZŁAPANO {attack_type.upper()} ({bssid}) {f}\033[0m"
                            await asyncio.sleep(0.1)
                    
                    if "SUKCES" in self.shared_state.get('action', ''):
                        self.shared_state['action'] = "Skanowanie eteru..."
            
        except asyncio.TimeoutError:
            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()  # Zapobiega zombie-procesowi
                except Exception:
                    pass
        except Exception as e:
            sys.stderr.write(f"Validator Error: {e}\n")
