$kali_ip = "192.168.2.108"
$kali_user = "kali"
$target_dir = "/home/kali/skanerb"

Write-Host "============================================="
Write-Host "Wdrazanie projektu na Raspberry Pi Zero (Kali)"
Write-Host "IP: $kali_ip"
Write-Host "Uzytkownik: $kali_user"
Write-Host "Katalog: $target_dir"
Write-Host "Haslo: kali (zostaniesz poproszony o haslo)"
Write-Host "============================================="

# Tworzenie katalogu docelowego na malince
Write-Host " "
Write-Host "[1/2] Tworzenie struktury katalogow na Kali..."
ssh ${kali_user}@${kali_ip} "mkdir -p $target_dir/core $target_dir/handshakes"

# Kopiowanie plikow
Write-Host " "
Write-Host "[2/2] Kopiowanie plikow zrodlowych przez SCP..."
scp skrypt_startowy.sh main.py web.py requirements.txt plan_projektu.md ${kali_user}@${kali_ip}:${target_dir}/
scp -r core/* ${kali_user}@${kali_ip}:${target_dir}/core/

Write-Host " "
Write-Host "============================================="
Write-Host "Wdrazanie zakonczone sukcesem!"
Write-Host "Aby uruchomic skrypt, zaloguj sie na Kali:"
Write-Host "ssh $kali_user@$kali_ip"
Write-Host "cd $target_dir"
Write-Host "chmod +x skrypt_startowy.sh"
Write-Host "sudo ./skrypt_startowy.sh wlan0"
Write-Host "============================================="
