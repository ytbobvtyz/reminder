"""
LLM-агент для работы с напоминаниями.
Подключается к MCP-серверу через stdio.
Использует OpenRouter API (модель MiniMax M2.5).
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import nest_asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# Разрешаем вложенные event loops (нужно для Streamlit)
nest_asyncio.apply()

load_dotenv()


# === System Prompt ===
SYSTEM_PROMPT = """Ты агент-ассистент по напоминаниям. У тебя есть MCP инструмент add_reminder.

Когда пользователь просит напомнить о чём-то через N секунд/минут/часов:
1. Извлеки сообщение (что напомнить)
2. Переведи время в секунды:
   - 1 минута = 60 секунд
   - 1 час = 3600 секунд
   - 1 день = 86400 секунд
3. Вызови add_reminder(message="сообщение", delay_seconds=число)
4. Сообщи пользователю, что напоминание установлено, укажи через сколько секунд сработает

ВАЖНО: 
- Всегда используй инструмент add_reminder для создания напоминаний
- Не отвечай из своих знаний — всегда вызывай инструмент
- Если пользователь не указал конкретное время, используй 30 секунд по умолчанию
- Извлекай только суть напоминания, без слов "напомни", "через X секунд" и т.д."""


class ReminderAgent:
    """Агент для обработки напоминаний через LLM и MCP."""
    
    def __init__(self):
        self.client: AsyncOpenAI | None = None
        self.session: ClientSession | None = None
        self._stdio_context = None
        self._session_context = None
        self._tools: list[dict] = []
        
    async def connect(self):
        """Подключение к MCP-серверу и получение инструментов."""
        # Настройка OpenRouter клиента
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY не найден в .env")
        
        # Используем AsyncOpenAI без параметра proxies
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        # Путь к MCP-серверу
        server_path = str(Path(__file__).parent / "mcp_server.py")
        
        server_params = StdioServerParameters(
            command="python",
            args=[server_path],
        )
        
        # Запуск MCP-сервера как дочернего процесса
        self._stdio_context = stdio_client(server_params)
        read_stream, write_stream = await self._stdio_context.__aenter__()
        
        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()
        
        # Инициализация и получение инструментов
        await self.session.initialize()
        tools_result = await self.session.list_tools()
        
        # Конвертация инструментов MCP в формат OpenAI
        self._tools = []
        for tool in tools_result.tools:
            self._tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
            })
        
        print(f"[Agent] Подключено. Инструменты: {[t['function']['name'] for t in self._tools]}")
        
    async def close(self):
        """Закрытие соединений."""
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._stdio_context:
            await self._stdio_context.__aexit__(None, None, None)
            
    async def _call_mcp_tool(self, tool_name: str, arguments: dict) -> Any:
        """Вызов инструмента на MCP-сервере."""
        if not self.session:
            raise RuntimeError("Агент не подключён к MCP-серверу")
        
        result = await self.session.call_tool(tool_name, arguments)
        
        # Извлекаем текст из результата
        if result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return None
    
    async def process(self, user_input: str) -> str:
        """Обработка запроса пользователя через LLM."""
        if not self.client:
            raise RuntimeError("Агент не инициализирован")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]
        
        # Первый вызов LLM
        response = await self.client.chat.completions.create(
            model="minimax/minimax-m2.5",
            messages=messages,
            tools=self._tools,
            tool_choice="auto",
        )
        
        message = response.choices[0].message
        
        # Если LLM вызвал инструмент
        if message.tool_calls:
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"[Agent] Вызов инструмента: {function_name}({function_args})")
                
                # Вызов MCP инструмента
                tool_result = await self._call_mcp_tool(function_name, function_args)
                
                # Добавляем результат вызова инструмента в сообщения
                messages.append({
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": function_name,
                                "arguments": tool_call.function.arguments,
                            }
                        }
                    ]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result)
                })
            
            # Второй вызов LLM для формирования ответа
            second_response = await self.client.chat.completions.create(
                model="minimax/minimax-m2.5",
                messages=messages,
                tools=self._tools,
            )
            
            return second_response.choices[0].message.content or "Напоминание установлено."
        
        return message.content or "Я не понял запрос. Попробуйте переформулировать."
    
    async def call_mcp_tool_direct(self, tool_name: str, arguments: dict) -> Any:
        """Прямой вызов MCP инструмента (для polling уведомлений)."""
        return await self._call_mcp_tool(tool_name, arguments)


# === Синхронная обёртка для удобства ===
class SyncReminderAgent:
    """Синхронная обёртка над ReminderAgent для использования в Streamlit."""
    
    def __init__(self):
        self._agent = ReminderAgent()
        self._loop = asyncio.get_event_loop()
        
    def connect(self):
        """Синхронное подключение."""
        self._loop.run_until_complete(self._agent.connect())
        
    def close(self):
        """Синхронное закрытие."""
        self._loop.run_until_complete(self._agent.close())
            
    def process(self, user_input: str) -> str:
        """Синхронная обработка запроса."""
        return self._loop.run_until_complete(self._agent.process(user_input))
    
    def call_mcp_tool(self, tool_name: str, arguments: dict) -> Any:
        """Синхронный вызов MCP инструмента."""
        return self._loop.run_until_complete(
            self._agent.call_mcp_tool_direct(tool_name, arguments)
        )


if __name__ == "__main__":
    async def test():
        agent = ReminderAgent()
        await agent.connect()
        
        response = await agent.process("напомни через 5 секунд проверить тест")
        print(f"Ответ: {response}")
        
        await agent.close()
    
    asyncio.run(test())
