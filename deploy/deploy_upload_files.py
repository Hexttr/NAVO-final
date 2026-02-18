"""
Загрузка изменённых файлов на сервер (без git push).
Запуск: python deploy/deploy_upload_files.py
"""
import os
import paramiko

HOST = os.environ.get("NAVO_SSH_HOST", "195.133.63.34")
USER = os.environ.get("NAVO_SSH_USER", "root")
PASSWORD = os.environ.get("NAVO_SSH_PASSWORD", "hdp-k.PD6u8K7U")
APP_DIR = "/opt/navo-radio"

# Локальные пути -> удалённые пути (добавляйте при изменении)
FILES = [
    ("backend/services/streamer_service.py", f"{APP_DIR}/backend/services/streamer_service.py"),
    ("backend/services/broadcast_service.py", f"{APP_DIR}/backend/services/broadcast_service.py"),
    ("backend/services/broadcast_generator.py", f"{APP_DIR}/backend/services/broadcast_generator.py"),
    ("backend/icecast_source.py", f"{APP_DIR}/backend/icecast_source.py"),
    ("backend/routes/broadcast.py", f"{APP_DIR}/backend/routes/broadcast.py"),
    ("backend/routes/podcasts.py", f"{APP_DIR}/backend/routes/podcasts.py"),
    ("backend/routes/intros.py", f"{APP_DIR}/backend/routes/intros.py"),
    ("frontend/src/api.js", f"{APP_DIR}/frontend/src/api.js"),
    ("frontend/src/pages/admin/Broadcast.jsx", f"{APP_DIR}/frontend/src/pages/admin/Broadcast.jsx"),
    ("frontend/src/pages/admin/Broadcast.css", f"{APP_DIR}/frontend/src/pages/admin/Broadcast.css"),
    ("frontend/src/pages/Player.jsx", f"{APP_DIR}/frontend/src/pages/Player.jsx"),
    ("frontend/src/pages/Player.css", f"{APP_DIR}/frontend/src/pages/Player.css"),
]


def run(ssh, cmd, check=True):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if check and code != 0:
        raise RuntimeError(f"Command failed ({code}): {cmd}\nstderr: {err}")
    return out, err, code


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print("Подключение к серверу...")
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
        print("Подключено.\n")

        sftp = client.open_sftp()

        for local_rel, remote_path in FILES:
            local_path = os.path.join(project_root, local_rel)
            if not os.path.exists(local_path):
                print(f"Пропуск (не найден): {local_rel}")
                continue
            print(f"Загрузка: {local_rel} -> {remote_path}")
            sftp.put(local_path, remote_path)

        sftp.close()

        print("\nСборка frontend...")
        run(client, f"cd {APP_DIR}/frontend && VITE_API_URL=https://navoradio.com npm run build", check=False)

        print("\nПерезапуск сервисов...")
        run(client, "systemctl restart navo-radio")
        run(client, "systemctl restart navo-radio-source")

        out, _, _ = run(client, "systemctl is-active navo-radio", check=False)
        print(f"navo-radio: {out.strip()}")
        out, _, _ = run(client, "systemctl is-active navo-radio-source", check=False)
        print(f"navo-radio-source: {out.strip()}")

        print("\nГотово!")

    except Exception as e:
        print(f"Ошибка: {e}")
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
