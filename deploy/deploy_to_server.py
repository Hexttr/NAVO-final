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


def update_env_key_only(client, key_name, env_var_name):
    """Только обновить один ключ в .env на сервере. Для быстрого апдейта без полного деплоя."""
    val = os.environ.get(env_var_name, "").strip()
    if not val:
        return False
    sftp = client.open_sftp()
    with sftp.file(f"{APP_DIR}/.env", "r") as f:
        content = f.read().decode("utf-8", errors="replace")
    lines = content.splitlines()
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key_name}=") or (stripped.startswith("#") and f"{key_name}=" in stripped):
            new_lines.append(f"{key_name}={val}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key_name}={val}")
    with sftp.file(f"{APP_DIR}/.env", "w") as f:
        f.write("\n".join(new_lines) + "\n")
    sftp.close()
    return True


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

        # 2. Проверка .env и обновление ключей (если заданы NAVO_ELEVENLABS_API_KEY, NAVO_OPENAI_API_KEY)
        if not dry_run:
            out, _, code = run(client, f"test -f {APP_DIR}/.env", check=False)
            if code != 0:
                print("ВНИМАНИЕ: .env не найден. Скопируйте .env.example в .env и заполните ключи.")
                run(client, f"cp {APP_DIR}/.env.example {APP_DIR}/.env")
            keys_to_set = {}
            for env_key, line_key in [
                ("NAVO_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY"),
                ("NAVO_OPENAI_API_KEY", "OPENAI_API_KEY"),
            ]:
                val = os.environ.get(env_key, "").strip()
                if val:
                    keys_to_set[line_key] = val
            if keys_to_set:
                sftp = client.open_sftp()
                with sftp.file(f"{APP_DIR}/.env", "r") as f:
                    content = f.read().decode("utf-8", errors="replace")
                lines = content.splitlines()
                keys_found = set()
                new_lines = []
                for line in lines:
                    replaced = False
                    for k, v in keys_to_set.items():
                        stripped = line.strip()
                        if stripped == f"{k}=" or stripped.startswith(f"{k}=") or (stripped.startswith("#") and f"{k}=" in stripped):
                            new_lines.append(f"{k}={v}")
                            keys_found.add(k)
                            replaced = True
                            break
                    if not replaced:
                        new_lines.append(line)
                for k, v in keys_to_set.items():
                    if k not in keys_found:
                        new_lines.append(f"{k}={v}")
                with sftp.file(f"{APP_DIR}/.env", "w") as f:
                    f.write("\n".join(new_lines) + "\n")
                sftp.close()
                for k in keys_to_set:
                    print(f"Обновлён {k} в .env")

        # 3. Backend: venv + зависимости
        print(f"{prefix}Установка backend...")
        if not dry_run:
            run(client, f"cd {APP_DIR} && python3 -m venv venv")
            run(client, f"{APP_DIR}/venv/bin/pip install -q -r {APP_DIR}/backend/requirements.txt")

        # 4. Frontend: npm install + build (NODE_OPTIONS — лимит памяти, иначе OOM на слабых серверах)
        print(f"{prefix}Сборка frontend...")
        if not dry_run:
            run(client, f"cd {APP_DIR}/frontend && npm ci --silent 2>/dev/null || npm install --silent")
            run(client, f"cd {APP_DIR}/frontend && NODE_OPTIONS=--max-old-space-size=1536 VITE_API_URL=https://navoradio.com npm run build")

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


def key_and_restart(ssh):
    """Обновить ELEVENLABS_API_KEY в .env и перезапустить backend. Быстро, без полного деплоя."""
    val = os.environ.get("NAVO_ELEVENLABS_API_KEY", "").strip()
    if not val:
        print("Задайте NAVO_ELEVENLABS_API_KEY в окружении")
        return 1
    if update_env_key_only(ssh, "ELEVENLABS_API_KEY", "NAVO_ELEVENLABS_API_KEY"):
        print("Обновлён ELEVENLABS_API_KEY в .env")
    run(ssh, "systemctl restart navo-radio")
    print("navo-radio перезапущен")
    out, _, code = run(ssh, "systemctl is-active navo-radio-source", check=False)
    if code == 0:
        run(ssh, "systemctl restart navo-radio-source")
        print("navo-radio-source перезапущен")
    return 0


def frontend_local_build(client):
    """Собрать frontend локально и загрузить dist на сервер. Обход OOM на слабых серверах."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    frontend_dir = os.path.join(project_root, "frontend")
    dist_dir = os.path.join(frontend_dir, "dist")
    if not os.path.exists(frontend_dir):
        print("frontend/ не найден")
        return 1
    print("Сборка frontend локально...")
    import subprocess
    env = os.environ.copy()
    env["VITE_API_URL"] = "https://navoradio.com"
    cmd = "npm run build" if os.name == "nt" else ["npm", "run", "build"]
    r = subprocess.run(cmd, cwd=frontend_dir, env=env, capture_output=True, text=True, shell=(os.name == "nt"))
    if r.returncode != 0:
        print(f"Ошибка сборки:\n{r.stderr}")
        return 1
    if not os.path.exists(dist_dir):
        print("dist/ не создан")
        return 1
    print("Загрузка dist/ на сервер...")
    sftp = client.open_sftp()
    remote_dist = f"{APP_DIR}/frontend/dist"
    run(client, f"rm -rf {remote_dist}/*")
    run(client, f"mkdir -p {remote_dist}")
    for root, dirs, files in os.walk(dist_dir):
        rel = os.path.relpath(root, dist_dir)
        for f in files:
            local = os.path.join(root, f)
            rpath = os.path.join(rel, f) if rel != "." else f
            remote = f"{remote_dist}/{rpath}".replace("\\", "/")
            remote_dir = os.path.dirname(remote)
            run(client, f"mkdir -p {remote_dir}", check=False)
            sftp.put(local, remote)
    sftp.close()
    print("Готово. Frontend обновлён.")
    return 0


def nginx_only(client):
    """Только обновить nginx config и reload."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(script_dir, "nginx-navoradio.conf"), "r", encoding="utf-8") as f:
        nginx_conf = f.read()
    sftp = client.open_sftp()
    with sftp.file("/etc/nginx/sites-available/navoradio", "w") as remote:
        remote.write(nginx_conf)
    sftp.close()
    run(client, "nginx -t")
    run(client, "systemctl reload nginx")
    print("Nginx обновлён и перезагружен")
    return 0


if __name__ == "__main__":
    if "--frontend-local" in sys.argv:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
            sys.exit(frontend_local_build(client))
        except Exception as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
        finally:
            client.close()
    if "--nginx-only" in sys.argv:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
            sys.exit(nginx_only(client))
        except Exception as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
        finally:
            client.close()
    if "--key-and-restart" in sys.argv:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
            sys.exit(key_and_restart(client))
        except Exception as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
        finally:
            client.close()
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    sys.exit(main(dry_run=dry))
