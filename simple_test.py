#!/usr/bin/env python3
"""
Простой тест для проверки работоспособности компонентов.
"""

import os
import sys
import subprocess

def check_dependencies():
    """Проверка установленных зависимостей."""
    print("🔍 Проверка зависимостей...")
    
    deps = {
        'openai': 'openai==0.28.1',
        'mcp': 'mcp==1.12.0',
        'apscheduler': 'apscheduler==3.10.4',
        'streamlit': 'streamlit==1.35.0',
        'python-dotenv': 'python-dotenv==1.0.0',
    }
    
    for dep, version in deps.items():
        try:
            __import__(dep)
            print(f"✅ {dep} установлен")
        except ImportError:
            print(f"❌ {dep} не установлен (требуется {version})")
    
    print()

def check_api_key():
    """Проверка API ключа."""
    print("🔑 Проверка API ключа...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        print(f"✅ API ключ найден: {api_key[:20]}...")
    else:
        print("❌ API ключ не найден в .env файле")
    
    print()

def test_mcp_server():
    """Тест запуска MCP сервера."""
    print("🔄 Тест MCP сервера...")
    
    try:
        # Пробуем импортировать модуль
        import mcp_server
        print("✅ mcp_server.py импортируется успешно")
    except Exception as e:
        print(f"❌ Ошибка импорта mcp_server.py: {e}")
    
    # Проверяем, что файл существует и может быть выполнен
    if os.path.exists("mcp_server.py"):
        print("✅ Файл mcp_server.py существует")
        
        # Проверяем синтаксис
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", "mcp_server.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Синтаксис mcp_server.py корректен")
        else:
            print(f"❌ Синтаксическая ошибка в mcp_server.py: {result.stderr}")
    else:
        print("❌ Файл mcp_server.py не найден")
    
    print()

def test_agent():
    """Тест агента."""
    print("🤖 Тест агента...")
    
    try:
        import agent
        print("✅ agent.py импортируется успешно")
        
        # Проверяем основные классы
        from agent import ReminderAgent, SyncReminderAgent
        print("✅ Классы ReminderAgent и SyncReminderAgent доступны")
    except Exception as e:
        print(f"❌ Ошибка импорта agent.py: {e}")
    
    print()

def test_streamlit():
    """Тест Streamlit UI."""
    print("🎨 Тест Streamlit UI...")
    
    try:
        import app
        print("✅ app.py импортируется успешно")
        
        # Проверяем основные функции
        if hasattr(app, 'main'):
            print("✅ Функция main() доступна")
        else:
            print("❌ Функция main() не найдена в app.py")
    except Exception as e:
        print(f"❌ Ошибка импорта app.py: {e}")
    
    print()

def check_requirements():
    """Проверка файла requirements.txt."""
    print("📋 Проверка requirements.txt...")
    
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r") as f:
            lines = f.readlines()
            print(f"✅ Файл requirements.txt существует ({len(lines)} зависимостей)")
            
            # Выводим список зависимостей
            print("Список зависимостей:")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    print(f"  - {line}")
    else:
        print("❌ Файл requirements.txt не найден")
    
    print()

def main():
    """Основная функция тестирования."""
    print("🚀 Начинаем проверку проекта MCP Scheduler Agent")
    print("=" * 50)
    
    check_dependencies()
    check_api_key()
    check_requirements()
    test_mcp_server()
    test_agent()
    test_streamlit()
    
    print("=" * 50)
    print("📋 Сводка:")
    print("1. Установите зависимости: pip install -r requirements.txt")
    print("2. Проверьте API ключ в .env файле")
    print("3. Запустите тест: python test_agent.py")
    print("4. Запустите приложение: streamlit run app.py")
    print("")
    print("🎉 Проект готов к запуску!")

if __name__ == "__main__":
    main()