# NAVO RADIO — Инструкция по развёртыванию на Ubuntu

Инструкция для агента Cursor или разработчика по развёртыванию приложения на сервере Ubuntu.

---

## 1. Требования к серверу

- **ОС:** Ubuntu 22.04 LTS или 24.04 LTS
- **Память:** минимум 1 GB RAM (рекомендуется 2 GB)
- **Диск:** 5+ GB свободного места
- **Сеть:** открытые порты 80 (HTTP), 443 (HTTPS), 8000 (API, опционально)

---

## 2. Установка зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Python 3.11+
sudo apt install -y python3 python3-pip python3-venv

# Node.js 20+ (для сборки фронтенда)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# FFmpeg (для стриминга аудио)
sudo apt install -y ffmpeg

# Git
sudo apt install -y git
```

---

## 3. Клонирование репозитория

```bash
cd /opt  # или /home/ubuntu, /var/www — на выбор
sudo git clone https://github.com/Hexttr/NAVO-final.git navo-radio
sudo chown -R $USER:$USER navo-radio
cd navo-radio
```

---

## 4. Секреты и переменные окружения

### 4.1. Создание `.env` в корне проекта

Файл `.env` **не должен** попадать в git. Создайте его вручную:

```bash
cp .env.example .env
nano .env
```

Заполните значения (см. `.env.example`):

- `JAMENDO_CLIENT_ID` — [jamendo.com](https://www.jamendo.com/) → API
- `GROQ_API_KEY` — [console.groq.com](https://console.groq.com/)
- `WEATHER_API_KEY` — [openweathermap.org](https://openweathermap.org/api)
- `DATABASE_URL` — по умолчанию `sqlite:///./navo.db`
- `BACKEND_HOST`, `BACKEND_PORT` — для продакшена можно оставить `0.0.0.0` и `8000`

### 4.2. Бесплатная передача секретов (без git)

**Вариант A — OneTimeSecret (рекомендуется)**  
1. Перейдите на [onetimesecret.com](https://onetimesecret.com)  
2. Вставьте содержимое `.env` в поле  
3. Установите пароль (опционально)  
4. Создайте секрет и скопируйте ссылку  
5. Передайте ссылку агенту/админу (по защищённому каналу)  
6. Ссылка работает один раз, после просмотра удаляется  

**Вариант B — Bitwarden Send**  
1. [bitwarden.com/products/send](https://bitwarden.com/products/send)  
2. Создайте Send с содержимым `.env`  
3. Установите срок жизни и пароль  
4. Передайте ссылку  

**Вариант C — SCP/SFTP**  
```bash
# С локальной машины на сервер
scp .env user@server:/opt/navo-radio/.env
```

**Вариант D — Ручное создание на сервере**  
1. SSH на сервер  
2. `nano /opt/navo-radio/.env`  
3. Вставьте значения (скопировать из защищённого источника)  

---

## 5. Бэкенд (FastAPI)

```bash
cd /opt/navo-radio

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Зависимости
pip install -r backend/requirements.txt

# Запуск (для проверки)
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

Проверка: `curl http://localhost:8000/` → `{"message":"NAVO RADIO API",...}`

---

## 6. Фронтенд (React + Vite)

### 6.1. Сборка с URL API

Перед сборкой задайте URL бэкенда:

```bash
cd /opt/navo-radio/frontend

# Для продакшена (замените на ваш домен или IP)
export VITE_API_URL=https://your-domain.com
# или для теста на том же сервере:
# export VITE_API_URL=http://YOUR_SERVER_IP:8000

npm install
npm run build
```

Артефакты появятся в `frontend/dist/`.

### 6.2. Раздача статики

Бэкенд может раздавать статику. Добавьте в `backend/main.py` (если ещё нет):

```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

Либо настройте Nginx (см. ниже).

---

## 7. Systemd (автозапуск бэкенда)

Создайте `/etc/systemd/system/navo-radio.service`:

```ini
[Unit]
Description=NAVO RADIO API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/navo-radio/backend
Environment="PATH=/opt/navo-radio/venv/bin"
ExecStart=/opt/navo-radio/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Загрузить .env в сервис (опционально)
# В [Service] добавьте:
# EnvironmentFile=/opt/navo-radio/.env

sudo systemctl daemon-reload
sudo systemctl enable navo-radio
sudo systemctl start navo-radio
sudo systemctl status navo-radio
```

---

## 8. Nginx (реверс-прокси, HTTPS)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Создайте `/etc/nginx/sites-available/navo-radio`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Статика фронтенда
    root /opt/navo-radio/frontend/dist;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Стриминг
    location /stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 86400s;
    }

    # Загрузки (аудио)
    location /uploads {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/navo-radio /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# HTTPS (Let's Encrypt)
sudo certbot --nginx -d your-domain.com
```

---

## 9. Переменная VITE_API_URL при сборке

При использовании Nginx с одним доменом API и фронтент на одном домене:

```bash
export VITE_API_URL=https://your-domain.com
npm run build
```

Если API на поддомене:

```bash
export VITE_API_URL=https://api.your-domain.com
npm run build
```

---

## 10. CORS (если фронт и API на разных доменах)

В `backend/main.py` добавьте ваш домен в `allow_origins`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://your-domain.com",
        "https://www.your-domain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 11. Проверка

- Фронт: `https://your-domain.com/`
- Админка: `https://your-domain.com/admin`
- Стрим: `https://your-domain.com/stream`
- API docs: `https://your-domain.com/docs`

---

## 12. Обновление приложения

```bash
cd /opt/navo-radio
git pull
source venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && VITE_API_URL=https://your-domain.com npm run build
sudo systemctl restart navo-radio
```

---

## 13. Резюме по секретам

| Способ              | Сложность | Безопасность |
|---------------------|-----------|--------------|
| OneTimeSecret       | Низкая    | Высокая      |
| Bitwarden Send      | Низкая    | Высокая      |
| SCP/SFTP            | Средняя   | Высокая      |
| Ручное создание     | Средняя   | Высокая      |

**Не используйте:** публичные paste-сервисы, чаты, email без шифрования.
