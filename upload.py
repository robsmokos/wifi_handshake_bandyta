import paramiko
import sys
import os

host = '192.168.2.108'
user = 'kali'
password = 'kali'

local_files = [
    (r'c:\DATA\ROB\AI\Programista\bettercup\web.py', '/home/kali/skanerb/web.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\main.py', '/home/kali/skanerb/main.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\core\bettercap_api.py', '/home/kali/skanerb/core/bettercap_api.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\core\brain.py', '/home/kali/skanerb/core/brain.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\core\database.py', '/home/kali/skanerb/core/database.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\migrate_db.py', '/home/kali/skanerb/migrate_db.py'),
    (r'c:\DATA\ROB\AI\Programista\bettercup\skrypt_startowy.sh', '/home/kali/skanerb/skrypt_startowy.sh')
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    print(f"Connecting to {host}...")
    ssh.connect(host, username=user, password=password, timeout=10)
    
    print("Opening SFTP session...")
    sftp = ssh.open_sftp()
    
    for local_path, remote_path in local_files:
        print(f"Uploading {local_path} to {remote_path}...")
        sftp.put(local_path, remote_path)
    
    sftp.close()
    
    print("Running database migration...")
    stdin, stdout, stderr = ssh.exec_command("cd skanerb && sudo python3 migrate_db.py")
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    print("Restarting bettercup processes via sudo...")
    ssh.exec_command("sudo tmux kill-session -t wifi_collector")
    ssh.exec_command("cd skanerb && sudo ./skrypt_startowy.sh wlan1")
    print("Upload, migration, and restart complete.")
except Exception as e:
    print("ERROR:", e)
finally:
    ssh.close()
