import re
import os
from datetime import datetime


def get_safe_name(name: str):
    """Очистка имени папки от запрещенных символов"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def format_time(dt):
    """Безопасное форматирование: возвращает ЧЧ:ММ"""
    if not dt:
        return ""
    if hasattr(dt, 'strftime'):
        return dt.strftime('%H:%M')

    # Если пришла строка "2026-04-15 13:47:19.473026"
    dt_str = str(dt)
    if ' ' in dt_str:
        # Берем часть после пробела и отрезаем секунды
        return dt_str.split(' ')[1][:5]
    return dt_str[:5]


def write_to_history(folder_path: str, author: str, text: str, file_name: str = None, action=""):
    """Запись в историю проекта (history.txt)"""
    history_path = os.path.join(folder_path, "history.txt")
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    file_info = f"\n[Файл: {file_name}]" if file_name else ""
    action_info = f" ({action})" if action else ""

    with open(history_path, "a", encoding="utf-16") as f:
        f.write(f"[{timestamp}] {author}{action_info}:\n{text}{file_info}\n")
        f.write("-" * 30 + "\n")