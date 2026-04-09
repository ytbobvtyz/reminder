#!/usr/bin/env python3
"""
MCP сервер для планировщика задач с использованием APScheduler и SQLite.
Предоставляет инструменты для создания и управления напоминаниями.
"""

import sys
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from mcp import Server
import mcp.types as types


class ReminderMCP:
    """MCP сервер для управления напоминаниями."""
    
    def __init__(self, db_path: str = "reminders.db"):
        """Инициализация сервера с базой данных SQLite и планировщиком."""
        self.db_path = db_path
        self._init_database()
        
        # Настройка планировщика с SQLite хранилищем
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        }
        
        self.scheduler = BackgroundScheduler(jobstores=jobstores)
        self.scheduler.start()
        
        # Восстановление задач из базы данных
        self._restore_tasks()
        
    def _init_database(self):
        """Инициализация базы данных SQLite с таблицами."""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица задач
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    message TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )
            """)
            
            # Таблица логов выполнения
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_db_connection(self):
        """Контекстный менеджер для работы с базой данных."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _restore_tasks(self):
        """Восстановление pending задач из базы данных в планировщик."""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, message, run_at FROM tasks WHERE status = 'pending'"
            )
            
            for row in cursor.fetchall():
                task_id = row['id']
                message = row['message']
                run_at = datetime.fromisoformat(row['run_at'])
                
                # Если задача еще не выполнена, добавляем в планировщик
                if run_at > datetime.now():
                    delay = (run_at - datetime.now()).total_seconds()
                    if delay > 0:
                        self.scheduler.add_job(
                            self._execute_reminder,
                            'date',
                            run_date=run_at,
                            args=[task_id, message],
                            id=task_id
                        )
                    else:
                        # Задача просрочена, помечаем как выполненную
                        self._mark_task_done(task_id)
    
    def _execute_reminder(self, task_id: str, message: str):
        """Выполнение напоминания и запись в лог."""
        print(f"🔔 Напоминание: {message}", file=sys.stderr)
        
        # Записываем выполнение в лог
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO execution_logs (task_id, executed_at) VALUES (?, ?)",
                (task_id, datetime.now().isoformat())
            )
            cursor.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?",
                (task_id,)
            )
            conn.commit()
    
    def _mark_task_done(self, task_id: str):
        """Пометить задачу как выполненную."""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?",
                (task_id,)
            )
            conn.commit()
    
    def add_reminder(self, message: str, delay_seconds: int) -> Dict[str, Any]:
        """Добавить новое напоминание."""
        import uuid
        import time
        
        task_id = str(uuid.uuid4())
        created_at = datetime.now()
        run_at = created_at + timedelta(seconds=delay_seconds)
        
        # Сохраняем в базу данных
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (id, message, run_at, created_at, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (task_id, message, run_at.isoformat(), created_at.isoformat())
            )
            conn.commit()
        
        # Добавляем в планировщик
        self.scheduler.add_job(
            self._execute_reminder,
            'date',
            run_date=run_at,
            args=[task_id, message],
            id=task_id
        )
        
        return {
            "task_id": task_id,
            "message": message,
            "run_at": run_at.isoformat(),
            "created_at": created_at.isoformat(),
            "delay_seconds": delay_seconds
        }
    
    def list_tasks(self, status: str = "all") -> List[Dict[str, Any]]:
        """Получить список задач по статусу."""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            if status == "all":
                cursor.execute("SELECT * FROM tasks ORDER BY run_at")
            elif status in ["pending", "done"]:
                cursor.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY run_at",
                    (status,)
                )
            else:
                raise ValueError(f"Неверный статус: {status}")
            
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row["id"],
                    "message": row["message"],
                    "run_at": row["run_at"],
                    "status": row["status"],
                    "created_at": row["created_at"]
                })
            
            return tasks
    
    def get_due_tasks(self) -> List[Dict[str, Any]]:
        """Получить задачи, которые должны быть выполнены сейчас."""
        now = datetime.now().isoformat()
        
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM tasks 
                WHERE status = 'pending' AND run_at <= ?
                ORDER BY run_at
                """,
                (now,)
            )
            
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row["id"],
                    "message": row["message"],
                    "run_at": row["run_at"],
                    "status": row["status"],
                    "created_at": row["created_at"]
                })
            
            return tasks
    
    def mark_done(self, task_id: str) -> Dict[str, Any]:
        """Пометить задачу как выполненную."""
        # Удаляем задачу из планировщика
        try:
            job = self.scheduler.get_job(task_id)
            if job:
                job.remove()
        except:
            pass
        
        # Помечаем как выполненную в базе данных
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,)
            )
            task = cursor.fetchone()
            
            if not task:
                raise ValueError(f"Задача с ID {task_id} не найдена")
            
            cursor.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?",
                (task_id,)
            )
            
            # Записываем выполнение в лог
            cursor.execute(
                "INSERT INTO execution_logs (task_id, executed_at) VALUES (?, ?)",
                (task_id, datetime.now().isoformat())
            )
            
            conn.commit()
        
        return {"success": True, "task_id": task_id}
    
    def get_tools(self) -> List[types.Tool]:
        """Возвращает список доступных инструментов MCP."""
        return [
            types.Tool(
                name="add_reminder",
                description="Добавить напоминание через указанное количество секунд",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Сообщение напоминания"
                        },
                        "delay_seconds": {
                            "type": "integer",
                            "description": "Задержка в секундах",
                            "minimum": 1,
                            "maximum": 86400  # 24 часа
                        }
                    },
                    "required": ["message", "delay_seconds"]
                }
            ),
            types.Tool(
                name="list_tasks",
                description="Получить список задач по статусу",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Статус задач: 'pending', 'done', или 'all'",
                            "enum": ["pending", "done", "all"],
                            "default": "all"
                        }
                    }
                }
            ),
            types.Tool(
                name="get_due_tasks",
                description="Получить задачи, которые должны быть выполнены сейчас",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            types.Tool(
                name="mark_done",
                description="Пометить задачу как выполненную",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "ID задачи для пометки как выполненной"
                        }
                    },
                    "required": ["task_id"]
                }
            )
        ]
    
    def handle_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка вызова инструмента."""
        if name == "add_reminder":
            return self.add_reminder(
                message=arguments["message"],
                delay_seconds=arguments["delay_seconds"]
            )
        elif name == "list_tasks":
            status = arguments.get("status", "all")
            return {"tasks": self.list_tasks(status)}
        elif name == "get_due_tasks":
            return {"tasks": self.get_due_tasks()}
        elif name == "mark_done":
            return self.mark_done(arguments["task_id"])
        else:
            raise ValueError(f"Неизвестный инструмент: {name}")


async def main():
    """Запуск MCP сервера."""
    server = Server("reminder-mcp-server")
    reminder_server = ReminderMCP()
    
    @server.list_tools()
    async def handle_list_tools():
        return reminder_server.get_tools()
    
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: Dict[str, Any] = None):
        try:
            result = reminder_server.handle_tool_call(name, arguments or {})
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)
                )
            ]
    
    # Запускаем сервер
    await server.run_stdio()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())