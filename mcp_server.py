"""
MCP-сервер для планирования напоминаний.
Запускается отдельно от Streamlit-приложения.
Инструменты: add_reminder, list_tasks, get_due_tasks, mark_done.
"""

import asyncio
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from mcp.server import Server  # type: ignore
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# === Конфигурация ===
DB_PATH = Path(__file__).parent / "reminders.db"


# === Инициализация базы данных ===
def init_db():
    """Создание таблиц в SQLite."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            run_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    
    conn.commit()
    conn.close()


# === Планировщик APScheduler ===
scheduler = BackgroundScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url=f'sqlite:///{DB_PATH}')
    }
)


def mark_task_done_callback(task_id: str):
    """Callback для APScheduler — отмечает задачу выполненной."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE tasks SET status = 'done' WHERE id = ?",
        (task_id,)
    )
    
    cursor.execute(
        "INSERT INTO execution_logs (task_id, executed_at) VALUES (?, ?)",
        (task_id, datetime.now().isoformat())
    )
    
    conn.commit()
    conn.close()


def restore_tasks():
    """Восстановление pending-задач при старте сервера."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, message, run_at FROM tasks WHERE status = 'pending'"
    )
    tasks = cursor.fetchall()
    conn.close()
    
    now = datetime.now()
    for task_id, message, run_at_str in tasks:
        run_at = datetime.fromisoformat(run_at_str)
        if run_at > now:
            scheduler.add_job(
                mark_task_done_callback,
                'date',
                run_date=run_at,
                args=[task_id],
                id=task_id,
                replace_existing=True
            )


# === MCP сервер ===
app = Server("reminder-scheduler")


@app.list_tools()
async def list_tools():
    """Список доступных MCP-инструментов."""
    return [
        Tool(
            name="add_reminder",
            description="Создаёт напоминание с указанным сообщением и задержкой в секундах",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Текст напоминания"
                    },
                    "delay_seconds": {
                        "type": "integer",
                        "description": "Задержка в секундах до напоминания"
                    }
                },
                "required": ["message", "delay_seconds"]
            }
        ),
        Tool(
            name="list_tasks",
            description="Возвращает список задач с фильтрацией по статусу",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "done", "all"],
                        "description": "Фильтр по статусу",
                        "default": "all"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_due_tasks",
            description="Возвращает задачи, которые должны быть выполнены сейчас (status=pending и run_at <= now)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="mark_done",
            description="Отмечает задачу как выполненную",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID задачи"
                    }
                },
                "required": ["task_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict | None = None) -> list[TextContent]:
    """Обработка вызовов инструментов."""
    if arguments is None:
        arguments = {}
    
    if name == "add_reminder":
        return handle_add_reminder(arguments)
    elif name == "list_tasks":
        return handle_list_tasks(arguments)
    elif name == "get_due_tasks":
        return handle_get_due_tasks()
    elif name == "mark_done":
        return handle_mark_done(arguments)
    else:
        return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


def handle_add_reminder(args: dict) -> list[TextContent]:
    """Создание нового напоминания."""
    message = args.get("message", "")
    delay_seconds = args.get("delay_seconds", 0)
    
    task_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    run_at = now + timedelta(seconds=delay_seconds)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO tasks (id, message, run_at, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (task_id, message, run_at.isoformat(), now.isoformat())
    )
    
    conn.commit()
    conn.close()
    
    # Планируем задачу через APScheduler
    scheduler.add_job(
        mark_task_done_callback,
        'date',
        run_date=run_at,
        args=[task_id],
        id=task_id
    )
    
    result = {
        "task_id": task_id,
        "message": message,
        "run_at": run_at.isoformat(),
        "delay_seconds": delay_seconds
    }
    
    return [TextContent(type="text", text=json.dumps(result))]


def handle_list_tasks(args: dict) -> list[TextContent]:
    """Получение списка задач."""
    status_filter = args.get("status", "all")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    if status_filter == "all":
        cursor.execute("SELECT id, message, run_at, status, created_at FROM tasks ORDER BY created_at DESC")
    else:
        cursor.execute(
            "SELECT id, message, run_at, status, created_at FROM tasks WHERE status = ? ORDER BY created_at DESC",
            (status_filter,)
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "message": row[1],
            "run_at": row[2],
            "status": row[3],
            "created_at": row[4]
        })
    
    return [TextContent(type="text", text=json.dumps(tasks))]


def handle_get_due_tasks() -> list[TextContent]:
    """Получение задач, которые нужно выполнить сейчас."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    cursor.execute(
        "SELECT id, message, run_at, status, created_at FROM tasks WHERE status = 'pending' AND run_at <= ?",
        (now,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "message": row[1],
            "run_at": row[2],
            "status": row[3],
            "created_at": row[4]
        })
    
    return [TextContent(type="text", text=json.dumps(tasks))]


def handle_mark_done(args: dict) -> list[TextContent]:
    """Отметка задачи как выполненной."""
    task_id = args.get("task_id", "")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE tasks SET status = 'done' WHERE id = ?",
        (task_id,)
    )
    
    cursor.execute(
        "INSERT INTO execution_logs (task_id, executed_at) VALUES (?, ?)",
        (task_id, datetime.now().isoformat())
    )
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected > 0:
        result = {"success": True, "task_id": task_id}
    else:
        result = {"success": False, "error": "Задача не найдена"}
    
    return [TextContent(type="text", text=json.dumps(result))]


async def main():
    """Точка входа для запуска MCP-сервера."""
    init_db()
    
    if not scheduler.running:
        restore_tasks()
        scheduler.start()
    
    print("[MCP Server] Сервер запущен. Ожидание подключений...")
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
    
    scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
