#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы MCP Scheduler Agent.
"""

import os
import asyncio
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

from agent import ReminderAgent

async def test_basic_reminder():
    """Тест создания напоминания."""
    print("🔍 Тестирование создания напоминания...")
    
    agent = ReminderAgent()
    await agent.connect()
    
    # Тест 1: Создание напоминания
    print("Тест 1: Создание напоминания через 10 секунд")
    response = await agent.process("напомни через 10 секунд проверить почту")
    print(f"Ответ агента: {response}")
    
    # Тест 2: Просмотр задач
    print("\nТест 2: Просмотр ожидающих задач")
    response = await agent.process("какие задачи ожидают выполнения?")
    print(f"Ответ агента: {response}")
    
    # Тест 3: Разные форматы времени
    print("\nТест 3: Разные форматы времени")
    response = await agent.process("напомни через 1 минуту выпить воды")
    print(f"Ответ агента: {response}")
    
    # Тест 4: Проверка просроченных задач
    print("\nТест 4: Проверка задач для выполнения")
    response = await agent.process("какие задачи должны быть выполнены сейчас?")
    print(f"Ответ агента: {response}")
    
    await agent.close()
    print("\n✅ Все тесты завершены")


async def test_mcp_server_tools():
    """Тест прямого взаимодействия с MCP инструментами."""
    print("\n🔍 Тестирование MCP инструментов напрямую...")
    
    agent = ReminderAgent()
    await agent.connect()
    
    # Тест 1: add_reminder напрямую
    print("Тест 1: add_reminder напрямую")
    result = await agent._call_mcp_tool("add_reminder", {
        "message": "тестовое напоминание",
        "delay_seconds": 15
    })
    print(f"Результат: {result}")
    
    # Тест 2: list_tasks напрямую
    print("\nТест 2: list_tasks напрямую")
    result = await agent._call_mcp_tool("list_tasks", {"status": "pending"})
    print(f"Результат: {result}")
    
    # Тест 3: get_due_tasks напрямую
    print("\nТест 3: get_due_tasks напрямую")
    result = await agent._call_mcp_tool("get_due_tasks", {})
    print(f"Результат: {result}")
    
    await agent.close()
    print("\n✅ Тесты MCP инструментов завершены")


async def test_streamlit_compatibility():
    """Тест работы агента в режиме для Streamlit."""
    print("\n🔍 Тестирование синхронного агента для Streamlit...")
    
    from agent import SyncReminderAgent
    
    agent = SyncReminderAgent()
    
    # Подключение
    print("Подключение к агент...")
    success = agent.connect()
    print(f"Результат подключения: {success}")
    
    # Тест обработки запросов
    print("\nТест обработки запросов:")
    response = agent.process("напомни через 5 секунд тестовое сообщение")
    print(f"Ответ агента: {response}")
    
    # Тест прямого вызова инструментов
    print("\nТест прямого вызова инструментов:")
    result = agent.call_mcp_tool("list_tasks", {"status": "all"})
    print(f"Результат: {result}")
    
    agent.close()
    print("\n✅ Тесты синхронного агента завершены")


def main():
    """Основная функция тестирования."""
    print("🚀 Начинаем тестирование MCP Scheduler Agent")
    
    # Проверка API ключа
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY не найден в .env файле")
        return
    
    print(f"✅ API ключ найден: {api_key[:20]}...")
    
    # Запуск тестов
    try:
        # Тест базовых напоминаний
        asyncio.run(test_basic_reminder())
        
        # Тест MCP инструментов
        asyncio.run(test_mcp_server_tools())
        
        # Тест Streamlit compatibility
        asyncio.run(test_streamlit_compatibility())
        
        print("\n🎉 Все тесты успешно выполнены!")
        print("\nСледующий шаг: запустить Streamlit приложение:")
        print("streamlit run app.py")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        print("\nВозможные причины:")
        print("1. Не установлены зависимости (pip install -r requirements.txt)")
        print("2. API ключ не работает")
        print("3. Ошибка в коде")


if __name__ == "__main__":
    main()