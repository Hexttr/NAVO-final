"""
Деплой Icecast + Source для NAVO RADIO.
Запуск: python deploy/deploy_icecast.py
Пароли Icecast берутся из локального .env (ICECAST_SOURCE_PASSWORD, ICECAST_ADMIN_PASSWORD).
"""
import base64
import os
from pathlib import Path

import paramiko
from dotenv import load_dotenv

# Загружаем .env из корня проекта
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = "root"
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD")
ICECAST_SOURCE_PW = os.environ.get("ICECAST_SOURCE_PASSWORD")
ICECAST_ADMIN_PW = os.environ.get("ICECAST_ADMIN_PASSWORD")

if not PASSWORD:
    raise SystemExit("NAVO_SSH_PASSWORD не задан. Укажите в .env.")
if not ICECAST_SOURCE_PW:
    raise SystemExit("ICECAST_SOURCE_PASSWORD не задан в .env.")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP = "/opt/navo-radio"


def run(ssh, cmd, check=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if check and code != 0:
        raise RuntimeError(f"Failed ({code}): {cmd}\n{err}")
    return out, err, code


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    try:
        print("0. Обновление кода...")
        run(client, f"cd {APP} && git fetch origin && git checkout ubuntu && git pull origin ubuntu", check=False)

        print("1. Установка Icecast2...")
        run(client, "apt-get update -qq && apt-get install -y -qq icecast2", check=False)

        print("2. Настройка Icecast (порт 8001)...")
        run(client, "cp /etc/icecast2/icecast.xml /etc/icecast2/icecast.xml.bak 2>/dev/null; true", check=False)
        run(client, "sed -i 's/<port>8000<\\/port>/<port>8001<\\/port>/' /etc/icecast2/icecast.xml 2>/dev/null; true", check=False)
        # Подставляем пароли из .env (base64 — безопасно для спецсимволов)
        pw_b64 = base64.b64encode(ICECAST_SOURCE_PW.encode()).decode()
        admin_b64 = base64.b64encode((ICECAST_ADMIN_PW or ICECAST_SOURCE_PW).encode()).decode()
        py_script = f"""import base64,re
pw=base64.b64decode('{pw_b64}').decode()
adm=base64.b64decode('{admin_b64}').decode()
p='/etc/icecast2/icecast.xml'
with open(p) as f:c=f.read()
c=re.sub(r'<source-password>.*?</source-password>',f'<source-password>{{pw}}</source-password>',c)
c=re.sub(r'<relay-password>.*?</relay-password>',f'<relay-password>{{pw}}</relay-password>',c)
c=re.sub(r'<admin-password>.*?</admin-password>',f'<admin-password>{{adm}}</admin-password>',c)
with open(p,'w') as f:f.write(c)"""
        run(client, f"python3 -c {repr(py_script)}")

        print("3. Копирование конфигов...")
        sftp = client.open_sftp()
        for f in ["navo-radio-source.service"]:
            local = os.path.join(SCRIPT_DIR, f)
            if os.path.exists(local):
                sftp.put(local, f"/etc/systemd/system/{f}")
        sftp.close()

        print("4. Systemd...")
        run(client, "systemctl enable icecast2")
        run(client, "systemctl restart icecast2")
        run(client, "sleep 2")
        run(client, "systemctl daemon-reload")
        run(client, "systemctl enable navo-radio-source")
        run(client, "systemctl restart navo-radio-source")

        print("5. Frontend...")
        run(client, f"cd {APP}/frontend && npm ci --silent 2>/dev/null || npm install --silent")
        run(client, f"cd {APP}/frontend && VITE_API_URL=https://navoradio.com npm run build")

        print("6. Nginx...")
        with open(os.path.join(SCRIPT_DIR, "nginx-navoradio.conf"), "r", encoding="utf-8") as f:
            nginx = f.read()
        sftp = client.open_sftp()
        with sftp.file("/etc/nginx/sites-available/navoradio", "w") as r:
            r.write(nginx)
        sftp.close()
        run(client, "nginx -t")
        run(client, "systemctl reload nginx")

        print("7. Проверка...")
        out, _, _ = run(client, "systemctl is-active icecast2", check=False)
        print(f"   icecast2: {out.strip()}")
        out, _, _ = run(client, "systemctl is-active navo-radio-source", check=False)
        print(f"   navo-radio-source: {out.strip()}")

        print("\nГотово. Эфир: https://navoradio.com/stream")
    finally:
        client.close()


if __name__ == "__main__":
    main()
