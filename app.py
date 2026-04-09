"""
Streamlit UI для агента напоминаний.
Включает чат с агентом и фоновый polling для уведомлений.
Запуск: streamlit run app.py
"""

import streamlit as st
import threading
import time
from datetime import datetime

from streamlit_autorefresh import st_autorefresh
from agent import SyncReminderAgent


# === Конфигурация страницы ===
st.set_page_config(
    page_title="MCP Scheduler Agent",
    page_icon="🤖",
    layout="centered"
)


# === Глобальное хранилище уведомлений (thread-safe) ===
_notifications = []
_notifications_lock = threading.Lock()
_polling_started = False


def get_notifications():
    """Получить и очистить очередь уведомлений."""
    global _notifications
    with _notifications_lock:
        notifications = list(_notifications)
        _notifications.clear()
    return notifications


def add_notification(message: str):
    """Добавить уведомление в очередь (из любого потока)."""
    global _notifications
    with _notifications_lock:
        _notifications.append(message)


def poll_notifications(agent: SyncReminderAgent):
    """Фоновый поток для проверки уведомлений.
    
    НЕ вызывает Streamlit API напрямую!
    Только добавляет уведомления в очередь.
    """
    while True:
        try:
            due_tasks = agent.call_mcp_tool("get_due_tasks", {})
            if due_tasks and isinstance(due_tasks, list):
                for task in due_tasks:
                    add_notification(f"🔔 {task['message']}")
                    agent.call_mcp_tool(
                        "mark_done",
                        {"task_id": task["id"]}
                    )
        except Exception:
            pass
        time.sleep(1)


def start_polling(agent: SyncReminderAgent):
    """Запуск фонового потока polling."""
    global _polling_started
    if not _polling_started:
        thread = threading.Thread(
            target=poll_notifications,
            args=(agent,),
            daemon=True
        )
        thread.start()
        _polling_started = True


# === Инициализация состояния ===
if "agent" not in st.session_state:
    st.session_state.agent = None
    st.session_state.connected = False
    st.session_state.messages = []


def connect_agent() -> bool:
    """Подключение агента к MCP-серверу."""
    if st.session_state.agent is None:
        st.session_state.agent = SyncReminderAgent()
        try:
            st.session_state.agent.connect()
            st.session_state.connected = True
            return True
        except Exception as e:
            st.error(f"Ошибка подключения: {e}")
            return False
    return True


# === Подключение агента ===
if not st.session_state.connected:
    with st.spinner("Подключение к MCP-серверу..."):
        if connect_agent():
            st.success("✅ Агент подключён!")
            start_polling(st.session_state.agent)
            st.rerun()
        else:
            st.error("❌ Не удалось подключиться к серверу")
            st.stop()


# === Авто-обновление каждые 2 секунды для проверки уведомлений ===
st_autorefresh(interval=2000, limit=None, key="notification_refresh")


# === Показываем уведомления из очереди (в основном потоке!) ===
notifications = get_notifications()
for msg in notifications:
    st.toast(msg, icon="⏰")


# === Заголовок ===
st.title("🤖 MCP Scheduler Agent")
st.caption("Агент с LLM и планировщиком задач")


# === Отображение истории чата ===
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# === Ввод пользователя ===
if prompt := st.chat_input("Введите сообщение..."):
    # Добавляем сообщение пользователя
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Получаем ответ от агента
    with st.chat_message("assistant"):
        with st.spinner("Думаю..."):
            try:
                agent = st.session_state.agent
                if agent:
                    response = agent.process(prompt)
                else:
                    response = "Агент не подключён"
            except Exception as e:
                response = f"Произошла ошибка: {e}"

        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})

    # Проверяем уведомления сразу после обработки
    notifications = get_notifications()
    for msg in notifications:
        st.toast(msg, icon="⏰")


# === Боковая панель с активными задачами ===
with st.sidebar:
    st.header("📋 Активные задачи")

    if st.session_state.agent and st.session_state.connected:
        try:
            tasks = st.session_state.agent.call_mcp_tool(
                "list_tasks",
                {"status": "pending"}
            )

            if tasks and isinstance(tasks, list) and len(tasks) > 0:
                for task in tasks:
                    run_at = datetime.fromisoformat(task["run_at"])
                    now = datetime.now()
                    delta = run_at - now

                    if delta.total_seconds() > 0:
                        minutes = int(delta.total_seconds() // 60)
                        seconds = int(delta.total_seconds() % 60)

                        if minutes > 0:
                            time_str = f"{minutes} мин {seconds} сек"
                        else:
                            time_str = f"{seconds} сек"

                        st.markdown(f"• **{task['message']}** → через {time_str}")
                    else:
                        st.markdown(f"• **{task['message']}** → сейчас")
            else:
                st.info("Нет активных задач")
        except Exception as e:
            st.error(f"Ошибка: {e}")
    else:
        st.warning("Агент не подключён")

    st.divider()
    st.caption("Для создания напоминания напишите:")
    st.code('"Напомни через 30 секунд попить кофе"', language="text")
