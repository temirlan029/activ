# NEVERLOVE Activity Tracker

Discord-бот + FastAPI + React дашборд для трекинга активности сервера.

---

## Локальный запуск (тест)

### 1. Установить зависимости Python

```bash
pip install -r requirements.txt
```

### 2. Создать `.env` файл

```bash
cp .env.example .env
```
Открой `.env` и вставь токен бота:
```
DISCORD_TOKEN=твой_токен
PORT=8000
```

### 3. Собрать React фронтенд

```bash
cd frontend
cp .env.example .env        # оставь VITE_API_URL пустым для локалки
npm install
npm run build
cd ..
```

### 4. Запустить

```bash
python main.py
```

Открой браузер: **http://localhost:8000**

---

## Деплой на DigitalOcean

### 1. Создать Droplet
- Ubuntu 22.04 LTS, план Basic $6/мес (1 vCPU, 1GB RAM)
- Регион: Amsterdam или Frankfurt (ближе к Discord EU серверам)

### 2. Подключиться по SSH
```bash
ssh root@ВАШ_IP
```

### 3. Установить Python и Node.js
```bash
apt update && apt install -y python3-pip python3-venv nodejs npm git
```

### 4. Клонировать репозиторий
```bash
git clone https://github.com/ВАШ_АККАУНТ/neverloveactiv.git
cd neverloveactiv
```

### 5. Настроить окружение
```bash
cp .env.example .env
nano .env   # вставь токен
```

### 6. Установить зависимости и собрать фронтенд
```bash
pip3 install -r requirements.txt

cd frontend
cp .env.example .env
# В frontend/.env укажи: VITE_API_URL=http://ВАШ_IP:8000
npm install && npm run build
cd ..
```

### 7. Запустить через systemd (автозапуск)
```bash
nano /etc/systemd/system/neverlove.service
```

Содержимое:
```ini
[Unit]
Description=NeverLove Activity Tracker
After=network.target

[Service]
WorkingDirectory=/root/neverloveactiv
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/neverloveactiv/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable neverlove
systemctl start neverlove
systemctl status neverlove
```

Дашборд доступен по адресу: **http://ВАШ_IP:8000**

---

## Структура проекта

```
neverloveactiv/
├── main.py          # Точка входа (бот + API)
├── bot.py           # Discord бот
├── api.py           # FastAPI эндпоинты
├── database.py      # SQLite операции
├── requirements.txt
├── .env.example
├── data/
│   └── activity.db  # База данных (создаётся автоматически)
└── frontend/        # React + Tailwind дашборд
    ├── src/
    │   ├── App.jsx
    │   ├── main.jsx
    │   └── index.css
    └── dist/        # Собранный фронтенд (после npm run build)
```
