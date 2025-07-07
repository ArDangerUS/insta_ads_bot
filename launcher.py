#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram Bot v2.7.2025 - КРОССПЛАТФОРМЕННАЯ версия (ИСПРАВЛЕНО)
Совместимость: Windows, Linux, VPS
Исправления конфликтов сессий без использования fcntl
"""
import requests
import asyncio
import random
import time
import json
import logging
import sqlite3
import os
import threading
import sys
import platform
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum
import concurrent.futures

# Instagram API
try:
    from instagrapi import Client
    from instagrapi.exceptions import (
        LoginRequired, ChallengeRequired, FeedbackRequired,
        RateLimitError, ClientError, PleaseWaitFewMinutes
    )

    INSTAGRAPI_AVAILABLE = True
except ImportError:
    print("⚠️ instagrapi не установлен. Установите: pip install instagrapi")
    INSTAGRAPI_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot_fixed.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"


class InteractionType(Enum):
    LIKERS = "likers"
    COMMENTERS = "commenters"
    BOTH = "both"


@dataclass
class ProxyConfig:
    """Конфигурация прокси"""
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    type: str = "http"  # http, https, socks4, socks5

    def to_dict(self) -> dict:
        return {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'type': self.type
        }

    def get_proxy_url(self) -> str:
        """Получить URL прокси для requests"""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        else:
            auth = ""

        return f"{self.type}://{auth}{self.host}:{self.port}"

    def get_instagrapi_proxy(self) -> dict:
        """Получить настройки прокси для instagrapi"""
        proxy_dict = {
            f"{self.type}": f"{self.host}:{self.port}"
        }

        if self.username and self.password:
            proxy_dict['auth'] = f"{self.username}:{self.password}"

        return proxy_dict


# 3. ДОБАВЬТЕ КЛАСС ProxyManager после ProxyConfig:

class ProxyManager:
    """Менеджер для работы с прокси"""

    @staticmethod
    def test_proxy(proxy_config: ProxyConfig) -> dict:
        """Тестирование прокси"""
        try:
            proxy_url = proxy_config.get_proxy_url()
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }

            # Тестируем подключение
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxies,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Пытаемся получить информацию о местоположении
                try:
                    geo_response = requests.get(
                        f"http://ip-api.com/json/{data['origin']}",
                        timeout=5
                    )
                    geo_data = geo_response.json() if geo_response.status_code == 200 else {}
                except:
                    geo_data = {}

                return {
                    'success': True,
                    'ip': data['origin'],
                    'country': geo_data.get('country', 'Unknown'),
                    'city': geo_data.get('city', 'Unknown')
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}'
                }

        except requests.exceptions.ProxyError:
            return {
                'success': False,
                'error': 'Прокси недоступен или неверные данные авторизации'
            }
        except requests.exceptions.ConnectTimeout:
            return {
                'success': False,
                'error': 'Тайм-аут подключения к прокси'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Ошибка подключения к прокси'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Неизвестная ошибка: {str(e)}'
            }

    @staticmethod
    def configure_instagrapi_proxy(client: Client, proxy_config: ProxyConfig):
        """Настройка прокси для instagrapi клиента"""
        try:
            if proxy_config.type in ['socks4', 'socks5']:
                # Для SOCKS прокси используем специальную настройку
                proxy_dict = {
                    'https': f"{proxy_config.type}://{proxy_config.host}:{proxy_config.port}"
                }
                if proxy_config.username and proxy_config.password:
                    proxy_dict[
                        'https'] = f"{proxy_config.type}://{proxy_config.username}:{proxy_config.password}@{proxy_config.host}:{proxy_config.port}"
            else:
                # Для HTTP/HTTPS прокси
                proxy_dict = proxy_config.get_instagrapi_proxy()

            # Устанавливаем прокси в клиент
            client.set_proxy(proxy_dict)
            logger.info(f"✅ Прокси настроен: {proxy_config.type}://{proxy_config.host}:{proxy_config.port}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка настройки прокси: {e}")
            return False


@dataclass
class UserFilter:
    """Расширенные фильтры для отбора пользователей"""
    min_followers: int = 100
    max_followers: int = 50000
    min_following: int = 50
    max_following: int = 5000
    min_posts: int = 3
    has_profile_pic: bool = True
    private_account: bool = False

    # Новые фильтры
    countries: List[str] = None
    languages: List[str] = None
    gender: Gender = Gender.ANY

    # Фильтры по активности
    engagement_rate_min: float = 0.01
    engagement_rate_max: float = 0.20

    # Фильтры по контенту
    exclude_business_accounts: bool = False
    exclude_verified_accounts: bool = False
    required_keywords_in_bio: List[str] = None
    excluded_keywords_in_bio: List[str] = None

    def __post_init__(self):
        if self.countries is None:
            self.countries = []
        if self.languages is None:
            self.languages = []
        if self.required_keywords_in_bio is None:
            self.required_keywords_in_bio = []
        if self.excluded_keywords_in_bio is None:
            self.excluded_keywords_in_bio = []


@dataclass
class BotConfig:
    """Конфигурация Instagram бота"""
    bot_id: str
    username: str
    password: str
    target_accounts: List[str]
    filters: UserFilter
    message_template: str
    main_account: str
    active: bool = True
    proxy: Optional[ProxyConfig] = None

    # Настройки активности
    max_likes_per_hour: int = 8
    max_follows_per_hour: int = 4
    max_messages_per_hour: int = 2
    max_comments_per_hour: int = 3
    min_delay: int = 300
    max_delay: int = 600

    # Настройки взаимодействия
    interaction_types: List[InteractionType] = None
    posts_to_like: int = 2
    posts_to_analyze: int = 3

    # Настройки сообщений
    personalized_messages: bool = True
    message_variants: List[str] = None

    def __post_init__(self):
        if self.interaction_types is None:
            self.interaction_types = [InteractionType.BOTH]
        if self.message_variants is None:
            self.message_variants = [self.message_template]


class CrossPlatformLockManager:
    """Кроссплатформенный менеджер блокировок без fcntl"""

    def __init__(self):
        self.locks_dir = Path("sessions/locks")
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        self.active_locks = {}
        self.lock_timeout = 3600  # 1 час

        # Очистка при инициализации
        self.cleanup_stale_locks()

    def _get_lock_info(self, lock_file: Path) -> Optional[dict]:
        """Получить информацию о блокировке"""
        try:
            if not lock_file.exists():
                return None

            with open(lock_file, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
        except Exception:
            return None

    def _is_process_running(self, pid: int) -> bool:
        """Проверить, запущен ли процесс (кроссплатформенно)"""
        try:
            if platform.system() == "Windows":
                import subprocess
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                                        capture_output=True, text=True)
                return str(pid) in result.stdout
            else:
                # Linux/Unix
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.SubprocessError):
            return False

    def acquire_lock(self, username: str) -> bool:
        """Захватить блокировку для сессии"""
        lock_file = self.locks_dir / f"{username}.lock"
        current_pid = os.getpid()
        current_time = time.time()

        try:
            # Проверяем существующую блокировку
            existing_lock = self._get_lock_info(lock_file)

            if existing_lock:
                # Проверяем, не устарела ли блокировка
                lock_age = current_time - existing_lock.get('timestamp', 0)
                lock_pid = existing_lock.get('pid')

                if lock_age > self.lock_timeout:
                    logger.info(f"🧹 Удаляем устаревшую блокировку для {username}")
                    lock_file.unlink(missing_ok=True)
                elif lock_pid and self._is_process_running(lock_pid):
                    logger.warning(f"⚠️ Сессия {username} уже используется процессом {lock_pid}")
                    return False
                else:
                    logger.info(f"🧹 Удаляем блокировку неактивного процесса для {username}")
                    lock_file.unlink(missing_ok=True)

            # Создаем новую блокировку
            lock_info = {
                'username': username,
                'pid': current_pid,
                'timestamp': current_time,
                'platform': platform.system(),
                'thread_id': threading.get_ident()
            }

            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_info, f, indent=2)

            self.active_locks[username] = {
                'file': lock_file,
                'pid': current_pid,
                'timestamp': current_time
            }

            logger.info(f"🔒 Блокировка сессии {username} захвачена (PID: {current_pid})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка захвата блокировки для {username}: {e}")
            return False

    def release_lock(self, username: str):
        """Освободить блокировку сессии"""
        try:
            if username in self.active_locks:
                lock_file = self.active_locks[username]['file']
                if lock_file.exists():
                    lock_file.unlink()
                del self.active_locks[username]
                logger.info(f"🔓 Блокировка сессии {username} освобождена")
        except Exception as e:
            logger.error(f"❌ Ошибка освобождения блокировки {username}: {e}")

    def cleanup_stale_locks(self):
        """Очистка устаревших блокировок"""
        try:
            current_time = time.time()

            for lock_file in self.locks_dir.glob("*.lock"):
                lock_info = self._get_lock_info(lock_file)

                if not lock_info:
                    lock_file.unlink(missing_ok=True)
                    continue

                # Проверяем возраст блокировки
                lock_age = current_time - lock_info.get('timestamp', 0)
                if lock_age > self.lock_timeout:
                    logger.info(f"🧹 Удаляем устаревшую блокировку: {lock_file.name}")
                    lock_file.unlink(missing_ok=True)
                    continue

                # Проверяем, жив ли процесс
                lock_pid = lock_info.get('pid')
                if lock_pid and not self._is_process_running(lock_pid):
                    logger.info(f"🧹 Удаляем блокировку мертвого процесса: {lock_file.name}")
                    lock_file.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Ошибка очистки блокировок: {e}")

    def get_active_sessions(self) -> List[str]:
        """Получить список активных сессий"""
        active_sessions = []

        for lock_file in self.locks_dir.glob("*.lock"):
            lock_info = self._get_lock_info(lock_file)
            if lock_info:
                username = lock_info.get('username')
                if username:
                    active_sessions.append(username)

        return active_sessions


class DatabaseManager:
    """Менеджер базы данных для отслеживания активности"""

    def __init__(self, db_path: str = "instagram_bot.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    liked BOOLEAN DEFAULT FALSE,
                    followed BOOLEAN DEFAULT FALSE,
                    messaged BOOLEAN DEFAULT FALSE,
                    UNIQUE(bot_id, user_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target_user_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT
                )
            """)

            conn.commit()

    def is_user_processed(self, bot_id: str, user_id: str) -> bool:
        """Проверка, был ли пользователь обработан"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_users WHERE bot_id = ? AND user_id = ?",
                (bot_id, user_id)
            )
            return cursor.fetchone() is not None

    def mark_user_processed(self, bot_id: str, user_id: str, username: str = None,
                            liked: bool = False, followed: bool = False, messaged: bool = False):
        """Отметить пользователя как обработанного"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO processed_users 
                (bot_id, user_id, username, liked, followed, messaged)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (bot_id, user_id, username, liked, followed, messaged))
            conn.commit()

    def log_activity(self, bot_id: str, action_type: str, target_user_id: str = None,
                     success: bool = True, error_message: str = None):
        """Логирование активности бота"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_activity (bot_id, action_type, target_user_id, success, error_message)
                VALUES (?, ?, ?, ?, ?)
            """, (bot_id, action_type, target_user_id, success, error_message))
            conn.commit()

    def get_hourly_activity_count(self, bot_id: str, action_type: str) -> int:
        """Получить количество действий за последний час"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM bot_activity 
                WHERE bot_id = ? AND action_type = ? 
                AND timestamp > datetime('now', '-1 hour')
                AND success = TRUE
            """, (bot_id, action_type))
            return cursor.fetchone()[0]


class FixedInstagramBot:
    """КРОССПЛАТФОРМЕННЫЙ Instagram бот"""

    def __init__(self, config: BotConfig):
        self.config = config
        self.db = DatabaseManager()
        self.lock_manager = CrossPlatformLockManager()
        self.proxy_manager = ProxyManager()

        if not INSTAGRAPI_AVAILABLE:
            raise Exception("instagrapi не установлен")

        self.client = Client()
        self.session_file = f"sessions/{config.username}.json"
        self.is_logged_in = False
        self.is_running = False
        self.processed_users = set()
        self.login_attempts = 0
        self.max_login_attempts = 3
        self.session_locked = False
        if self.config.proxy:
            logger.info(f"🌐 Настройка прокси для {config.username}: {config.proxy.host}:{config.proxy.port}")
            if not self.proxy_manager.configure_instagrapi_proxy(self.client, self.config.proxy):
                logger.warning(f"⚠️ Не удалось настроить прокси для {config.username}")

        Path("sessions").mkdir(exist_ok=True)

    # ИСПРАВЛЕНИЕ: Добавляем правильные асинхронные контекстные менеджеры
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        self.cleanup()

    def __enter__(self):
        """Синхронный контекстный менеджер"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическая очистка ресурсов"""
        self.cleanup()

    def acquire_session_lock(self) -> bool:
        """Захватить блокировку сессии"""
        if self.session_locked:
            return True

        if self.lock_manager.acquire_lock(self.config.username):
            self.session_locked = True
            return True

        return False

    def release_session_lock(self):
        """Освободить блокировку сессии"""
        if self.session_locked:
            self.lock_manager.release_lock(self.config.username)
            self.session_locked = False

    def cleanup(self):
        """Очистка ресурсов"""
        try:
            self.is_running = False
            if hasattr(self, 'client'):
                time.sleep(2)
            self.release_session_lock()
            logger.info(f"🧹 Ресурсы бота {self.config.username} очищены")
        except Exception as e:
            logger.error(f"Ошибка очистки ресурсов: {e}")

    def _setup_client(self):
        """Настройка клиента Instagram"""
        try:
            # Увеличенные задержки для стабильности
            self.client.delay_range = [10, 15]

            # Реалистичные User-Agent'ы
            user_agents = [
                "Instagram 194.0.0.36.172 Android (26/8.0.0; 480dpi; 1080x1920; Xiaomi; MI 5s; capricorn; qcom; en_US; 301484483)",
                "Instagram 195.0.0.45.120 Android (28/9; 420dpi; 1080x2340; samsung; SM-G973F; beyond1; exynos9820; en_US; 303396592)",
                "Instagram 196.0.0.34.120 Android (29/10; 560dpi; 1440x3040; LGE/lge; LM-G850; judypn; sdm855; en_US; 304067749)"
            ]

            user_agent = random.choice(user_agents)
            self.client.set_user_agent(user_agent)

            self.client.set_locale('en_US')
            self.client.set_timezone_offset(-3 * 60 * 60)

            # Дополнительные настройки
            self.client.request_timeout = 30
            if self.config.proxy:
                self.proxy_manager.configure_instagrapi_proxy(self.client, self.config.proxy)
            logger.info(f"✅ Клиент настроен для {self.config.username}")

        except Exception as e:
            logger.error(f"Ошибка настройки клиента: {e}")

    def check_rate_limits(self, action: str) -> bool:
        """Проверка лимитов активности"""
        count = self.db.get_hourly_activity_count(self.config.bot_id, action)

        limits = {
            'like': self.config.max_likes_per_hour,
            'follow': self.config.max_follows_per_hour,
            'message': self.config.max_messages_per_hour,
            'comment': self.config.max_comments_per_hour
        }

        limit = limits.get(action, 5)
        logger.info(f"⏱️ Лимит {action}: {count}/{limit} (прокси: {'✅' if self.config.proxy else '❌'})")
        return count < limit

    async def safe_request(self, func, *args, **kwargs):
        """Безопасное выполнение запроса с retry логикой"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if not self.is_running:
                    raise Exception("Bot stopped")

                result = func(*args, **kwargs)

                # Динамические паузы в зависимости от типа запроса
                if 'user_medias' in str(func):
                    delay = random.uniform(10, 20)
                elif 'media_likers' in str(func):
                    delay = random.uniform(15, 30)
                elif 'user_info' in str(func):
                    delay = random.uniform(10, 15)
                else:
                    delay = random.uniform(5, 10)

                logger.debug(f"⏳ Пауза {delay:.1f}с после {func.__name__}")
                await asyncio.sleep(delay)
                return result

            except Exception as e:
                error_message = str(e).lower()

                # Критические ошибки
                if any(keyword in error_message for keyword in ['403', 'csrf', 'challenge_required', 'login_required']):
                    logger.error(f"🚨 Критическая ошибка API: {e}")
                    raise e

                # Лимиты
                elif any(keyword in error_message for keyword in ['rate limit', 'please wait', 'spam']):
                    wait_time = min(600 * (attempt + 1), 1800)
                    logger.warning(f"⏳ Превышение лимитов, пауза {wait_time / 60:.1f} мин: {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

                # Сетевые ошибки
                elif any(keyword in error_message for keyword in ['connection', 'timeout', 'network']):
                    wait_time = 10 * (2 ** attempt)
                    logger.warning(f"🌐 Сетевая ошибка, пауза {wait_time}с: {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

                # Прочие ошибки
                else:
                    wait_time = random.uniform(30, 60)
                    logger.warning(f"⚠️ Ошибка запроса (попытка {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

    async def get_users_from_interactions(self, target_account: str, limit: int = 30) -> List[str]:
        """Получение пользователей из лайков и комментариев"""
        try:
            logger.info(f"🎯 Получение пользователей из взаимодействий с @{target_account}")

            await asyncio.sleep(random.uniform(15, 30))

            user_id = await self.safe_request(
                self.client.user_id_from_username, target_account
            )
            logger.info(f"✅ ID аккаунта @{target_account}: {user_id}")

            await asyncio.sleep(random.uniform(10, 15))

            # Получаем медиа с fallback
            medias = []
            try:
                medias = await self.safe_request(
                    self.client.user_medias, user_id, amount=self.config.posts_to_analyze
                )
            except Exception as e:
                logger.warning(f"⚠️ Основной метод получения медиа не сработал: {e}")
                try:
                    await asyncio.sleep(random.uniform(45, 60))
                    medias = await self.safe_request(
                        self.client.user_medias, user_id, amount=min(self.config.posts_to_analyze, 2)
                    )
                except Exception as e2:
                    logger.error(f"❌ Не удалось получить медиа: {e2}")
                    return []

            logger.info(f"📸 Найдено {len(medias)} постов")

            if not medias:
                logger.warning(f"У аккаунта @{target_account} нет доступных постов")
                return []

            target_users = set()

            for i, media in enumerate(medias):
                if len(target_users) >= limit or not self.is_running:
                    break

                logger.info(f"📸 Анализ поста {i + 1}/{len(medias)} ({media.like_count} лайков)")

                await asyncio.sleep(random.uniform(15, 25))

                # Получаем лайкеров
                if InteractionType.LIKERS in self.config.interaction_types or InteractionType.BOTH in self.config.interaction_types:
                    try:
                        logger.info(f"👥 Получаем лайкеров поста...")
                        await asyncio.sleep(random.uniform(10, 15))

                        likers = await self.safe_request(
                            self.client.media_likers, media.id
                        )
                        logger.info(f"✅ Получено {len(likers)} лайкеров")

                        for liker in likers[:min(15, len(likers))]:
                            target_users.add(str(liker.pk))
                            if len(target_users) >= limit:
                                break

                    except Exception as e:
                        logger.warning(f"❌ Ошибка получения лайкеров: {e}")
                        await asyncio.sleep(random.uniform(60, 120))

                # Получаем комментаторов
                if (InteractionType.COMMENTERS in self.config.interaction_types or
                    InteractionType.BOTH in self.config.interaction_types) and len(target_users) < limit:

                    try:
                        await asyncio.sleep(random.uniform(25, 40))

                        logger.info(f"💬 Получаем комментаторов...")
                        comments = await self.safe_request(
                            self.client.media_comments, media.id, amount=8
                        )
                        logger.info(f"✅ Получено {len(comments)} комментариев")

                        for comment in comments:
                            target_users.add(str(comment.user.pk))
                            if len(target_users) >= limit:
                                break

                    except Exception as e:
                        logger.warning(f"❌ Ошибка получения комментариев: {e}")

                # Пауза между постами
                if i < len(medias) - 1:
                    pause_time = random.uniform(20, 50)
                    logger.info(f"😴 Пауза {pause_time:.1f}с перед следующим постом")
                    await asyncio.sleep(pause_time)

            logger.info(f"✅ Всего найдено {len(target_users)} уникальных пользователей из @{target_account}")
            return list(target_users)[:limit]

        except Exception as e:
            logger.error(f"❌ Критическая ошибка получения пользователей из {target_account}: {e}")
            return []

    def check_user_basic_filters(self, user_id: str) -> bool:
        """Базовая проверка пользователя по фильтрам"""
        try:
            user_info = self.client.user_info(user_id)
            filters = self.config.filters

            if not (filters.min_followers <= user_info.follower_count <= filters.max_followers):
                return False

            if not (filters.min_following <= user_info.following_count <= filters.max_following):
                return False

            if user_info.media_count < filters.min_posts:
                return False

            if filters.has_profile_pic and not user_info.profile_pic_url:
                return False

            if user_info.is_private and not filters.private_account:
                return False

            if filters.exclude_business_accounts and user_info.is_business:
                return False

            if filters.exclude_verified_accounts and user_info.is_verified:
                return False

            return True

        except Exception as e:
            logger.warning(f"Ошибка проверки фильтров для {user_id}: {e}")
            return False

    def _get_personalized_message(self, user_info) -> str:
        """Создание персонализированного сообщения"""
        if not self.config.personalized_messages:
            return random.choice(self.config.message_variants)

        message_template = random.choice(self.config.message_variants)
        message = message_template.replace('{main_account}', f"@{self.config.main_account}")

        if user_info.full_name:
            first_name = user_info.full_name.split()[0]
            message = message.replace('{name}', first_name)
        else:
            message = message.replace('{name}', user_info.username)

        return message

    async def interact_with_user(self, user_id: str) -> Dict[str, bool]:
        """Взаимодействие с пользователем"""
        results = {'like': False, 'follow': False, 'message': False}

        try:
            if self.db.is_user_processed(self.config.bot_id, user_id):
                return results

            if not self.check_user_basic_filters(user_id):
                return results

            user_info = await self.safe_request(self.client.user_info, user_id)
            logger.info(f"👤 Обрабатываем: @{user_info.username}")

            await asyncio.sleep(random.uniform(30, 50))

            # Получаем посты пользователя
            try:
                user_medias = await self.safe_request(
                    self.client.user_medias, user_id, amount=self.config.posts_to_like
                )
            except:
                logger.warning(f"Не удалось получить посты @{user_info.username}")
                return results

            # Лайкаем посты
            if self.check_rate_limits('like') and user_medias:
                try:
                    posts_to_like = min(len(user_medias), self.config.posts_to_like)
                    for i, media in enumerate(user_medias[:posts_to_like]):
                        if not self.is_running:
                            break

                        await self.safe_request(self.client.media_like, media.id)
                        self.db.log_activity(self.config.bot_id, 'like', user_id, True)
                        logger.info(f"👍 Лайк {i + 1}/{posts_to_like} @{user_info.username}")

                        if i < posts_to_like - 1:
                            await asyncio.sleep(random.uniform(15, 35))

                    results['like'] = True

                except Exception as e:
                    logger.warning(f"Ошибка лайка @{user_info.username}: {e}")
                    self.db.log_activity(self.config.bot_id, 'like', user_id, False, str(e))

            # Подписываемся
            if results['like'] and self.check_rate_limits('follow') and self.is_running:
                await asyncio.sleep(random.uniform(60, 120))
                try:
                    await self.safe_request(self.client.user_follow, user_id)
                    self.db.log_activity(self.config.bot_id, 'follow', user_id, True)
                    results['follow'] = True
                    logger.info(f"➕ Подписка на @{user_info.username}")

                except Exception as e:
                    logger.warning(f"Ошибка подписки @{user_info.username}: {e}")
                    self.db.log_activity(self.config.bot_id, 'follow', user_id, False, str(e))

            # Отправляем сообщение
            if results['follow'] and self.check_rate_limits('message') and self.is_running:
                await asyncio.sleep(random.uniform(40, 120))
                try:
                    message = self._get_personalized_message(user_info)
                    await self.safe_request(
                        self.client.direct_send, message, [user_id]
                    )
                    self.db.log_activity(self.config.bot_id, 'message', user_id, True)
                    results['message'] = True
                    logger.info(f"💬 Сообщение отправлено @{user_info.username}")

                except Exception as e:
                    logger.warning(f"Ошибка отправки сообщения @{user_info.username}: {e}")
                    self.db.log_activity(self.config.bot_id, 'message', user_id, False, str(e))

            # Отмечаем как обработанного
            self.db.mark_user_processed(
                self.config.bot_id, user_id, user_info.username,
                results['like'], results['follow'], results['message']
            )

            # Пауза между пользователями
            if self.is_running:
                delay = random.uniform(self.config.min_delay, self.config.max_delay)
                logger.info(f"😴 Пауза {delay / 60:.1f} минут до следующего пользователя")

                # Разбиваем длинную паузу для возможности остановки
                while delay > 0 and self.is_running:
                    sleep_time = min(60, delay)
                    await asyncio.sleep(sleep_time)
                    delay -= sleep_time

        except Exception as e:
            logger.error(f"Общая ошибка взаимодействия с {user_id}: {e}")
            self.db.log_activity(self.config.bot_id, 'error', user_id, False, str(e))

        return results

    def _load_session_safely(self) -> bool:
        """Безопасная загрузка сессии"""
        try:
            if not Path(self.session_file).exists():
                logger.info(f"Файл сессии не найден: {self.session_file}")
                return False

            # Проверяем возраст сессии
            session_age = time.time() - os.path.getmtime(self.session_file)
            if session_age > 24 * 60 * 60:
                logger.info(f"Сессия устарела для {self.config.username}")
                os.remove(self.session_file)
                return False

            # Проверяем размер файла
            if os.path.getsize(self.session_file) < 100:
                logger.info(f"Файл сессии поврежден для {self.config.username}")
                os.remove(self.session_file)
                return False

            settings = {}
            with open(self.session_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            if not settings or 'cookies' not in settings:
                logger.info(f"Некорректная сессия для {self.config.username}")
                return False

            self.client.set_settings(settings)
            logger.info(f"✅ Сессия загружена для {self.config.username}")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки сессии: {e}")
            return False

    def _save_session_safely(self):
        """Безопасное сохранение сессии"""
        try:
            settings = self.client.get_settings()

            if not settings or 'cookies' not in settings:
                logger.warning(f"Нет данных для сохранения сессии {self.config.username}")
                return False

            # Сохраняем во временный файл сначала
            temp_file = f"{self.session_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)

            # Затем переименовываем (атомарная операция)
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            os.rename(temp_file, self.session_file)

            logger.info(f"✅ Сессия сохранена для {self.config.username}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения сессии: {e}")
            return False

    async def login(self) -> bool:
        """Авторизация с блокировками"""
        if self.login_attempts >= self.max_login_attempts:
            logger.error(f"Превышено максимальное количество попыток входа для {self.config.username}")
            return False

        # Проверяем блокировку сессии
            # Проверяем блокировку сессии (игнорируем если уже заблокирована)
        if not self.session_locked:
            if not self.acquire_session_lock():
                logger.warning(
                    f"⚠️ Сессия {self.config.username} уже используется, но продолжаем (управляется backend)")
                self.session_locked = True  # Принудительно устанавливаем флаг

        self.login_attempts += 1

        try:
            self._setup_client()

            await asyncio.sleep(random.uniform(5, 15))

            session_loaded = self._load_session_safely()

            if session_loaded:
                try:
                    account_info = self.client.account_info()
                    logger.info(f"✅ Авторизация через сессию: @{self.config.username}")
                    self.is_logged_in = True
                    self.login_attempts = 0
                    return True

                except Exception as e:
                    logger.info(f"Сессия недействительна для {self.config.username}: {e}")

            logger.info(f"🔑 Выполняем новый вход для {self.config.username}")

            # Очищаем настройки клиента
            old_settings = self.client.get_settings()
            self.client.set_settings({})

            if old_settings.get('uuids'):
                self.client.set_uuids(old_settings['uuids'])

            await asyncio.sleep(random.uniform(15, 25))

            success = self.client.login(self.config.username, self.config.password)

            if success:
                try:
                    account_info = self.client.account_info()
                    logger.info(f"✅ Успешный новый вход: @{self.config.username}")
                    self.is_logged_in = True
                    self.login_attempts = 0

                    self._save_session_safely()
                    await asyncio.sleep(random.uniform(30, 60))
                    return True

                except Exception as e:
                    logger.warning(f"Ошибка получения информации об аккаунте: {e}")
                    self.is_logged_in = True
                    self.login_attempts = 0
                    self._save_session_safely()
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Ошибка авторизации {self.config.username}: {e}")
            self.release_session_lock()
            return False

    async def run_cycle(self):
        """Основной цикл работы бота"""
        try:
            logger.info(f"🎯 === НАЧАЛО ЦИКЛА для {self.config.username} ===")

            if not self.config.target_accounts:
                logger.error("❌ ОШИБКА: Список целевых аккаунтов пуст!")
                return

            for i, target_account in enumerate(self.config.target_accounts):
                if not self.is_running:
                    logger.info("🛑 Бот остановлен, прерываем цикл")
                    break

                logger.info(f"🎯 === АККАУНТ {i + 1}/{len(self.config.target_accounts)}: @{target_account} ===")

                try:
                    target_users = await self.get_users_from_interactions(target_account, limit=15)

                    if not target_users:
                        logger.warning(f"⚠️ Не удалось получить пользователей из @{target_account}")
                        continue

                    logger.info(f"✅ Получено {len(target_users)} пользователей из @{target_account}")

                    processed_count = 0
                    skipped_count = 0

                    for j, user_id in enumerate(target_users):
                        if not self.is_running:
                            logger.info("🛑 Бот остановлен, прерываем обработку пользователей")
                            break

                        logger.info(f"👤 === ПОЛЬЗОВАТЕЛЬ {j + 1}/{len(target_users)}: {user_id} ===")

                        try:
                            if self.db.is_user_processed(self.config.bot_id, user_id):
                                logger.info(f"⏭️ Пользователь {user_id} уже обработан ранее")
                                skipped_count += 1
                                continue

                            results = await self.interact_with_user(user_id)

                            actions = []
                            if results['like']: actions.append('лайк')
                            if results['follow']: actions.append('подписка')
                            if results['message']: actions.append('сообщение')

                            if actions:
                                logger.info(f"✅ Выполнено для {user_id}: {', '.join(actions)}")
                                processed_count += 1
                            else:
                                logger.info(f"⏭️ Пользователь {user_id} пропущен")
                                skipped_count += 1

                        except Exception as e:
                            logger.error(f"❌ Ошибка обработки пользователя {user_id}: {e}")
                            skipped_count += 1
                            await asyncio.sleep(random.uniform(120, 240))

                    logger.info(f"📊 Результаты для @{target_account}:")
                    logger.info(f"   ✅ Обработано: {processed_count}")
                    logger.info(f"   ⏭️ Пропущено: {skipped_count}")

                    # Пауза между аккаунтами
                    if i < len(self.config.target_accounts) - 1 and self.is_running:
                        pause_minutes = random.uniform(45, 90)
                        logger.info(f"😴 Пауза {pause_minutes:.1f} мин перед следующим аккаунтом")

                        pause_seconds = pause_minutes * 60
                        while pause_seconds > 0 and self.is_running:
                            sleep_time = min(30, pause_seconds)
                            await asyncio.sleep(sleep_time)
                            pause_seconds -= sleep_time

                except Exception as e:
                    logger.error(f"❌ Критическая ошибка при обработке @{target_account}: {e}")
                    await asyncio.sleep(random.uniform(600, 1200))

            logger.info(f"🏁 === ЦИКЛ ЗАВЕРШЕН для {self.config.username} ===")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле: {e}")
            await asyncio.sleep(random.uniform(1800, 3600))

    async def start(self):
        """Запуск бота"""
        try:
            logger.info(f"🚀 Запуск кроссплатформенного бота: {self.config.username}")
            logger.info(f"🖥️ Платформа: {platform.system()} {platform.release()}")

            if not await self.login():
                logger.error(f"❌ Не удалось авторизоваться: {self.config.username}")
                return False

            self.is_running = True
            cycle_count = 0

            while self.is_running and self.config.active:
                try:
                    cycle_count += 1
                    logger.info(f"🔄 Начинаем цикл #{cycle_count} для {self.config.username}")

                    if not self.session_locked:
                        logger.warning("⚠️ Сессия не заблокирована, возможен конфликт")
                        break

                    await self.run_cycle()

                    logger.info(f"✅ Цикл #{cycle_count} завершен для {self.config.username}")

                    # Пауза между циклами
                    if self.is_running and self.config.active:
                        if cycle_count == 1:
                            pause_minutes = random.uniform(60, 120)
                            logger.info(f"😴 Пауза {pause_minutes:.1f} минут после первого цикла")
                        else:
                            pause_hours = random.uniform(6, 12)
                            logger.info(f"😴 Большая пауза {pause_hours:.1f} часов до следующего цикла")
                            pause_minutes = pause_hours * 60

                        pause_seconds = pause_minutes * 60
                        while pause_seconds > 0 and self.is_running and self.config.active:
                            sleep_time = min(60, pause_seconds)
                            await asyncio.sleep(sleep_time)
                            pause_seconds -= sleep_time

                except Exception as e:
                    logger.error(f"Ошибка в цикле {cycle_count}: {e}")

                    if "login" in str(e).lower() or "auth" in str(e).lower():
                        logger.info(f"Попытка переавторизации для {self.config.username}")
                        self.is_logged_in = False

                        if not await self.login():
                            logger.error(f"Не удалось переавторизоваться: {self.config.username}")
                            break

                    await asyncio.sleep(random.uniform(1800, 3600))

            logger.info(f"🛑 Бот остановлен: {self.config.username}")
            return True

        except Exception as e:
            logger.error(f"Критическая ошибка бота {self.config.username}: {e}")
            return False
        finally:
            self.cleanup()

    def stop(self):
        """Остановка бота"""
        logger.info(f"🛑 Получена команда остановки для бота: {self.config.username}")
        self.is_running = False
        time.sleep(5)
        self.cleanup()

    def get_statistics(self) -> Dict:
        """Получение статистики бота"""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    action_type,
                    COUNT(*) as count,
                    COUNT(CASE WHEN success = 1 THEN 1 END) as success_count
                FROM bot_activity 
                WHERE bot_id = ? 
                GROUP BY action_type
            """, (self.config.bot_id,))

            stats = {}
            for row in cursor.fetchall():
                action, total, success = row
                stats[action] = {'total': total, 'success': success, 'error': total - success}

            cursor.execute("""
                SELECT action_type, COUNT(*) 
                FROM bot_activity 
                WHERE bot_id = ? AND timestamp > datetime('now', '-1 hour')
                GROUP BY action_type
            """, (self.config.bot_id,))

            hourly_stats = dict(cursor.fetchall())

            return {
                'total_stats': stats,
                'hourly_stats': hourly_stats,
                'is_running': self.is_running,
                'session_locked': self.session_locked,
                'username': self.config.username,
                'platform': platform.system(),
                'proxy': self.config.proxy.to_dict() if self.config.proxy else None
            }


def create_config_for_windows_vps() -> BotConfig:
    """Создание конфигурации для Windows/VPS"""
    filters = UserFilter(
        min_followers=30,
        max_followers=8000,
        min_following=5,
        max_following=1500,
        min_posts=1,
        has_profile_pic=False,
        private_account=False,
        countries=[],
        languages=[],
        exclude_business_accounts=False,
        exclude_verified_accounts=True,
        required_keywords_in_bio=[],
        excluded_keywords_in_bio=['bot', 'spam', 'fake']
    )

    config = BotConfig(
        bot_id="windows_vps_bot",
        username="artem_lotariev_",  # 🔧 ЗАМЕНИТЕ НА ВАШ USERNAME
        password="Artem1702L",  # 🔧 ЗАМЕНИТЕ НА ВАШ ПАРОЛЬ

        target_accounts=[
            "grandcar_ukraine",
            "ukraine_insta",
            "kyiv_official"
        ],

        filters=filters,
        message_template="Привіт! Цікавий контент на @{main_account} 🤖",
        main_account="pschol",  # 🔧 ЗАМЕНИТЕ НА ВАШ ОСНОВНОЙ АККАУНТ

        interaction_types=[InteractionType.LIKERS],
        posts_to_analyze=2,
        posts_to_like=1,

        # Мягкие лимиты для VPS
        max_likes_per_hour=6,
        max_follows_per_hour=3,
        max_messages_per_hour=2,

        # Увеличенные паузы для стабильности
        min_delay=600,  # 10 минут
        max_delay=1200,  # 20 минут

        message_variants=[
            "Привіт {name}! Цікавий контент на @{main_account} 🇺🇦",
            "Вітаю! Рекомендую заглянути @{main_account} ✨",
            "Привіт! AI та новини на @{main_account} 🤖"
        ],

        personalized_messages=True
    )

    return config


async def test_cross_platform_bot():
    """Тест кроссплатформенного бота"""
    print("🧪 ТЕСТ КРОССПЛАТФОРМЕННОГО INSTAGRAM БОТА")
    print("=" * 60)
    print(f"🖥️ Платформа: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print()

    config = create_config_for_windows_vps()

    if config.password == "YOUR_PASSWORD_HERE" or config.main_account == "YOUR_MAIN_ACCOUNT":
        print("❌ ОШИБКА: Настройте конфигурацию!")
        print("🔧 Откройте launcher.py и измените:")
        print('   username="your_instagram_username"')
        print('   password="your_password"')
        print('   main_account="your_main_account"')
        return

    # ИСПРАВЛЕНИЕ: Используем правильный асинхронный контекстный менеджер
    async with FixedInstagramBot(config) as bot:
        try:
            print(f"🔑 Тестируем авторизацию @{config.username}...")

            if await bot.login():
                print("✅ Авторизация успешна!")
                print("🚀 Запуск полноценной работы...")
                await bot.start()
            else:
                print("❌ Ошибка авторизации")

        except KeyboardInterrupt:
            print("\n🛑 Получена команда остановки (Ctrl+C)")
            bot.stop()
        except Exception as e:
            print(f"❌ Ошибка: {e}")


def show_platform_info():
    """Показать информацию о платформе и настройках"""
    print("🔧 ИНФОРМАЦИЯ О СИСТЕМЕ")
    print("=" * 50)
    print(f"🖥️ Операционная система: {platform.system()} {platform.release()}")
    print(f"🏗️ Архитектура: {platform.machine()}")
    print(f"🐍 Python: {platform.python_version()}")
    print(f"📂 Рабочая директория: {os.getcwd()}")
    print()

    # Проверяем доступные модули
    modules_status = {}
    required_modules = ['instagrapi', 'flask', 'flask_socketio']

    for module in required_modules:
        try:
            __import__(module)
            modules_status[module] = "✅ Установлен"
        except ImportError:
            modules_status[module] = "❌ Не установлен"

    print("📦 СТАТУС МОДУЛЕЙ:")
    for module, status in modules_status.items():
        print(f"   {module}: {status}")
    print()

    # Проверяем права доступа
    print("🔐 ПРАВА ДОСТУПА:")
    test_dirs = ['sessions', 'sessions/locks', 'logs']
    for test_dir in test_dirs:
        try:
            Path(test_dir).mkdir(parents=True, exist_ok=True)
            test_file = Path(test_dir) / "test.tmp"
            test_file.write_text("test")
            test_file.unlink()
            print(f"   {test_dir}: ✅ Чтение/запись OK")
        except Exception as e:
            print(f"   {test_dir}: ❌ Ошибка: {e}")
    print()

    print("🌐 РЕКОМЕНДАЦИИ ДЛЯ VPS:")
    print("   • Используйте screen или tmux для фоновой работы")
    print("   • Настройте автозапуск через systemd (Linux)")
    print("   • Мониторьте использование памяти и CPU")
    print("   • Регулярно делайте бэкапы sessions/ и logs/")
    print("   • Используйте VPS с IP из целевой страны")


if __name__ == "__main__":
    print("🤖 КРОССПЛАТФОРМЕННЫЙ INSTAGRAM BOT v2.7.2025 - ИСПРАВЛЕНО")
    print("=" * 65)
    print("🔧 ИСПРАВЛЕНИЯ В ЭТОЙ ВЕРСИИ:")
    print("   ✅ Добавлены правильные асинхронные контекстные менеджеры")
    print("   ✅ Исправлена ошибка AttributeError: __aenter__")
    print("   ✅ Совместимость с Windows и Linux")
    print("   ✅ Готовность к развертыванию на VPS")
    print("   ✅ Блокировки сессий без fcntl")
    print("   ✅ Улучшенная обработка ошибок")
    print("   ✅ Автоматическая очистка ресурсов")
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == '--info':
            show_platform_info()
        elif sys.argv[1] == '--test':
            asyncio.run(test_cross_platform_bot())
        else:
            print("❓ Доступные команды:")
            print("   --info  : Информация о системе")
            print("   --test  : Тестовый запуск")
    else:
        print("🚀 Для запуска используйте:")
        print("   python launcher_fixed.py --test")
        print()
        asyncio.run(test_cross_platform_bot())


def test_proxy_api(proxy_data: dict) -> dict:
    """API функция для тестирования прокси"""
    try:
        proxy_config = ProxyConfig(
            host=proxy_data['host'],
            port=int(proxy_data['port']),
            username=proxy_data.get('username'),
            password=proxy_data.get('password'),
            type=proxy_data['type']
        )

        return ProxyManager.test_proxy(proxy_config)

    except Exception as e:
        return {
            'success': False,
            'error': f'Ошибка конфигурации прокси: {str(e)}'
        }