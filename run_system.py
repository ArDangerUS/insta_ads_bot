#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram Bot Management System - Launcher
Полноценная система управления Instagram ботами
"""

import os
import sys
import subprocess
import time
from pathlib import Path


def check_dependencies():
    """Проверка и установка зависимостей"""
    print("🔍 Проверка зависимостей...")

    required_packages = [
        'flask',
        'flask-socketio',
        'instagrapi',
        'requests'
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} - установлен")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} - не найден")

    if missing_packages:
        print(f"\n📦 Установка недостающих пакетов: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install',
                *missing_packages
            ])
            print("✅ Все зависимости установлены!")
        except subprocess.CalledProcessError:
            print("❌ Ошибка установки зависимостей")
            return False

    return True


def create_directory_structure():
    """Создание структуры директорий"""
    print("📁 Создание структуры директорий...")

    directories = [
        'templates',
        'static',
        'sessions',
        'logs',
        'backups'
    ]

    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Директория {directory} создана")


def create_html_template():
    """Создание HTML шаблона"""
    template_path = Path('templates/index.html')

    if not template_path.exists():
        print("📝 Создание HTML шаблона...")

        # Читаем HTML из артефакта (в реальной системе это будет отдельный файл)
        html_content = """<!-- Здесь должен быть HTML код из артефакта -->
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Bot Management System</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        /* CSS стили из артефакта */
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        /* Остальные стили... */
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Instagram Bot Management System</h1>
            <p class="subtitle">Система управления Instagram ботами</p>
        </div>
        <div id="app">Загрузка...</div>
    </div>
    <script>
        // JavaScript код из артефакта
        console.log('Instagram Bot Management System загружен');
    </script>
</body>
</html>"""

        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print("✅ HTML шаблон создан")


def check_configuration():
    """Проверка конфигурации"""
    print("⚙️ Проверка конфигурации...")

    # Проверяем наличие файла launcher.py
    if not Path('launcher.py').exists():
        print("❌ Файл launcher.py не найден!")
        print("📝 Скопируйте ваш код Instagram бота в файл launcher.py")
        return False

    print("✅ Основной файл launcher.py найден")
    return True


def run_system():
    """Запуск системы"""
    print("\n🚀 ЗАПУСК INSTAGRAM BOT MANAGEMENT SYSTEM")
    print("=" * 60)

    # Проверка всех компонентов
    if not check_dependencies():
        return False

    create_directory_structure()
    create_html_template()

    if not check_configuration():
        return False

    print("\n✅ Все проверки пройдены!")
    print("\n🌐 Запуск веб-сервера...")
    print("📍 URL: http://localhost:5000")
    print("🔄 Нажмите Ctrl+C для остановки")
    print("-" * 60)

    try:
        # Импортируем и запускаем основной модуль
        from instagram_bot_backend import app, socketio
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        print("📝 Убедитесь, что все файлы находятся в одной директории")
        return False

    except KeyboardInterrupt:
        print("\n\n🛑 Система остановлена пользователем")
        return True

    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        return False


def show_help():
    """Показать справку"""
    print("""
🤖 INSTAGRAM BOT MANAGEMENT SYSTEM - СПРАВКА
=""" + "=" * 50 + """

📋 СТРУКТУРА ФАЙЛОВ:
   launcher.py           - Ваш основной код Instagram бота
   instagram_bot_backend.py - Backend системы управления  
   run_system.py         - Этот файл (запускает систему)
   templates/index.html  - Веб-интерфейс
   sessions/            - Сессии Instagram аккаунтов
   logs/                - Логи системы

🚀 ЗАПУСК:
   python run_system.py

🌐 ИСПОЛЬЗОВАНИЕ:
   1. Откройте http://localhost:5000 в браузере
   2. Нажмите "➕ Добавить бота"
   3. Заполните данные аккаунта Instagram
   4. Нажмите "▶️ Запустить"
   5. Наблюдайте за работой в реальном времени

⚙️ ФУНКЦИИ:
   ✅ Добавление до 10 ботов
   ✅ Автоматический поиск лайкеров постов
   ✅ Лайки, подписки, отправка DM
   ✅ Умные фильтры пользователей
   ✅ Статистика в реальном времени
   ✅ Защита от блокировок

🔧 НАСТРОЙКИ:
   - Лимиты активности (лайки/подписки/сообщения в час)
   - Фильтры аудитории (подписчики, посты, пол)
   - Персонализированные сообщения
   - Целевые аккаунты для поиска

📊 МОНИТОРИНГ:
   - Статус каждого бота
   - Количество лайков/подписок/сообщений
   - Логи активности
   - Уведомления об ошибках

🛡️ БЕЗОПАСНОСТЬ:
   - Умные задержки между действиями
   - Соблюдение лимитов Instagram
   - Обработка ошибок и переподключения
   - Сохранение сессий

❓ ПОМОЩЬ:
   - Все настройки имеют подсказки
   - Hover-эффекты показывают дополнительную информацию
   - Горячие клавиши: Ctrl+R (обновить), Ctrl+N (новый бот)

💡 СОВЕТЫ:
   - Начните с одного бота для тестирования
   - Используйте мягкие фильтры для большей аудитории
   - Регулярно проверяйте логи
   - Не превышайте рекомендуемые лимиты
""")


def create_example_config():
    """Создание примера конфигурации"""
    example_config = """
# Пример конфигурации бота

ПРИМЕР НАСТРОЕК БОТА:
{
    "username": "your_instagram_username",
    "password": "your_password", 
    "main_account": "your_main_account",
    "target_accounts": ["natgeo", "nasa", "bbcnews"],
    "message_template": "Привіт {name}! Цікавий контент на @{main_account} 🤖",
    "filters": {
        "min_followers": 50,
        "max_followers": 10000,
        "min_posts": 1,
        "exclude_verified_accounts": true
    },
    "limits": {
        "max_likes_per_hour": 8,
        "max_follows_per_hour": 4, 
        "max_messages_per_hour": 2
    }
}

РЕКОМЕНДУЕМЫЕ ЦЕЛЕВЫЕ АККАУНТЫ ДЛЯ УКРАИНСКОЙ АУДИТОРИИ:
- ukraine, kyiv_official (новости)
- natgeo, nasa (образование)  
- designfeed, behance (дизайн)
- techcrunch, theverge (технологии)
"""

    with open('example_config.txt', 'w', encoding='utf-8') as f:
        f.write(example_config)

    print("📄 Пример конфигурации создан: example_config.txt")


if __name__ == "__main__":
    print("""
🤖 INSTAGRAM BOT MANAGEMENT SYSTEM v1.0
=""" + "=" * 50)

    if len(sys.argv) > 1:
        if sys.argv[1] == '--help' or sys.argv[1] == '-h':
            show_help()
        elif sys.argv[1] == '--example':
            create_example_config()
        else:
            print("❓ Неизвестная команда. Используйте --help для справки")
    else:
        # Запуск основной системы
        success = run_system()

        if not success:
            print("\n❌ Система не смогла запуститься")
            print("💡 Попробуйте: python run_system.py --help")
            sys.exit(1)
        else:
            print("\n✅ Система завершена успешно")
            sys.exit(0)