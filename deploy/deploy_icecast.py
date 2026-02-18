"""
Деплой Icecast + Source для NAVO RADIO.
Запуск: python deploy/deploy_icecast.py
"""
import os
import paramiko

HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = "root"
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD", "hdp-k.PD6u8K7U")
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

        print("2. Создание директорий Icecast...")
        run(client, "mkdir -p /var/log/icecast2 /var/run/icecast2", check=False)

        print("3. Копирование конфигов...")
        sftp = client.open_sftp()
        for f in ["icecast.xml", "icecast-navoradio.service", "navo-radio-source.service"]:
            local = os.path.join(SCRIPT_DIR, f)
            if os.path.exists(local):
                remote = f"{APP}/deploy/{f}"
                sftp.put(local, remote)
        sftp.close()

        print("4. Systemd...")
        run(client, f"cp {APP}/deploy/icecast-navoradio.service /etc/systemd/system/")
        run(client, f"cp {APP}/deploy/navo-radio-source.service /etc/systemd/system/")
        run(client, "systemctl daemon-reload")
        run(client, "systemctl enable icecast-navoradio navo-radio-source")
        run(client, "systemctl start icecast-navoradio")
        run(client, "sleep 2")
        run(client, "systemctl start navo-radio-source")

        print("5. Nginx...")
        with open(os.path.join(SCRIPT_DIR, "nginx-navoradio.conf"), "r", encoding="utf-8") as f:
            nginx = f.read()
        sftp = client.open_sftp()
        with sftp.file("/etc/nginx/sites-available/navoradio", "w") as r:
            r.write(nginx)
        sftp.close()
        run(client, "nginx -t")
        run(client, "systemctl reload nginx")

        print("6. Проверка...")
        out, _, _ = run(client, "systemctl is-active icecast-navoradio", check=False)
        print(f"   icecast-navoradio: {out.strip()}")
        out, _, _ = run(client, "systemctl is-active navo-radio-source", check=False)
        print(f"   navo-radio-source: {out.strip()}")

        print("\nГотово. Эфир: https://navoradio.com/stream")
    finally:
        client.close()


if __name__ == "__main__":
    main()
