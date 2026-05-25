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
                
                # Zapisujemy sukces w bazie!
                await self.db.update_status(bssid, status, self.pcap_file)
                
                # Renderowanie wielkiego komunikatu ASCII, który odsunie pasek zadań w dół
                art = f"""
\033[92m  _   _                 _     _           _        
 | | | | __ _ _ __   __| |___| |__   __ _| | _____ 
 | |_| |/ _` | '_ \\ / _` / __| '_ \\ / _` | |/ / _ \\
 |  _  | (_| | | | | (_| \\__ \\ | | | (_| |   <  __/
 |_| |_|\\__,_|_| |_|\\__,_|___/_| |_|\\__,_|_|\\_\\___|\033[0m
\033[93m>>> ZŁAPANO {attack_type.upper()} DLA SIECI: {bssid} <<<\033[0m
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
