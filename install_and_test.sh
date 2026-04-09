#!/bin/bash
echo "Установка зависимостей..."
pip install -r requirements.txt

echo -e "\nПроверка установки зависимостей..."
python -c "
import sys
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
    import apscheduler
    print('✅ apscheduler установлена')
except ImportError as e:
    print(f'❌ apscheduler не установлена: {e}')

try:
    import streamlit
    print('✅ streamlit установлена')
except ImportError as e:
    print(f'❌ streamlit не установлена: {e}')
"

echo -e "\nПроверка API ключа..."
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')
if api_key:
    print(f'✅ API ключ найден: {api_key[:20]}...')
else:
    print('❌ API ключ не найден в .env файле')
"

echo -e "\nЗапуск тестового скрипта..."
python test_agent.py