#!/bin/bash

echo "=== MCP Scheduler Agent ==="
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+"
    exit 1
fi

echo "✅ Python3 найден: $(python3 --version)"

# Проверка pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не найден. Установите pip"
    exit 1
fi

echo "✅ pip3 найден"

# Установка зависимостей
echo ""
echo "Установка зависимостей..."
pip3 install -r requirements.txt

# Проверка переменных окружения
echo ""
echo "Проверка переменных окружения..."
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден"
    echo "Создайте файл .env с содержимым:"
    echo "OPENROUTER_API_KEY=ваш_ключ_здесь"
    exit 1
fi

# Загрузка API ключа
source .env 2>/dev/null || true
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ OPENROUTER_API_KEY не найден в .env файле"
    exit 1
fi

echo "✅ API ключ найден"

# Проверка импортов
echo ""
echo "Проверка импортов Python..."
python3 -c "
try:
    import openai
    print('✅ openai установлена')
except ImportError as e:
    print(f'❌ openai не установлена: {e}')

try:
    from mcp import ClientSession, StdioServerParameters
    print('✅ mcp установлена')
except ImportError as e:
    print(f'❌ mcp не установлена: {e}')

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    print('✅ apscheduler установлена')
except ImportError as e:
    print(f'❌ apscheduler не установлена: {e}')

try:
    import streamlit
    print('✅ streamlit установлена')
except ImportError as e:
    print(f'❌ streamlit не установлена: {e}')
"

echo ""
echo "=== Инструкция по запуску ==="
echo ""
echo "1. Для тестирования агента выполните:"
echo "   python test_agent.py"
echo ""
echo "2. Для запуска приложения выполните:"
echo "   streamlit run app.py"
echo ""
echo "3. Затем откройте браузер по адресу:"
echo "   http://localhost:8501"
echo ""
echo "Примеры команд для тестирования:"
echo "- напомни через 10 секунд проверить почту"
echo "- какие задачи ожидают выполнения?"
echo "- напомни через 1 минуту выпить воды"