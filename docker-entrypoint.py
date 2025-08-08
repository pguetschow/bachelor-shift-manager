import time
import socket
import subprocess

print('Waiting for MySQL...')
while True:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('db', 3306))
        sock.close()
        if result == 0:
            break
    except Exception:
        pass
    print('MySQL not ready, waiting...')
    time.sleep(2)

print('MySQL ready! Starting Django...')
time.sleep(2)

subprocess.run(['python', 'manage.py', 'migrate'], check=True)
subprocess.run(['python', 'manage.py', 'collectstatic', '--noinput'], check=True)
subprocess.run(['python', 'manage.py', 'runserver', '0.0.0.0:8000'], check=True)
