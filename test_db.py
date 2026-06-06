import sqlite3
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.2.108', username='kali', password='kali')
stdin, stdout, stderr = client.exec_command('cd skanerb && sqlite3 handshakes.db "SELECT count(*), type FROM (SELECT typeof(gps_lat) as type FROM handshakes) GROUP BY type;"')
print("TYPES:", stdout.read().decode())

stdin, stdout, stderr = client.exec_command('cd skanerb && sqlite3 handshakes.db "SELECT id, gps_lat, gps_lon FROM handshakes WHERE gps_lat IS NOT NULL AND typeof(gps_lat) != \'null\' LIMIT 5;"')
print("ROWS:", stdout.read().decode())
