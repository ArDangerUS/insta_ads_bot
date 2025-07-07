#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram Bot Management System - КРОССПЛАТФОРМЕННЫЙ Backend
Совместимость: Windows, Linux, VPS
Решение проблемы бесконечных запросов без fcntl
"""

import asyncio
import json
import threading
import time
import uuid
import platform
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import logging
import sqlite3

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.serving import make_server
import queue

# Импортируем классы из исправленного launcher
from launcher import (
    FixedInstagramBot, BotConfig, UserFilter, Gender,
    InteractionType, DatabaseManager, CrossPlatformLockManager
)

# Попробуем импортировать поддержку прокси
try:
    from launcher import ProxyConfig, ProxyManager, test_proxy_api

    PROXY_SUPPORT = True
except ImportError:
    PROXY_SUPPORT = False
    print("⚠️ Поддержка прокси не найдена в launcher.py")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'instagram_bot_secret_key_2025'
socketio = SocketIO(app, cors_allowed_origins="*")


class CrossPlatformBotManager:
    """Кроссплатформенный менеджер ботов с поддержкой прокси"""

    def __init__(self):
        self.bots: Dict[str, FixedInstagramBot] = {}
        self.bot_threads: Dict[str, threading.Thread] = {}
        self.bot_configs: Dict[str, BotConfig] = {}
        self.session_manager = CrossPlatformLockManager()
        self.db = DatabaseManager("bot_management.db")

        self.init_management_db()
        self.load_configs_from_db()

        # Очистка при запуске
        self.session_manager.cleanup_stale_locks()

        logger.info(f"🖥️ Менеджер ботов запущен на {platform.system()}")

    def init_management_db(self):
        """Инициализация БД управления с поддержкой прокси"""
        with sqlite3.connect("bot_management.db") as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_configurations (
                    id TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT TRUE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_status (
                    bot_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT,
                    session_locked BOOLEAN DEFAULT FALSE,
                    platform TEXT,
                    proxy_host TEXT,
                    proxy_port INTEGER,
                    proxy_type TEXT,
                    FOREIGN KEY (bot_id) REFERENCES bot_configurations (id)
                )
            """)

            # Добавляем столбцы для прокси если их нет
            try:
                cursor.execute("ALTER TABLE bot_status ADD COLUMN proxy_host TEXT")
                cursor.execute("ALTER TABLE bot_status ADD COLUMN proxy_port INTEGER")
                cursor.execute("ALTER TABLE bot_status ADD COLUMN proxy_type TEXT")
            except sqlite3.OperationalError:
                # Столбцы уже существуют
                pass

            conn.commit()

    def save_config_to_db(self, config: BotConfig):
        """Сохранение конфигурации в БД с поддержкой прокси"""
        config_dict = {
            'bot_id': config.bot_id,
            'username': config.username,
            'password': config.password,
            'target_accounts': config.target_accounts,
            'message_template': config.message_template,
            'main_account': config.main_account,
            'active': config.active,
            'max_likes_per_hour': config.max_likes_per_hour,
            'max_follows_per_hour': config.max_follows_per_hour,
            'max_messages_per_hour': config.max_messages_per_hour,
            'min_delay': config.min_delay,
            'max_delay': config.max_delay,
            'posts_to_like': config.posts_to_like,
            'posts_to_analyze': config.posts_to_analyze,
            'message_variants': config.message_variants,
            'personalized_messages': config.personalized_messages,
            'interaction_types': [t.value for t in config.interaction_types],
            'proxy': config.proxy.to_dict() if hasattr(config, 'proxy') and config.proxy else None,
            'filters': {
                'min_followers': config.filters.min_followers,
                'max_followers': config.filters.max_followers,
                'min_following': config.filters.min_following,
                'max_following': config.filters.max_following,
                'min_posts': config.filters.min_posts,
                'has_profile_pic': config.filters.has_profile_pic,
                'private_account': config.filters.private_account,
                'countries': config.filters.countries,
                'languages': config.filters.languages,
                'gender': config.filters.gender.value,
                'engagement_rate_min': config.filters.engagement_rate_min,
                'engagement_rate_max': config.filters.engagement_rate_max,
                'exclude_business_accounts': config.filters.exclude_business_accounts,
                'exclude_verified_accounts': config.filters.exclude_verified_accounts,
                'required_keywords_in_bio': config.filters.required_keywords_in_bio,
                'excluded_keywords_in_bio': config.filters.excluded_keywords_in_bio
            }
        }

        with sqlite3.connect("bot_management.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO bot_configurations (id, config_json, updated_at)
                VALUES (?, ?, ?)
            """, (config.bot_id, json.dumps(config_dict), datetime.now()))
            conn.commit()

    def load_configs_from_db(self):
        """Загрузка конфигураций из БД с поддержкой прокси"""
        with sqlite3.connect("bot_management.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, config_json FROM bot_configurations WHERE active = TRUE")

            for bot_id, config_json in cursor.fetchall():
                try:
                    config_dict = json.loads(config_json)
                    config = self._dict_to_config(config_dict)
                    self.bot_configs[bot_id] = config
                except Exception as e:
                    logger.error(f"Ошибка загрузки конфигурации {bot_id}: {e}")

    def _dict_to_config(self, config_dict: dict) -> BotConfig:
        """Преобразование словаря в BotConfig с поддержкой прокси"""
        filters_dict = config_dict['filters']
        filters = UserFilter(
            min_followers=filters_dict['min_followers'],
            max_followers=filters_dict['max_followers'],
            min_following=filters_dict['min_following'],
            max_following=filters_dict['max_following'],
            min_posts=filters_dict['min_posts'],
            has_profile_pic=filters_dict['has_profile_pic'],
            private_account=filters_dict['private_account'],
            countries=filters_dict['countries'],
            languages=filters_dict['languages'],
            gender=Gender(filters_dict['gender']),
            engagement_rate_min=filters_dict['engagement_rate_min'],
            engagement_rate_max=filters_dict['engagement_rate_max'],
            exclude_business_accounts=filters_dict['exclude_business_accounts'],
            exclude_verified_accounts=filters_dict['exclude_verified_accounts'],
            required_keywords_in_bio=filters_dict['required_keywords_in_bio'],
            excluded_keywords_in_bio=filters_dict['excluded_keywords_in_bio']
        )

        interaction_types = [InteractionType(t) for t in config_dict['interaction_types']]

        # Обработка прокси
        proxy = None
        if PROXY_SUPPORT and config_dict.get('proxy'):
            proxy_data = config_dict['proxy']
            proxy = ProxyConfig(
                host=proxy_data['host'],
                port=proxy_data['port'],
                username=proxy_data.get('username'),
                password=proxy_data.get('password'),
                type=proxy_data['type']
            )

        return BotConfig(
            bot_id=config_dict['bot_id'],
            username=config_dict['username'],
            password=config_dict['password'],
            target_accounts=config_dict['target_accounts'],
            filters=filters,
            message_template=config_dict['message_template'],
            main_account=config_dict['main_account'],
            active=config_dict['active'],
            proxy=proxy,
            max_likes_per_hour=config_dict['max_likes_per_hour'],
            max_follows_per_hour=config_dict['max_follows_per_hour'],
            max_messages_per_hour=config_dict['max_messages_per_hour'],
            min_delay=config_dict['min_delay'],
            max_delay=config_dict['max_delay'],
            posts_to_like=config_dict['posts_to_like'],
            posts_to_analyze=config_dict['posts_to_analyze'],
            message_variants=config_dict['message_variants'],
            personalized_messages=config_dict['personalized_messages'],
            interaction_types=interaction_types
        )

    def add_bot(self, config: BotConfig) -> bool:
        """Добавление нового бота с проверкой сессий"""
        try:
            # Проверяем активные сессии
            active_sessions = self.session_manager.get_active_sessions()
            if config.username in active_sessions:
                logger.error(f"❌ Аккаунт {config.username} уже используется")
                return False

            # Проверяем дублирование в конфигах
            for existing_config in self.bot_configs.values():
                if existing_config.username == config.username:
                    logger.error(f"❌ Бот с аккаунтом {config.username} уже существует")
                    return False

            self.bot_configs[config.bot_id] = config
            self.save_config_to_db(config)

            proxy_info = f" с прокси {config.proxy.host}:{config.proxy.port}" if config.proxy else " без прокси"
            logger.info(f"✅ Бот {config.username} добавлен{proxy_info}")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления бота {config.username}: {e}")
            return False

    def start_bot(self, bot_id: str) -> bool:
        """Запуск бота с кроссплатформенными блокировками"""
        try:
            if bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive():
                logger.warning(f"⚠️ Бот {bot_id} уже запущен")
                return False

            config = self.bot_configs.get(bot_id)
            if not config:
                logger.error(f"❌ Конфигурация для бота {bot_id} не найдена")
                return False

            # Проверяем и захватываем сессию
            if not self.session_manager.acquire_lock(config.username):
                logger.error(f"❌ Не удалось захватить сессию для {config.username}")
                self.update_bot_status(bot_id, "error", "Сессия уже используется")
                return False

            # Небольшая пауза для завершения предыдущих операций
            time.sleep(3)

            proxy_info = f" с прокси {config.proxy.host}:{config.proxy.port}" if config.proxy else ""
            logger.info(f"🚀 Создание бота для {config.username}{proxy_info}...")
            bot = FixedInstagramBot(config)
            self.bots[bot_id] = bot

            def run_bot():
                try:
                    logger.info(f"🏃 Запуск потока бота {config.username}")
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(bot.start())
                except Exception as e:
                    logger.error(f"❌ Ошибка работы бота {bot_id}: {e}")
                    self.update_bot_status(bot_id, "error", str(e))
                finally:
                    # ОБЯЗАТЕЛЬНО освобождаем сессию
                    self.session_manager.release_lock(config.username)
                    logger.info(f"🔓 Сессия {config.username} освобождена")

            thread = threading.Thread(target=run_bot, daemon=True, name=f"Bot-{config.username}")
            thread.start()
            self.bot_threads[bot_id] = thread

            # Обновляем статус с информацией о прокси
            self.update_bot_status(
                bot_id, "running", None, session_locked=True,
                proxy_host=config.proxy.host if config.proxy else None,
                proxy_port=config.proxy.port if config.proxy else None,
                proxy_type=config.proxy.type if config.proxy else None
            )
            logger.info(f"✅ Бот {config.username} запущен успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска бота {bot_id}: {e}")

            # Освобождаем сессию при ошибке
            config = self.bot_configs.get(bot_id)
            if config:
                self.session_manager.release_lock(config.username)

            self.update_bot_status(bot_id, "error", str(e))
            return False

    def stop_bot(self, bot_id: str) -> bool:
        """Остановка бота"""
        try:
            config = self.bot_configs.get(bot_id)

            # Останавливаем бота
            if bot_id in self.bots:
                self.bots[bot_id].stop()
                logger.info(f"🛑 Команда остановки отправлена боту {bot_id}")
                del self.bots[bot_id]

            # Ждем завершения потока
            if bot_id in self.bot_threads:
                thread = self.bot_threads[bot_id]
                if thread.is_alive():
                    logger.info(f"⏳ Ожидание завершения потока бота {bot_id}...")
                    thread.join(timeout=15)

                del self.bot_threads[bot_id]

            # ОБЯЗАТЕЛЬНО освобождаем сессию
            if config:
                self.session_manager.release_lock(config.username)
                logger.info(f"🔓 Сессия {config.username} освобождена при остановке")

            self.update_bot_status(bot_id, "stopped", None, session_locked=False)
            logger.info(f"✅ Бот {bot_id} остановлен")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка остановки бота {bot_id}: {e}")
            return False

    def update_bot_status(self, bot_id: str, status: str, error_message: str = None,
                          session_locked: bool = None, proxy_host: str = None,
                          proxy_port: int = None, proxy_type: str = None):
        """Обновление статуса бота с информацией о платформе и прокси"""
        with sqlite3.connect("bot_management.db") as conn:
            cursor = conn.cursor()

            if session_locked is not None:
                cursor.execute("""
                    INSERT OR REPLACE INTO bot_status 
                    (bot_id, status, last_activity, error_message, session_locked, platform, proxy_host, proxy_port, proxy_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (bot_id, status, datetime.now(), error_message, session_locked,
                      platform.system(), proxy_host, proxy_port, proxy_type))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO bot_status 
                    (bot_id, status, last_activity, error_message, platform, proxy_host, proxy_port, proxy_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (bot_id, status, datetime.now(), error_message,
                      platform.system(), proxy_host, proxy_port, proxy_type))

            conn.commit()

        # Отправляем обновление через WebSocket
        socketio.emit('bot_status_update', {
            'bot_id': bot_id,
            'status': status,
            'error_message': error_message,
            'session_locked': session_locked,
            'platform': platform.system(),
            'proxy': {
                'host': proxy_host,
                'port': proxy_port,
                'type': proxy_type
            } if proxy_host else None,
            'timestamp': datetime.now().isoformat()
        })

    def get_bot_status(self, bot_id: str) -> dict:
        """Получение статуса бота с информацией о прокси"""
        with sqlite3.connect("bot_management.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, last_activity, error_message, session_locked, platform, 
                       proxy_host, proxy_port, proxy_type
                FROM bot_status WHERE bot_id = ?
            """, (bot_id,))

            result = cursor.fetchone()
            if result:
                status, last_activity, error_message, session_locked, bot_platform, proxy_host, proxy_port, proxy_type = result
                return {
                    'status': status,
                    'last_activity': last_activity,
                    'error_message': error_message,
                    'session_locked': bool(session_locked),
                    'platform': bot_platform or platform.system(),
                    'proxy': {
                        'host': proxy_host,
                        'port': proxy_port,
                        'type': proxy_type
                    } if proxy_host else None,
                    'is_running': bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive()
                }
            else:
                return {
                    'status': 'not_started',
                    'last_activity': None,
                    'error_message': None,
                    'session_locked': False,
                    'platform': platform.system(),
                    'proxy': None,
                    'is_running': False
                }

    def get_all_bots_status(self) -> dict:
        """Получение статуса всех ботов"""
        result = {}
        for bot_id in self.bot_configs:
            result[bot_id] = self.get_bot_status(bot_id)
        return result

    def get_bot_statistics(self, bot_id: str) -> dict:
        """Получение статистики бота"""
        if bot_id in self.bots:
            return self.bots[bot_id].get_statistics()
        else:
            # Получаем статистику из БД
            with sqlite3.connect("instagram_bot.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        action_type,
                        COUNT(*) as total,
                        COUNT(CASE WHEN success = 1 THEN 1 END) as success,
                        COUNT(CASE WHEN success = 0 THEN 1 END) as errors
                    FROM bot_activity 
                    WHERE bot_id = ? 
                    GROUP BY action_type
                """, (bot_id,))

                stats = {}
                for row in cursor.fetchall():
                    action, total, success, errors = row
                    stats[action] = {'total': total, 'success': success, 'errors': errors}

                config = self.bot_configs.get(bot_id)
                return {
                    'total_stats': stats,
                    'hourly_stats': {},
                    'is_running': bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive(),
                    'username': config.username if config else 'Unknown',
                    'platform': platform.system(),
                    'proxy': config.proxy.to_dict() if config and config.proxy else None
                }

    def delete_bot(self, bot_id: str) -> bool:
        """Удаление бота"""
        try:
            # Сначала останавливаем
            self.stop_bot(bot_id)

            # Удаляем из конфигурации
            if bot_id in self.bot_configs:
                config = self.bot_configs[bot_id]

                # Убеждаемся, что сессия освобождена
                self.session_manager.release_lock(config.username)

                del self.bot_configs[bot_id]

            # Помечаем как неактивный в БД
            with sqlite3.connect("bot_management.db") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bot_configurations SET active = FALSE WHERE id = ?
                """, (bot_id,))
                conn.commit()

            logger.info(f"✅ Бот {bot_id} удален")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка удаления бота {bot_id}: {e}")
            return False

    def cleanup_inactive_sessions(self):
        """Очистка неактивных сессий"""
        try:
            active_sessions = self.session_manager.get_active_sessions()

            for username in active_sessions:
                # Проверяем, есть ли активные боты для этого username
                has_active_bot = False
                for bot_id, config in self.bot_configs.items():
                    if (config.username == username and
                            bot_id in self.bot_threads and
                            self.bot_threads[bot_id].is_alive()):
                        has_active_bot = True
                        break

                if not has_active_bot:
                    logger.info(f"🧹 Освобождение неактивной сессии: {username}")
                    self.session_manager.release_lock(username)

        except Exception as e:
            logger.error(f"Ошибка очистки сессий: {e}")

    def get_system_info(self) -> dict:
        """Получение информации о системе"""
        active_sessions = self.session_manager.get_active_sessions()

        # Подсчитываем боты с прокси
        bots_with_proxy = sum(1 for config in self.bot_configs.values() if hasattr(config, 'proxy') and config.proxy)

        return {
            'platform': platform.system(),
            'platform_release': platform.release(),
            'python_version': platform.python_version(),
            'active_sessions': len(active_sessions),
            'total_bots': len(self.bot_configs),
            'bots_with_proxy': bots_with_proxy,
            'proxy_support': PROXY_SUPPORT,
            'running_bots': len([t for t in self.bot_threads.values() if t.is_alive()]),
            'active_usernames': active_sessions,
            'working_directory': os.getcwd()
        }

    def stop_all_bots(self):
        """Остановка всех ботов (для корректного завершения)"""
        logger.info("🛑 Остановка всех ботов...")
        for bot_id in list(self.bot_configs.keys()):
            self.stop_bot(bot_id)

        # Дополнительная очистка сессий
        self.session_manager.cleanup_stale_locks()


# Глобальный КРОССПЛАТФОРМЕННЫЙ менеджер ботов
bot_manager = CrossPlatformBotManager()


# Маршруты Flask
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/bots', methods=['GET'])
def get_bots():
    """Получение списка всех ботов"""
    try:
        bots_data = []
        for bot_id, config in bot_manager.bot_configs.items():
            status = bot_manager.get_bot_status(bot_id)
            stats = bot_manager.get_bot_statistics(bot_id)

            bots_data.append({
                'id': bot_id,
                'username': config.username,
                'main_account': config.main_account,
                'target_accounts': config.target_accounts,
                'proxy': config.proxy.to_dict() if hasattr(config, 'proxy') and config.proxy else None,
                'status': status,
                'stats': stats
            })

        return jsonify(bots_data)
    except Exception as e:
        logger.error(f"Ошибка получения списка ботов: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/test-proxy', methods=['POST'])
def test_proxy():
    """Тестирование прокси"""
    if not PROXY_SUPPORT:
        return jsonify({'success': False, 'error': 'Поддержка прокси не установлена'}), 500

    try:
        proxy_data = request.json
        result = test_proxy_api(proxy_data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Ошибка тестирования прокси: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots', methods=['POST'])
def add_bot():
    """Добавление нового бота с поддержкой прокси"""
    try:
        data = request.json

        # Создаем фильтры
        filters_data = data.get('filters', {})
        filters = UserFilter(
            min_followers=filters_data.get('min_followers', 100),
            max_followers=filters_data.get('max_followers', 50000),
            min_following=filters_data.get('min_following', 50),
            max_following=filters_data.get('max_following', 5000),
            min_posts=filters_data.get('min_posts', 3),
            has_profile_pic=filters_data.get('has_profile_pic', True),
            private_account=filters_data.get('private_account', False),
            countries=filters_data.get('countries', []),
            languages=filters_data.get('languages', []),
            gender=Gender(filters_data.get('gender', 'any')),
            engagement_rate_min=filters_data.get('engagement_rate_min', 0.01),
            engagement_rate_max=filters_data.get('engagement_rate_max', 0.20),
            exclude_business_accounts=filters_data.get('exclude_business_accounts', False),
            exclude_verified_accounts=filters_data.get('exclude_verified_accounts', False),
            required_keywords_in_bio=filters_data.get('required_keywords_in_bio', []),
            excluded_keywords_in_bio=filters_data.get('excluded_keywords_in_bio', [])
        )

        # Обработка прокси
        proxy = None
        if PROXY_SUPPORT and data.get('proxy'):
            proxy_data = data['proxy']
            if proxy_data.get('host') and proxy_data.get('port') and proxy_data.get('type'):
                proxy = ProxyConfig(
                    host=proxy_data['host'],
                    port=int(proxy_data['port']),
                    username=proxy_data.get('username'),
                    password=proxy_data.get('password'),
                    type=proxy_data['type']
                )

        # Создаем конфигурацию
        config = BotConfig(
            bot_id=str(uuid.uuid4()),
            username=data['username'],
            password=data['password'],
            target_accounts=data['target_accounts'],
            filters=filters,
            message_template=data['message_template'],
            main_account=data['main_account'],
            proxy=proxy,
            max_likes_per_hour=data.get('max_likes_per_hour', 8),
            max_follows_per_hour=data.get('max_follows_per_hour', 4),
            max_messages_per_hour=data.get('max_messages_per_hour', 2),
            min_delay=data.get('min_delay', 300),
            max_delay=data.get('max_delay', 600),
            posts_to_like=data.get('posts_to_like', 2),
            posts_to_analyze=data.get('posts_to_analyze', 3),
            message_variants=data.get('message_variants', [data['message_template']]),
            personalized_messages=data.get('personalized_messages', True),
            interaction_types=[InteractionType(t) for t in data.get('interaction_types', ['both'])]
        )

        if bot_manager.add_bot(config):
            return jsonify({'success': True, 'bot_id': config.bot_id})
        else:
            return jsonify({'success': False, 'error': 'Failed to add bot (username already in use)'}), 400

    except Exception as e:
        logger.error(f"Ошибка добавления бота: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bots/<bot_id>/start', methods=['POST'])
def start_bot(bot_id):
    """Запуск бота"""
    if bot_manager.start_bot(bot_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to start bot (session conflict or error)'}), 500


@app.route('/api/bots/<bot_id>/stop', methods=['POST'])
def stop_bot(bot_id):
    """Остановка бота"""
    if bot_manager.stop_bot(bot_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to stop bot'}), 500


@app.route('/api/bots/<bot_id>', methods=['DELETE'])
def delete_bot(bot_id):
    """Удаление бота"""
    if bot_manager.delete_bot(bot_id):
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to delete bot'}), 500


@app.route('/api/bots/<bot_id>/statistics')
def get_bot_statistics(bot_id):
    """Получение статистики бота"""
    try:
        stats = bot_manager.get_bot_statistics(bot_id)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/status')
def get_system_status():
    """Получение общего статуса системы"""
    try:
        all_bots = bot_manager.get_all_bots_status()
        total_bots = len(all_bots)
        running_bots = sum(1 for status in all_bots.values() if status['is_running'])
        system_info = bot_manager.get_system_info()

        return jsonify({
            'total_bots': total_bots,
            'running_bots': running_bots,
            'stopped_bots': total_bots - running_bots,
            'bots_with_proxy': system_info['bots_with_proxy'],
            'proxy_support': system_info['proxy_support'],
            'system_uptime': time.time() - start_time,
            'platform': system_info['platform'],
            'platform_release': system_info['platform_release'],
            'python_version': system_info['python_version'],
            'active_sessions': system_info['active_sessions'],
            'active_usernames': system_info['active_usernames']
        })
    except Exception as e:
        logger.error(f"Ошибка получения статуса системы: {e}")
        return jsonify({'error': str(e)}), 500


# WebSocket события
@socketio.on('connect')
def handle_connect():
    emit('connected', {
        'data': 'Подключение установлено',
        'platform': platform.system(),
        'proxy_support': PROXY_SUPPORT,
        'server_time': datetime.now().isoformat()
    })


@socketio.on('request_status_update')
def handle_status_request():
    try:
        status = bot_manager.get_all_bots_status()
        emit('status_update', status)
    except Exception as e:
        emit('error', {'message': f'Ошибка получения статуса: {e}'})


@socketio.on('request_system_info')
def handle_system_info_request():
    try:
        system_info = bot_manager.get_system_info()
        emit('system_info', system_info)
    except Exception as e:
        emit('error', {'message': f'Ошибка получения информации о системе: {e}'})


# Периодическая очистка
def periodic_cleanup():
    """Периодическая очистка неактивных сессий"""

    def cleanup_worker():
        while True:
            try:
                time.sleep(300)  # Каждые 5 минут
                bot_manager.cleanup_inactive_sessions()
                bot_manager.session_manager.cleanup_stale_locks()
            except Exception as e:
                logger.error(f"Ошибка периодической очистки: {e}")

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True, name="SessionCleanup")
    cleanup_thread.start()


# Создание папок
Path("templates").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)
Path("sessions").mkdir(exist_ok=True)
Path("sessions/locks").mkdir(exist_ok=True)

start_time = time.time()

if __name__ == '__main__':
    print("🚀 Запуск КРОССПЛАТФОРМЕННОЙ Instagram Bot Management System")
    print("=" * 70)
    print("🔧 КЛЮЧЕВЫЕ ОСОБЕННОСТИ:")
    print("   ✅ Кроссплатформенный контроль сессий (без fcntl)")
    print("   ✅ Защита от конфликтов между ботами")
    print("   ✅ Автоматическое освобождение заблокированных сессий")
    print("   ✅ Совместимость с Windows и Linux")
    print("   ✅ Готовность к развертыванию на VPS")

    if PROXY_SUPPORT:
        print("   🌐 Поддержка HTTP/HTTPS/SOCKS4/SOCKS5 прокси")
        print("   🔍 Тестирование прокси через веб-интерфейс")
    else:
        print("   ⚠️ Поддержка прокси недоступна (добавьте в launcher.py)")

    print()
    print(f"🖥️ Платформа: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print(f"📂 Рабочая директория: {os.getcwd()}")
    print()
    print("🌐 Веб-интерфейс: http://localhost:5000")
    print("📊 Управление ботами через браузер")
    print("🔄 Автоматическое обновление статуса")
    print("🔒 Контроль сессий в реальном времени")

    if PROXY_SUPPORT:
        print("🌐 Настройка прокси для каждого бота")

    print()

    # Запуск периодической очистки
    periodic_cleanup()

    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n🛑 Получена команда остановки")
        print("🧹 Корректное завершение работы...")

        # Останавливаем всех ботов
        bot_manager.stop_all_bots()

        print("✅ Система остановлена корректно")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        # Аварийная остановка всех ботов
        bot_manager.stop_all_bots()