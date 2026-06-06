import paramiko
import os

host = '192.168.2.108'
user = 'kali'
password = 'kali'
remote_base = '/home/kali/skanerb'

files_to_upload = [
    ('web.py', f'{remote_base}/web.py'),
    ('main.py', f'{remote_base}/main.py'),
    ('core/database.py', f'{remote_base}/core/database.py'),
    ('migrate_db.py', f'{remote_base}/migrate_db.py'),
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect(host, username=user, password=password, timeout=15)
    sftp = ssh.open_sftp()
    for local_path, remote_path in files_to_upload:
        print(f'Uploading {local_path} -> {remote_path}')
        sftp.put(local_path, remote_path)
        print(f'  OK')
    sftp.close()
    print('\nWszystkie pliki wgrane pomyslnie!')

    # Uruchom migrację DB
    print('\nUruchamiam migracje bazy danych...')
    stdin, stdout, stderr = ssh.exec_command(
        "cd /home/kali/skanerb && python3 migrate_db.py"
    )
    out = stdout.read().decode('utf-8').strip()
    err = stderr.read().decode('utf-8').strip()
    print('STDOUT:', out)
    if err:
        print('STDERR:', err)

    # Restart main.py
    print('\nRestartuje main.py...')
    ssh.exec_command("sudo pkill -f 'python3 main.py'")
    import time; time.sleep(1)
    stdin, stdout, stderr = ssh.exec_command(
        "sudo tmux send-keys -t wifi_collector:0.1 'cd /home/kali/skanerb && sudo python3 main.py' Enter"
    )
    stdout.read()
    print('Restart OK')

except Exception as e:
    print('ERROR:', e)
finally:
    ssh.close()
