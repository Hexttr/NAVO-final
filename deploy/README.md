# Деплой NAVO RADIO на navoradio.com

## Icecast (единый эфир для всех)

Эфир идёт через Icecast — один источник, все слушатели слышат одно и то же.

```bash
python deploy/deploy_icecast.py
```

Устанавливает: Icecast2, navo-radio-source (стримит эфир в Icecast), обновляет nginx.

## Подготовка

### 1. Ветка ubuntu

Работа ведётся в ветке `ubuntu`. Перед первым деплоем:

```bash
git add .
git commit -m "Ubuntu deployment config"
git push origin ubuntu
```

### 2. Файл .env на сервере

Приложение требует API-ключи. Создайте `.env` на сервере в `/opt/navo-radio/.env`:

| Переменная | Описание | Где взять |
|------------|----------|-----------|
| `JAMENDO_CLIENT_ID` | Музыка (Jamendo) | [jamendo.com](https://www.jamendo.com/) → API |
| `GROQ_API_KEY` | LLM для новостей, погоды, DJ | [console.groq.com](https://console.groq.com/) |
| `WEATHER_API_KEY` | Погода | [openweathermap.org](https://openweathermap.org/api) |

Минимальный `.env`:

```
JAMENDO_CLIENT_ID=ваш_ключ
GROQ_API_KEY=ваш_ключ
WEATHER_API_KEY=ваш_ключ
DATABASE_URL=sqlite:///./navo.db
```

Скопировать на сервер:

```bash
scp .env root@195.133.63.34:/opt/navo-radio/.env
```

Или создать вручную через SSH.

## Запуск деплоя

Из папки проекта (где лежит `deploy/`):

```bash
python deploy/deploy_to_server.py
```

Просмотр без выполнения:

```bash
python deploy/deploy_to_server.py --dry-run
```

## Возможные сложности

1. **Ветка ubuntu не на GitHub** — деплой возьмёт `main`. Чтобы использовать `ubuntu`, выполните `git push origin ubuntu`.

2. **Нет API-ключей** — приложение запустится, но генерация новостей/погоды/Jamendo не будет работать. Админка и стрим будут доступны после создания эфира вручную.

3. **FFmpeg** — нужен для стриминга. На Ubuntu: `apt install ffmpeg`. Должен быть установлен на сервере.

4. **Node.js 20+** — для сборки фронтенда. Если нет: `curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt install -y nodejs`.

5. **Пустой эфир** — при первом заходе на `/stream` будет 404. Нужно зайти в админку `/admin`, создать сетку эфира (Songs, News, Weather и т.д.) и нажать «Сгенерировать эфир».
