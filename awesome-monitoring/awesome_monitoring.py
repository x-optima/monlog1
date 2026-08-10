#!/usr/bin/env python3
"""
Сбор метрик сервера для дополнительного задания.

Читает данные из /proc.
Для диска дополнительно используется os.statvfs (это допускается заданием).

Результат — одна JSON-строка в файле:
  /var/log/YY-MM-DD-awesome-monitoring.log

Если нет прав на /var/log, каталог можно задать переменной LOG_DIR.
Запуск по расписанию — через cron (см. crontab.example).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


# Каталог для файлов журнала. По условию задания — /var/log.
# Пример переопределения: LOG_DIR=./logs python3 awesome_monitoring.py
LOG_DIR = Path(os.environ.get("LOG_DIR", "/var/log"))


def read_text(path: Path) -> str:
    """Читает текстовый файл и убирает пробелы по краям."""
    # encoding=utf-8 — обычная кодировка текстов в Linux
    # errors='replace' — не прерывать работу, если встретился некорректный байт
    return path.read_text(encoding="utf-8", errors="replace").strip()


def collect_loadavg() -> Dict[str, float]:
    """
    Средняя загрузка системы за 1, 5 и 15 минут.
    Источник: /proc/loadavg
    """
    # Пример строки: 0.12 0.34 0.56 1/234 5678
    parts = read_text(Path("/proc/loadavg")).split()

    # Первые три поля — средние значения загрузки
    return {
        "loadavg_1m": float(parts[0]),
        "loadavg_5m": float(parts[1]),
        "loadavg_15m": float(parts[2]),
    }


def collect_memory() -> Dict[str, int]:
    """
    Оперативная память в килобайтах.
    Источник: /proc/meminfo
    """
    values: Dict[str, int] = {}

    # Разбираем файл построчно: «Имя:  число kB»
    for line in read_text(Path("/proc/meminfo")).splitlines():
        key, raw_value = line.split(":", 1)
        # Берём только число, единицу измерения (kB) отбрасываем
        number = int(raw_value.strip().split()[0])
        values[key] = number

    # MemAvailable — оценка памяти, доступной новым процессам
    mem_total = values["MemTotal"]
    mem_available = values["MemAvailable"]
    # Использованный объём считаем самостоятельно
    mem_used = mem_total - mem_available

    return {
        "mem_total_kb": mem_total,
        "mem_available_kb": mem_available,
        "mem_used_kb": mem_used,
        # Процент занятости, округление до сотых
        "mem_used_percent": round(mem_used * 100.0 / mem_total, 2),
    }


def collect_cpu() -> Dict[str, float]:
    """
    Доли времени процессора по состояниям.
    Источник: /proc/stat, первая строка «cpu ...»
    """
    # Берём сводную строку по всем ядрам (не cpu0, cpu1, ...)
    first_line = read_text(Path("/proc/stat")).splitlines()[0]

    # После слова «cpu» идут целочисленные счётчики времени
    fields = [int(x) for x in first_line.split()[1:]]

    # Индексы полей ядра Linux:
    # 0 — пользовательское время (user)
    # 1 — время процессов с изменённым приоритетом (nice)
    # 2 — системное время (system)
    # 3 — время простоя (idle)
    user, nice, system, idle = fields[0], fields[1], fields[2], fields[3]

    # Сумма всех полей нужна для перевода счётчиков в проценты
    # «or 1» — защита от деления на ноль
    total = sum(fields) or 1

    return {
        "cpu_user_percent": round(user * 100.0 / total, 2),
        "cpu_system_percent": round(system * 100.0 / total, 2),
        "cpu_idle_percent": round(idle * 100.0 / total, 2),
        "cpu_nice_percent": round(nice * 100.0 / total, 2),
    }


def collect_processes() -> Dict[str, int]:
    """
    Число процессов и потоков.
    Процессы: каталоги /proc/<pid>
    Потоки: поле из /proc/loadavg
    """
    # В /proc у каждого процесса есть каталог с числовым именем (PID)
    proc_dirs = [
        entry
        for entry in Path("/proc").iterdir()
        if entry.is_dir() and entry.name.isdigit()
    ]

    # Четвёртое поле loadavg имеет вид «исполняется/всего», например 1/234
    threads_field = read_text(Path("/proc/loadavg")).split()[3]
    # Нас интересует общее число потоков — правая часть после «/»
    threads_total = int(threads_field.split("/")[1])

    return {
        "processes_count": len(proc_dirs),
        "threads_count": threads_total,
    }


def collect_uptime() -> Dict[str, float]:
    """
    Время непрерывной работы системы в секундах.
    Источник: /proc/uptime
    """
    # В файле два числа: секунды работы и сумма времени простоя
    # Для задания достаточно первого числа
    uptime_seconds = float(read_text(Path("/proc/uptime")).split()[0])
    return {
        "uptime_seconds": round(uptime_seconds, 2),
    }


def collect_disk() -> Dict[str, Any]:
    """
    Заполнение корневого раздела («/»).
    Используется os.statvfs — в задании разрешено выходить за пределы /proc.
    """
    # Статистика файловой системы корневого раздела
    st = os.statvfs("/")

    # f_blocks — всего блоков, f_frsize — размер блока в байтах
    total = st.f_blocks * st.f_frsize
    # f_bavail — блоки, доступные обычному пользователю
    free = st.f_bavail * st.f_frsize
    used = total - free

    # Если размер раздела определить не удалось, процент считаем нулём
    if total:
        used_percent = round(used * 100.0 / total, 2)
    else:
        used_percent = 0.0

    return {
        "disk_root_total_bytes": total,
        "disk_root_used_bytes": used,
        "disk_root_free_bytes": free,
        "disk_root_used_percent": used_percent,
    }


def collect_metrics() -> Dict[str, Any]:
    """
    Собирает все группы метрик в один словарь.
    По заданию в записи должен быть timestamp и не менее 4 метрик.
    """
    metrics: Dict[str, Any] = {
        # Временная метка: секунды с 1970-01-01 UTC (Unix time), целое число
        "timestamp": int(time.time()),
    }

    # Добавляем показатели по группам
    metrics.update(collect_loadavg())
    metrics.update(collect_memory())
    metrics.update(collect_cpu())
    metrics.update(collect_processes())
    metrics.update(collect_uptime())
    metrics.update(collect_disk())

    return metrics


def log_path_for_today() -> Path:
    """
    Путь к файлу журнала за текущий день.
    Шаблон имени из задания: YY-MM-DD-awesome-monitoring.log
    """
    # %y — год двумя цифрами, %m — месяц, %d — день
    date_part = time.strftime("%y-%m-%d")
    return LOG_DIR / f"{date_part}-awesome-monitoring.log"


def write_metrics(metrics: Dict[str, Any]) -> Path:
    """
    Дописывает одну JSON-строку в конец дневного файла.
    Возвращает путь к файлу.
    """
    # Создаём каталог журналов, если его ещё нет
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    target = log_path_for_today()

    # separators=(",", ":") — без пробелов после : и ,
    # ensure_ascii=False — не кодировать Unicode как \uXXXX
    line = json.dumps(metrics, ensure_ascii=False, separators=(",", ":"))

    # Режим «a» — дописать в конец, не затирая предыдущие записи
    with target.open("a", encoding="utf-8") as handle:
        # Каждая запись — отдельная строка (JSON Lines)
        handle.write(line + "\n")

    return target


def main() -> None:
    """Точка входа: сбор, запись в журнал, вывод в консоль."""
    metrics = collect_metrics()
    path = write_metrics(metrics)

    # Вывод нужен при ручном запуске и при проверке работы из cron
    print(f"Wrote metrics to {path}")
    # Второй print — тот же набор метрик в читаемом виде
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


# Запуск файла напрямую: python3 awesome_monitoring.py
if __name__ == "__main__":
    main()
