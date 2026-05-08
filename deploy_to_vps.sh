#!/bin/bash

# Скрипт деплоя NeverLove Activity Tracker на VPS
# Ubuntu 22.04

echo "🚀 Начинаем деплой NeverLove Activity Tracker..."

# 1. Обновление системы
echo "📦 Обновление системы..."
apt update && apt upgrade -y

# 2. Установка зависимостей
echo "📦 Установка Python, Node.js, Git..."
apt install -y python3 python3-pip python3-venv git curl

# Установка Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 3. Клонирование репозитория
echo "📥 Клонирование репозитория..."
cd /root
if [ -d "neverloveactiv" ]; then
    echo "Папка уже существует, удаляем..."
    rm -rf neverloveactiv
fi

git clone https://github.com/temirlan029/activ.git neverloveactiv
cd neverloveactiv

# 4. Создание виртуального окружения
echo "🐍 Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# 5. Установка Python зависимостей
echo "📦 Установка Python зависимостей..."
pip install -r requirements.txt

# 6. Сборка фронтенда
echo "🎨 Сборка фронтенда..."
cd frontend
npm install
npm run build
cd ..

# 7. Создание .env файла
echo "⚙️  Создание .env файла..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️  ВАЖНО: Отредактируйте .env файл и добавьте ваш DISCORD_TOKEN!"
    echo "   nano .env"
    echo "   После этого запустите: systemctl start neverlove"
else
    echo ".env файл уже существует"
fi

# 8. Создание директории для данных
echo "📁 Создание директории для данных..."
mkdir -p data

# 9. Создание systemd сервиса
echo "⚙️  Создание systemd сервиса..."
cat > /etc/systemd/system/neverlove.service << EOF
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
EOF

# 10. Активация сервиса
echo "🔄 Активация systemd сервиса..."
systemctl daemon-reload
systemctl enable neverlove

# 11. Настройка firewall
echo "🔥 Настройка firewall..."
ufw allow 22/tcp    # SSH
ufw allow 8000/tcp  # API
ufw --force enable

echo "✅ Деплой завершен!"
echo ""
echo "📝 Дальнейшие шаги:"
echo "1. Отредактируйте .env файл: nano /root/neverloveactiv/.env"
echo "2. Добавьте ваш DISCORD_TOKEN"
echo "3. Запустите сервис: systemctl start neverlove"
echo "4. Проверьте статус: systemctl status neverlove"
echo "5. Посмотрите логи: journalctl -u neverlove -f"
echo ""
echo "🌐 Дашборд будет доступен по адресу: http://185.9.147.15:8000"