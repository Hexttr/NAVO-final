"""
Деплой NAVO-final на сервер Ubuntu (navoradio.com).
Запуск: python deploy_to_server.py [--dry-run]

Требования:
- Перед деплоем: git push origin ubuntu (чтобы ветка ubuntu была на GitHub)
- На сервере: .env с API ключами (JAMENDO_CLIENT_ID, GROQ_API_KEY, WEATHER_API_KEY)
"""
import paramiko
import sys
import os

# === НАСТРОЙКИ (изменить при необходимости) ===
HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = os.environ.get("NAVO_SSH_USER", "root")
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD", "hdp-k.PD6u8K7U")
REPO_URL = "https://github.com/Hexttr/NAVO-final.git"
BRANCH = "ubuntu"
APP_DIR = "/opt/navo-radio"


def run(ssh, cmd, check=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if check and code != 0:
        raise RuntimeError(f"Command failed ({code}): {cmd}\nstderr: {err}")
    return out, err, code


def main(dry_run=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print("Подключение к серверу...")
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
        print("Подключено.\n")
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        return 1

    prefix = "[DRY] " if dry_run else ""

    try:
        # 1. Клонирование / обновление репозитория
        out, _, code = run(client, f"test -d {APP_DIR}/.git", check=False)
        if code != 0:
            print(f"{prefix}Клонирование репозитория...")
            if not dry_run:
                run(client, f"rm -rf {APP_DIR}")
                run(client, f"git clone {REPO_URL} {APP_DIR}")
                run(client, f"cd {APP_DIR} && git fetch origin && (git checkout {BRANCH} 2>/dev/null || git checkout main)")
        else:
            print(f"{prefix}Обновление репозитория...")
            if not dry_run:
                run(client, f"cd {APP_DIR} && git fetch origin && (git checkout {BRANCH} 2>/dev/null || git checkout main) && git reset --hard origin/{BRANCH} 2>/dev/null || git reset --hard origin/main")

        # 2. Проверка .env
        if not dry_run:
            out, _, code = run(client, f"test -f {APP_DIR}/.env", check=False)
            if code != 0:
                print("ВНИМАНИЕ: .env не найден. Скопируйте .env.example в .env и заполните ключи.")
                run(client, f"cp {APP_DIR}/.env.example {APP_DIR}/.env")

        # 3. Backend: venv + зависимости
        print(f"{prefix}Установка backend...")
        if not dry_run:
            run(client, f"cd {APP_DIR} && python3 -m venv venv")
            run(client, f"{APP_DIR}/venv/bin/pip install -q -r {APP_DIR}/backend/requirements.txt")

        # 4. Frontend: npm install + build
        print(f"{prefix}Сборка frontend...")
        if not dry_run:
            run(client, f"cd {APP_DIR}/frontend && npm ci --silent 2>/dev/null || npm install --silent")
            run(client, f"cd {APP_DIR}/frontend && VITE_API_URL=https://navoradio.com npm run build")

        # 5. Nginx config
        print(f"{prefix}Обновление nginx...")
        if not dry_run:
            with open(os.path.join(script_dir, "nginx-navoradio.conf"), "r", encoding="utf-8") as f:
                nginx_conf = f.read()
            sftp = client.open_sftp()
            with sftp.file("/etc/nginx/sites-available/navoradio", "w") as remote:
                remote.write(nginx_conf)
            sftp.close()
            run(client, "nginx -t")
            run(client, "systemctl reload nginx")

        # 6. Systemd services
        print(f"{prefix}Обновление systemd...")
        if not dry_run:
            sftp = client.open_sftp()
            for svc_name, local_file in [("navo-radio", "navo-radio.service"), ("navo-radio-source", "navo-radio-source.service")]:
                local_path = os.path.join(script_dir, local_file)
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as f:
                        svc = f.read()
                    with sftp.file(f"/etc/systemd/system/{svc_name}.service", "w") as remote:
                        remote.write(svc)
            sftp.close()
            run(client, "systemctl daemon-reload")
            run(client, "systemctl enable navo-radio")
            run(client, "systemctl restart navo-radio")
            out, _, code = run(client, "systemctl is-active navo-radio-source", check=False)
            if code == 0:
                run(client, "systemctl restart navo-radio-source")

        print("\nГотово!")
        if not dry_run:
            out, _, _ = run(client, "systemctl is-active navo-radio", check=False)
            print(f"navo-radio.service: {out.strip()}")

    except Exception as e:
        print(f"Ошибка: {e}")
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    sys.exit(main(dry_run=dry))
