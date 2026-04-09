#!/usr/bin/env python3
"""
Streamlit UI для MCP Scheduler Agent.
Предоставляет чат-интерфейс с агентом и фоновый polling для уведомлений.
"""

import streamlit as st
import time
import threading
import queue
import json
from datetime import datetime
from typing import Dict, List, Any

from agent import SyncReminderAgent


def setup_page():
    """Настройка страницы Streamlit."""
    st.set_page_config(
        page_title="MCP Scheduler Agent",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # CSS стили
    st.markdown("""
    <style>
    .stApp {
        background-color: #f5f5f5;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .assistant-message {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
    .notification-toast {
        background-color: #4caf50 !important;
        color: white !important;
    }
    .task-list {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)


class NotificationManager:
    """Менеджер для обработки уведомлений в фоновом потоке."""
    
    def __init__(self, agent):
        self.agent = agent
        self.notification_queue = queue.Queue()
        self.running = False
        self.thread = None
    
    def start(self):
        """Запуск фонового потока для проверки уведомлений."""
        if self.thread and self.thread.is_alive():
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._poll_notifications, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Остановка фонового потока."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def _poll_notifications(self):
        """Фоновый polling для проверки задач на выполнение."""
        while self.running:
            try:
                # Получаем задачи, которые должны быть выполнены сейчас
                result = self.agent.call_mcp_tool("get_due_tasks", {})
                
                if "tasks" in result:
                    tasks = result["tasks"]
                    for task in tasks:
                        # Добавляем уведомление в очередь
                        self.notification_queue.put({
                            "message": task["message"],
                            "task_id": task["id"],
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        # Помечаем задачу как выполненную
                        self.agent.call_mcp_tool("mark_done", {"task_id": task["id"]})
                
                # Проверяем каждую секунду
                time.sleep(1)
                
            except Exception as e:
                print(f"Ошибка в фоновом polling: {e}")
                time.sleep(2)
    
    def get_notifications(self):
        """Получение всех ожидающих уведомлений."""
        notifications = []
        while not self.notification_queue.empty():
            try:
                notifications.append(self.notification_queue.get_nowait())
            except queue.Empty:
                break
        return notifications


def initialize_session_state():
    """Инициализация состояния сессии Streamlit."""
    if "agent" not in st.session_state:
        st.session_state.agent = SyncReminderAgent()
    
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Привет! Я агент для установки напоминаний. Напиши что-то вроде:\n\n\"напомни через 30 секунд попить кофе\"\n\nили\n\n\"какие задачи ожидают выполнения?\""
            }
        ]
    
    if "notification_manager" not in st.session_state:
        st.session_state.notification_manager = NotificationManager(st.session_state.agent)
    
    if "tasks_refreshed" not in st.session_state:
        st.session_state.tasks_refreshed = 0
    
    if "connected" not in st.session_state:
        st.session_state.connected = False


def display_chat_history():
    """Отображение истории чата."""
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.messages:
            if message["role"] == "user":
                with st.chat_message("user", avatar="👤"):
                    st.markdown(message["content"])
            else:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(message["content"])


def handle_user_input(user_input: str):
    """Обработка ввода пользователя."""
    if not user_input.strip():
        return
    
    # Добавляем сообщение пользователя в историю
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Отображаем сообщение пользователя
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)
    
    # Обрабатываем запрос через агента
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Думаю..."):
            response = st.session_state.agent.process(user_input)
            st.markdown(response)
    
    # Добавляем ответ ассистента в историю
    st.session_state.messages.append({"role": "assistant", "content": response})


def display_active_tasks():
    """Отображение активных задач в сайдбаре."""
    st.sidebar.title("📋 Активные задачи")
    
    if st.sidebar.button("🔄 Обновить список", use_container_width=True):
        st.session_state.tasks_refreshed += 1
    
    try:
        # Получаем список ожидающих задач
        result = st.session_state.agent.call_mcp_tool("list_tasks", {"status": "pending"})
        
        if "tasks" in result and result["tasks"]:
            tasks = result["tasks"]
            
            for task in tasks:
                try:
                    run_at = datetime.fromisoformat(task["run_at"])
                    now = datetime.now()
                    
                    if run_at > now:
                        seconds_left = int((run_at - now).total_seconds())
                        
                        if seconds_left < 60:
                            time_left = f"через {seconds_left} секунд"
                        elif seconds_left < 3600:
                            minutes = seconds_left // 60
                            seconds = seconds_left % 60
                            time_left = f"через {minutes} мин {seconds} сек"
                        else:
                            hours = seconds_left // 3600
                            minutes = (seconds_left % 3600) // 60
                            time_left = f"через {hours} час {minutes} мин"
                        
                        st.sidebar.markdown(f"""
                        <div class="task-list">
                            <strong>{task['message']}</strong><br>
                            <small>⏰ {time_left}</small>
                        </div>
                        """, unsafe_allow_html=True)
                except Exception as e:
                    st.sidebar.error(f"Ошибка при обработке задачи: {e}")
        else:
            st.sidebar.info("Нет активных задач")
    
    except Exception as e:
        st.sidebar.error(f"Не удалось загрузить задачи: {e}")


def display_statistics():
    """Отображение статистики в сайдбаре."""
    st.sidebar.divider()
    st.sidebar.title("📊 Статистика")
    
    try:
        # Получаем все задачи
        result = st.session_state.agent.call_mcp_tool("list_tasks", {"status": "all"})
        
        if "tasks" in result:
            tasks = result["tasks"]
            pending = len([t for t in tasks if t["status"] == "pending"])
            done = len([t for t in tasks if t["status"] == "done"])
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                st.metric("⏳ Ожидают", pending)
            with col2:
                st.metric("✅ Выполнены", done)
    except:
        st.sidebar.info("Статистика недоступна")


def main():
    """Основная функция приложения."""
    setup_page()
    initialize_session_state()
    
    # Заголовок приложения
    st.title("🤖 MCP Scheduler Agent")
    st.markdown("Агент с LLM и планировщиком задач")
    st.divider()
    
    # Подключаемся к агенту
    if not st.session_state.connected:
        with st.spinner("Подключаюсь к агенту..."):
            try:
                st.session_state.agent.connect()
                st.session_state.notification_manager.start()
                st.session_state.connected = True
                st.success("✅ Подключено к агенту")
            except Exception as e:
                st.error(f"❌ Ошибка подключения: {e}")
    
    # Основной контейнер для чата
    main_container = st.container()
    
    with main_container:
        # Отображаем историю чата
        display_chat_history()
        
        # Обработка уведомлений
        if st.session_state.connected:
            notifications = st.session_state.notification_manager.get_notifications()
            for notification in notifications:
                st.toast(f"🔔 {notification['message']}", icon="⏰")
        
        # Поле для ввода сообщения
        user_input = st.chat_input("💬 Введите сообщение...")
        
        if user_input:
            handle_user_input(user_input)
            # Обновляем страницу для отображения новых сообщений
            st.rerun()
    
    # Садбар с задачами и статистикой
    with st.sidebar:
        if st.session_state.connected:
            display_active_tasks()
            display_statistics()
            
            st.divider()
            
            # Управление
            st.title("⚙️ Управление")
            
            if st.button("🧹 Очистить чат", use_container_width=True):
                st.session_state.messages = [
                    {
                        "role": "assistant",
                        "content": "Чат очищен. Чем могу помочь?"
                    }
                ]
                st.rerun()
            
            if st.button("🔄 Переподключиться", use_container_width=True):
                try:
                    st.session_state.agent.close()
                    st.session_state.agent = SyncReminderAgent()
                    st.session_state.agent.connect()
                    st.session_state.notification_manager.stop()
                    st.session_state.notification_manager = NotificationManager(st.session_state.agent)
                    st.session_state.notification_manager.start()
                    st.success("✅ Переподключено")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка переподключения: {e}")
        else:
            st.warning("Агент не подключен")
    
    # Футер
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("🤖 LLM Agent")
    with col2:
        st.caption("⏰ APScheduler")
    with col3:
        st.caption("💾 SQLite")


if __name__ == "__main__":
    main()