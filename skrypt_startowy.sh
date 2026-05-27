#!/bin/bash

# Przejdź do katalogu skryptu
cd "$(dirname "$0")"

# Domyślnie uruchamia wlan0, jeśli nie podano inaczej
IFACE=${1:-wlan0}

mkdir -p handshakes

# Generowanie tymczasowego capletu Bettercap z ustawieniami API
cat <<EOF > bettercap_config.cap
set api.rest.port 8081
set api.rest.username kali
set api.rest.password kali
set wifi.recon.channel clear
set wifi.handshakes.file handshakes/handshakes.pcap
wifi.recon on
api.rest on
gps on
EOF

echo "Uruchamianie środowiska dla interfejsu $IFACE..."

# Tworzenie sesji tmux: góra bettercap, dół podzielony pionowo (lewo: python, prawo: shell)
tmux new-session -d -s wifi_collector "bettercap -iface $IFACE -caplet bettercap_config.cap || sleep 60"
tmux split-window -t wifi_collector -v -p 65 "python3 main.py || sleep 60"
tmux split-window -t wifi_collector.1 -h
#tmux attach-session -t wifi_collector
