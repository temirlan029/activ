#!/bin/bash
# Скрипт диагностики и исправления проблем на VPS

echo "🔍 ДИАГНОСТИКА NEVERLOVE ACTIVITY TRACKER"
echo "========================================"
echo ""

echo "=== 1. Структура проекта ==="
ls -la /root/neverloveactiv/
echo ""
echo "=== Фронтенд папка ==="
ls -la /root/neverloveactiv/frontend/
echo ""
echo "=== Dist папка ==="
ls -la /root/neverloveactiv/frontend/dist/ 2>/dev/null || echo "❌ Dist папка не существует!"
echo ""

echo "=== 2. Проверка API ==="
echo "API /roles:"
curl -s http://localhost:8000/roles | head -5
echo ""
echo "API /top:"
curl -s http://localhost:8000/top?period=all&limit=3 | head -5
echo ""

echo "=== 3. Проверка БД ==="
ls -la /root/neverloveactiv/data/
echo ""
echo "Таблицы в БД:"
sqlite3 /root/neverloveactiv/data/activity.db '.tables'
echo ""
echo "Количество юзеров:"
sqlite3 /root/neverloveactiv/data/activity.db 'SELECT COUNT(*) FROM users'
echo ""

echo "=== 4. Логи сервиса (последние 20 строк) ==="
journalctl -u neverlove -n 20 --no-pager
echo ""

echo "=== 5. Статус сервиса ==="
systemctl status neverlove --no-pager
echo ""

echo "========================================"
echo "✅ Диагностика завершена"