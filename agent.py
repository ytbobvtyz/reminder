#!/usr/bin/env python3
"""
LLM агент для обработки запросов пользователя и взаимодействия с MCP сервером.
Использует OpenRouter API для анализа естественного языка.
"""

import os
import json
import asyncio
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime

import openai
from mcp import ClientSession, StdioServerParameters
import mcp.types as types


class ReminderAgent:
    """Агент для обработки запросов о напоминаниях через LLM."""
    
    def __init__(self):
        """Инициализация агента с подключением к OpenRouter API."""
        self.model = "qwen/qwen3.6-plus-preview:free"
        openai.base_url = "https://openrouter.ai/api/v1"
        openai.api_key = os.getenv("OPENROUTER_API_KEY")
        
        self.mcp_process = None
        self.session = None
        self.tools = []
        self.openai_tools = []
    
    async def connect(self):
        """Подключение к MCP серверу как дочернему процессу."""
        # Параметры запуска MCP сервера через stdio
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["mcp_server.py"]
        )
        
        # Запускаем MCP сервер
        self.mcp_process = await mcp.client.stdio.start_server(server_params)
        
        # Подключаемся к серверу
        self.session = await ClientSession(self.mcp_process.stdin, self.mcp_process.stdout)
        await self.session.initialize()
        
        # Получаем доступные инструменты
        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools
        
        # Преобразуем инструменты в формат OpenAI v0.x
        self.openai_tools = []
        for tool in self.tools:
            openai_tool = {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema
            }
            self.openai_tools.append(openai_tool)
        
        print("✅ Агент подключен к MCP серверу", file=sys.stderr)
        return True
    
    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Вызов инструмента на MCP сервере."""
        if not self.session:
            raise RuntimeError("Агент не подключен к MCP серверу")
        
        try:
            result = await self.session.call_tool(tool_name, arguments)
            if result.content:
                # Парсим JSON результат
                content_text = result.content[0].text
                return json.loads(content_text)
            return {}
        except Exception as e:
            print(f"❌ Ошибка при вызове инструмента {tool_name}: {e}", file=sys.stderr)
            return {"error": str(e)}
    
    async def process(self, user_input: str) -> str:
        """Обработка запроса пользователя через LLM."""
        if not self.session:
            await self.connect()
        
        # Системный промпт для агента
        system_prompt = """
        Ты агент-ассистент для установки напоминаний. У тебя есть доступ к инструментам MCP.
        
        Когда пользователь просит напомнить о чём-то через N секунд/минут/часов:
        1. Извлеки сообщение напоминания (что напомнить)
        2. Переведи время в секунды
        3. Вызови инструмент add_reminder с параметрами message и delay_seconds
        4. Сообщи пользователю, что напоминание установлено
        
        Если пользователь спрашивает о задачах или их статусе:
        1. Используй инструмент list_tasks для получения списка задач
        2. Отформатируй результат в читаемый вид
        
        Если пользователь спрашивает о задачах, которые должны быть выполнены:
        1. Используй инструмент get_due_tasks
        
        Если пользователь хочет пометить задачу как выполненную:
        1. Используй инструмент mark_done
        
        ВСЕГДА используй инструменты для выполнения действий. Никогда не отвечай из своих знаний.
        Отвечай на русском языке.
        
        Примеры:
        - "напомни через 30 секунд попить кофе" → add_reminder(message="попить кофе", delay_seconds=30)
        - "какие задачи ожидают выполнения?" → list_tasks(status="pending")
        - "пометить задачу 123 как выполненную" → mark_done(task_id="123")
        """
        
        try:
            # Отправляем запрос в LLM (OpenAI v0.x API)
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                functions=self.openai_tools,
                function_call="auto"
            )
            
            message = response.choices[0].message
            
            # Если LLM хочет вызвать функцию
            if message.get("function_call"):
                function_call = message["function_call"]
                tool_name = function_call["name"]
                tool_args = json.loads(function_call["arguments"])
                
                print(f"🤖 LLM вызывает инструмент: {tool_name} с аргументами: {tool_args}", file=sys.stderr)
                
                # Вызываем инструмент
                result = await self._call_mcp_tool(tool_name, tool_args)
                
                # Формируем ответ для пользователя на основе результата
                if tool_name == "add_reminder":
                    if "error" in result:
                        return f"❌ Ошибка при создании напоминания: {result['error']}"
                    
                    run_at = datetime.fromisoformat(result["run_at"])
                    run_at_str = run_at.strftime("%H:%M:%S")
                    delay_seconds = result["delay_seconds"]
                    
                    return f"✅ Напоминание \"{result['message']}\" установлено через {delay_seconds} секунд (в {run_at_str})"
                
                elif tool_name == "list_tasks":
                    tasks = result.get("tasks", [])
                    if not tasks:
                        return "📭 Нет задач с указанным статусом"
                    
                    response_text = "📋 Список задач:\n"
                    for task in tasks:
                        status_icon = "⏳" if task["status"] == "pending" else "✅"
                        run_at = datetime.fromisoformat(task["run_at"])
                        run_at_str = run_at.strftime("%H:%M:%S")
                        response_text += f"{status_icon} {task['message']} → {task['status']} (до {run_at_str})\n"
                    
                    return response_text
                
                elif tool_name == "get_due_tasks":
                    tasks = result.get("tasks", [])
                    if not tasks:
                        return "⏰ Нет задач для выполнения в данный момент"
                    
                    response_text = "🔔 Задачи для выполнения сейчас:\n"
                    for task in tasks:
                        response_text += f"• {task['message']}\n"
                    
                    return response_text
                
                elif tool_name == "mark_done":
                    if "error" in result:
                        return f"❌ Ошибка при пометке задачи: {result['error']}"
                    
                    return f"✅ Задача помечена как выполненная"
                
                else:
                    return f"Инструмент {tool_name} выполнен. Результат: {json.dumps(result, ensure_ascii=False)}"
            
            # Если LLM отвечает напрямую
            if message.content:
                return message.content
            
            return "Не удалось обработать запрос"
            
        except Exception as e:
            print(f"❌ Ошибка при обработке запроса: {e}", file=sys.stderr)
            return f"Произошла ошибка: {str(e)}"
    
    async def close(self):
        """Закрытие соединений."""
        if self.session:
            await self.session.close()
        if self.mcp_process:
            self.mcp_process.terminate()


# Синхронная обёртка для использования в Streamlit
class SyncReminderAgent:
    """Синхронная обёртка над асинхронным агентом."""
    
    def __init__(self):
        self.agent = ReminderAgent()
        self.loop = None
    
    def connect(self):
        """Подключение к MCP серверу (синхронная версия)."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        return self.loop.run_until_complete(self.agent.connect())
    
    def process(self, user_input: str) -> str:
        """Обработка запроса пользователя (синхронная версия)."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        return self.loop.run_until_complete(self.agent.process(user_input))
    
    def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Вызов инструмента MCP (синхронная версия)."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        return self.loop.run_until_complete(self.agent._call_mcp_tool(tool_name, arguments))
    
    def close(self):
        """Закрытие соединений (синхронная версия)."""
        if self.loop:
            self.loop.run_until_complete(self.agent.close())
            self.loop.close()


if __name__ == "__main__":
    # Пример использования
    import asyncio
    
    async def test():
        agent = ReminderAgent()
        await agent.connect()
        
        # Тестируем создание напоминания
        response = await agent.process("напомни через 10 секунд проверить почту")
        print(f"Ответ: {response}")
        
        # Тестируем список задач
        response = await agent.process("какие задачи ожидают выполнения?")
        print(f"Ответ: {response}")
        
        await agent.close()
    
    asyncio.run(test())