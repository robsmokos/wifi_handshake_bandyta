import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.2.108', username='kali', password='kali')
stdin, stdout, stderr = client.exec_command('cd skanerb && sqlite3 handshakes.db "SELECT id, bssid, essid, gps_lat, gps_lon FROM handshakes WHERE gps_lat IS NOT NULL AND gps_lat != \\"\\";"')
print(stdout.read().decode())
