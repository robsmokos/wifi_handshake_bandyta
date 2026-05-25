$kali_ip = "192.168.2.108"
$kali_user = "kali"
$target_dir = "/home/kali/skanerb"

Write-Host "============================================="
Write-Host "Wdrażanie projektu na Raspberry Pi Zero (Kali)"
Write-Host "IP: $kali_ip"
Write-Host "Użytkownik: $kali_user"
Write-Host "Katalog: $target_dir"
Write-Host "Hasło: kali (zostaniesz poproszony o hasło)"
Write-Host "============================================="

# Tworzenie katalogu docelowego na malince
Write-Host " "
Write-Host "[1/2] Tworzenie struktury katalogów na Kali..."
ssh ${kali_user}@${kali_ip} "mkdir -p $target_dir/core $target_dir/handshakes"

# Kopiowanie plików
Write-Host " "
Write-Host "[2/2] Kopiowanie plików źródłowych przez SCP..."
scp skrypt_startowy.sh main.py requirements.txt plan_projektu.md ${kali_user}@${kali_ip}:${target_dir}/
scp -r core/* ${kali_user}@${kali_ip}:${target_dir}/core/

Write-Host " "
Write-Host "============================================="
Write-Host "Wdrażanie zakończone sukcesem!"
Write-Host "Aby uruchomić skrypt, zaloguj się na Kali:"
Write-Host "ssh ${kali_user}@${kali_ip}"
Write-Host "cd $target_dir"
Write-Host "chmod +x skrypt_startowy.sh"
Write-Host "sudo ./skrypt_startowy.sh wlan0"
Write-Host "============================================="
