# Деплой на DigitalOcean

## После создания Droplet

### 1. Подключение по SSH

```bash
ssh root@YOUR_IP_ADDRESS
```

### 2. Обновление системы

```bash
apt update && apt upgrade -y
```

### 3. Установка зависимостей

```bash
# Python 3 и pip
apt install -y python3 python3-pip python3-venv

# Node.js и npm
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Git
apt install -y git
```

### 4. Клонирование репозитория

```bash
cd /root
git clone https://github.com/temirlan029/activ.git neverloveactiv
cd neverloveactiv
```

### 5. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
```

### 6. Установка Python зависимостей

```bash
pip install -r requirements.txt
```

### 7. Сборка фронтенда

```bash
cd frontend
npm install
npm run build
cd ..
```

### 8. Создание .env файла

```bash
cp .env.example .env
nano .env
```

Добавь Discord токен:
```
DISCORD_TOKEN=твой_токен_здесь
PORT=8000
```

Сохрани и выйди (Ctrl+X, Y, Enter)

### 9. Создание директории для данных

```bash
mkdir -p data
```

### 10. Тестовый запуск

```bash
source venv/bin/activate
python main.py
```

Проверь, что бот подключился. Останови (Ctrl+C).

### 11. Создание systemd сервиса

```bash
nano /etc/systemd/system/neverlove.service
```

Вставь следующее:

```ini
[Unit]
Description=Neverlove Activity Tracker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/neverloveactiv
Environment="PATH=/root/neverloveactiv/venv/bin"
ExecStart=/root/neverloveactiv/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохрани и выйди (Ctrl+X, Y, Enter)

### 12. Запуск сервиса

```bash
systemctl daemon-reload
systemctl enable neverlove
systemctl start neverlove
```

### 13. Проверка статуса

```bash
systemctl status neverlove
```

Должен показать "active (running)"

### 14. Проверка логов

```bash
journalctl -u neverlove -f
```

Останови (Ctrl+C)

### 15. Настройка firewall (опционально)

```bash
ufw allow 22/tcp    # SSH
ufw allow 8000/tcp  # API
ufw enable
```

### 16. Доступ

Дашборд будет доступен по адресу:
```
http://YOUR_IP_ADDRESS:8000
```

---

## Полезные команды

**Перезапуск сервиса:**
```bash
systemctl restart neverlove
```

**Остановка сервиса:**
```bash
systemctl stop neverlove
```

**Просмотр логов:**
```bash
journalctl -u neverlove -n 100
```

**Обновление кода:**
```bash
cd /root/neverloveactiv
git pull
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
systemctl restart neverlove
```

---

## Проблемы и решения

### Бот не подключается к Discord
- Проверь токен в .env
- Проверь логи: `journalctl -u neverlove -n 50`

### Фронтенд не собирается
- Убедись, что nodejs установлен: `node --version`
- Переустанови зависимости: `cd frontend && rm -rf node_modules && npm install`

### Порт 8000 занят
```bash
lsof -i :8000
kill -9 PID
```

### Мало памяти
- Если droplet с 512MB RAM, обнови до 1GB
- Или добавь swap файл:
```bash
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```