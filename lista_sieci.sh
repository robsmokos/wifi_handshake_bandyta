#!/bin/bash
sqlite3 -header -column /home/kali/skanerb/handshakes.db "SELECT bssid, essid, vendor, status FROM handshakes ORDER BY last_seen DESC;"
