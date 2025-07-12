#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Instagram Bot v3.0.2025 - CZECH OPTIMIZED VERSION
Совместимость: Windows, Linux, VPS
Оптимизировано для чешских устройств с улучшенной рандомизацией
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
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path
from enum import Enum


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
        logging.FileHandler('bot_czech.log', encoding='utf-8'),
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


class HumanActivity(Enum):
    EXPLORE = "explore"
    WATCH_REELS = "watch_reels"
    VIEW_STORIES = "view_stories"
    BROWSE_FEED = "browse_feed"
    SEARCH_HASHTAGS = "search_hashtags"
    VIEW_PROFILES = "view_profiles"


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

    # Настройки активности (более консервативные)
    max_likes_per_hour: int = 4
    max_follows_per_hour: int = 2
    max_messages_per_hour: int = 1
    max_comments_per_hour: int = 2
    min_delay: int = 1200  # 20 минут
    max_delay: int = 2400  # 40 минут

    # Настройки взаимодействия
    interaction_types: List[InteractionType] = None
    posts_to_like: int = 2
    posts_to_analyze: int = 2

    # Настройки сообщений
    personalized_messages: bool = True
    message_variants: List[str] = None

    def __post_init__(self):
        if self.interaction_types is None:
            self.interaction_types = [InteractionType.LIKERS]
        if self.message_variants is None:
            self.message_variants = [self.message_template]


class CzechDeviceManager:
    """Менеджер чешских устройств на основе реальной статистики"""

    @staticmethod
    def get_czech_devices():
        """Популярные устройства в Чехии основанные на реальной статистике"""
        return [
            # Samsung Galaxy S24 серия (лидер рынка 29.05%)
            {
                "model": "SM-S921B",
                "brand": "samsung",
                "name": "Galaxy S24",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1080x2340",
                "dpi": "416",
                "cpu": "arm64-v8a",
                "chipset": "exynos2400",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; SM-S921B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36 Instagram 322.0.0.40.96 Android (34/14; 416dpi; 1080x2340; samsung; SM-S921B; dm1q; exynos2400; cs_CZ; 563315329)"
            },
            {
                "model": "SM-S928B",
                "brand": "samsung",
                "name": "Galaxy S24 Ultra",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1440x3120",
                "dpi": "501",
                "cpu": "arm64-v8a",
                "chipset": "snapdragon8gen3",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; SM-S928B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36 Instagram 322.0.0.40.96 Android (34/14; 501dpi; 1440x3120; samsung; SM-S928B; dm3q; snapdragon8gen3; cs_CZ; 563315329)"
            },
            {
                "model": "SM-A546B",
                "brand": "samsung",
                "name": "Galaxy A54",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1080x2340",
                "dpi": "403",
                "cpu": "arm64-v8a",
                "chipset": "exynos1380",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; SM-A546B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.163 Mobile Safari/537.36 Instagram 318.0.0.37.116 Android (34/14; 403dpi; 1080x2340; samsung; SM-A546B; a54x; exynos1380; cs_CZ; 547348935)"
            },
            {
                "model": "SM-A256B",
                "brand": "samsung",
                "name": "Galaxy A25",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1080x2340",
                "dpi": "396",
                "cpu": "arm64-v8a",
                "chipset": "exynos1280",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; SM-A256B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/118.0.5993.111 Mobile Safari/537.36 Instagram 315.0.0.35.109 Android (34/14; 396dpi; 1080x2340; samsung; SM-A256B; a25x; exynos1280; cs_CZ; 534567234)"
            },

            # Xiaomi серия (второй по популярности 25.49%)
            {
                "model": "2312DRA50G",
                "brand": "Xiaomi",
                "name": "Redmi Note 13",
                "android_version": "13",
                "api_level": "33",
                "resolution": "1080x2400",
                "dpi": "395",
                "cpu": "arm64-v8a",
                "chipset": "dimensity6080",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 13; 2312DRA50G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.67 Mobile Safari/537.36 Instagram 309.0.0.40.113 Android (33/13; 395dpi; 1080x2400; Xiaomi; 2312DRA50G; sapphire; dimensity6080; cs_CZ; 536988435)"
            },
            {
                "model": "2312DRA4AG",
                "brand": "Xiaomi",
                "name": "Redmi Note 13 Pro",
                "android_version": "13",
                "api_level": "33",
                "resolution": "1080x2400",
                "dpi": "395",
                "cpu": "arm64-v8a",
                "chipset": "heliog99ultra",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 13; 2312DRA4AG Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.67 Mobile Safari/537.36 Instagram 309.0.0.40.113 Android (33/13; 395dpi; 1080x2400; Xiaomi; 2312DRA4AG; ruby; heliog99ultra; cs_CZ; 536988435)"
            },
            {
                "model": "23090RA98G",
                "brand": "Xiaomi",
                "name": "Xiaomi 14T",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1220x2712",
                "dpi": "446",
                "cpu": "arm64-v8a",
                "chipset": "dimensity8300ultra",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; 23090RA98G Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36 Instagram 322.0.0.40.96 Android (34/14; 446dpi; 1220x2712; Xiaomi; 23090RA98G; aristotle; dimensity8300ultra; cs_CZ; 563315329)"
            },
            {
                "model": "23013RK75G",
                "brand": "Redmi",
                "name": "Redmi Note 12",
                "android_version": "13",
                "api_level": "33",
                "resolution": "1080x2400",
                "dpi": "395",
                "cpu": "arm64-v8a",
                "chipset": "snapdragon4gen1",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 13; 23013RK75G Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/118.0.5993.111 Mobile Safari/537.36 Instagram 315.0.0.35.109 Android (33/13; 395dpi; 1080x2400; Redmi; 23013RK75G; tapas; snapdragon4gen1; cs_CZ; 534567234)"
            },

            # OnePlus серия (премиум сегмент)
            {
                "model": "CPH2573",
                "brand": "OnePlus",
                "name": "OnePlus 12",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1440x3168",
                "dpi": "510",
                "cpu": "arm64-v8a",
                "chipset": "snapdragon8gen3",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; CPH2573 Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36 Instagram 322.0.0.40.96 Android (34/14; 510dpi; 1440x3168; OnePlus; CPH2573; pineapple; snapdragon8gen3; cs_CZ; 563315329)"
            },
            {
                "model": "CPH2609",
                "brand": "OnePlus",
                "name": "OnePlus Nord 4",
                "android_version": "14",
                "api_level": "34",
                "resolution": "1240x2772",
                "dpi": "451",
                "cpu": "arm64-v8a",
                "chipset": "snapdragon7gen3",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 14; CPH2609 Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/119.0.6045.163 Mobile Safari/537.36 Instagram 318.0.0.37.116 Android (34/14; 451dpi; 1240x2772; OnePlus; CPH2609; aston; snapdragon7gen3; cs_CZ; 547348935)"
            },

            # Realme серия
            {
                "model": "RMX3031",
                "brand": "realme",
                "name": "Realme GT Neo 3",
                "android_version": "13",
                "api_level": "33",
                "resolution": "1080x2412",
                "dpi": "395",
                "cpu": "arm64-v8a",
                "chipset": "dimensity8100",
                "user_agent_template": "Mozilla/5.0 (Linux; Android 13; RMX3031 Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/118.0.5993.111 Mobile Safari/537.36 Instagram 315.0.0.35.109 Android (33/13; 395dpi; 1080x2412; realme; RMX3031; oscar; dimensity8100; cs_CZ; 534567234)"
            }
        ]

    @staticmethod
    def get_random_device():
        """Получить случайное чешское устройство с весами популярности"""
        devices = CzechDeviceManager.get_czech_devices()

        # Веса основанные на реальной статистике рынка
        weights = [
            # Samsung Galaxy (29.05% рынка)
            0.08, 0.06, 0.08, 0.07,  # S24, S24 Ultra, A54, A25
            # Xiaomi/Redmi (25.49% рынка)
            0.08, 0.07, 0.05, 0.055,  # Note 13, Note 13 Pro, 14T, Note 12
            # OnePlus (премиум сегмент ~5%)
            0.025, 0.025,  # OnePlus 12, Nord 4
            # Realme (~3%)
            0.03  # GT Neo 3
        ]

        return random.choices(devices, weights=weights)[0]

    @staticmethod
    def get_instagram_versions():
        """Актуальные версии Instagram 2024-2025"""
        return [
            "322.0.0.40.96",
            "318.0.0.37.116",
            "315.0.0.35.109",
            "309.0.0.40.113",
            "325.0.0.43.87",
            "328.0.0.46.92"
        ]

    @staticmethod
    def get_chrome_versions():
        """Актуальные версии Chrome для WebView"""
        return [
            "120.0.6099.230",
            "119.0.6045.163",
            "118.0.5993.111",
            "121.0.6167.164",
            "122.0.6261.105"
        ]


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


class CzechInstagramBot:
    """CZECH OPTIMIZED Instagram бот с улучшенной рандомизацией"""

    def __init__(self, config: BotConfig):
        self.config = config
        self.db = DatabaseManager()
        self.lock_manager = CrossPlatformLockManager()
        self.proxy_manager = ProxyManager()
        self.device_manager = CzechDeviceManager()

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

        # Выбираем случайное чешское устройство
        self.device = self.device_manager.get_random_device()
        logger.info(
            f"🇨🇿 Выбрано устройство: {self.device['brand']} {self.device['name']} (Android {self.device['android_version']})")

        if self.config.proxy:
            logger.info(f"🌐 Настройка прокси для {config.username}: {config.proxy.host}:{config.proxy.port}")
            if not self.proxy_manager.configure_instagrapi_proxy(self.client, self.config.proxy):
                logger.warning(f"⚠️ Не удалось настроить прокси для {config.username}")

        Path("sessions").mkdir(exist_ok=True)

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
        """Настройка клиента с чешскими устройствами"""
        try:
            # МАКСИМАЛЬНЫЕ задержки для избежания банов
            self.client.delay_range = [45, 90]  # Увеличено с [30, 60]

            # Установка чешского User-Agent на основе выбранного устройства
            instagram_version = random.choice(self.device_manager.get_instagram_versions())
            chrome_version = random.choice(self.device_manager.get_chrome_versions())

            # Создаем реалистичный User-Agent для выбранного устройства
            user_agent = self.device['user_agent_template'].replace(
                "322.0.0.40.96", instagram_version
            ).replace(
                "120.0.6099.230", chrome_version
            )

            self.client.set_user_agent(user_agent)
            logger.info(f"🤖 User-Agent: {self.device['brand']} {self.device['name']} (IG: {instagram_version})")

            # Чешские настройки локализации
            self.client.set_locale('cs_CZ')
            self.client.set_timezone_offset(1 * 60 * 60)  # UTC+1 для Чехии (зимнее время)

            # Дополнительные настройки
            self.client.request_timeout = 45  # Увеличен таймаут

            if self.config.proxy:
                self.proxy_manager.configure_instagrapi_proxy(self.client, self.config.proxy)

            logger.info(f"✅ Чешский клиент настроен для {self.config.username}")

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
        logger.info(f"⏱️ Лимит {action}: {count}/{limit} (устройство: {self.device['name']})")
        return count < limit

    async def safe_request(self, func, *args, **kwargs):
        """Безопасное выполнение запроса с увеличенными паузами"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if not self.is_running:
                    raise Exception("Bot stopped")

                result = func(*args, **kwargs)

                # ЗНАЧИТЕЛЬНО увеличенные динамические паузы
                if 'user_medias' in str(func):
                    delay = random.uniform(60, 120)  # Было 45-90
                elif 'media_likers' in str(func):
                    delay = random.uniform(90, 180)  # Было 60-120
                elif 'user_info' in str(func):
                    delay = random.uniform(45, 90)  # Было 30-60
                elif 'media_like' in str(func):
                    delay = random.uniform(60, 120)  # Новое - для лайков
                elif 'user_follow' in str(func):
                    delay = random.uniform(90, 180)  # Новое - для подписок
                elif 'direct_send' in str(func):
                    delay = random.uniform(120, 240)  # Новое - для сообщений
                elif 'explore_medias' in str(func):
                    delay = random.uniform(30, 60)  # Для explore
                elif 'clips_explore' in str(func):
                    delay = random.uniform(25, 50)  # Для reels
                else:
                    delay = random.uniform(30, 60)  # Было 20-40

                logger.debug(f"⏳ Пауза {delay:.1f}с после {func.__name__}")
                await asyncio.sleep(delay)
                return result

            except Exception as e:
                error_message = str(e).lower()

                # Критические ошибки
                if any(keyword in error_message for keyword in ['403', 'csrf', 'challenge_required', 'login_required']):
                    logger.error(f"🚨 Критическая ошибка API: {e}")
                    raise e

                # Лимиты - УВЕЛИЧЕННЫЕ паузы
                elif any(keyword in error_message for keyword in ['rate limit', 'please wait', 'spam']):
                    wait_time = min(1200 * (attempt + 1), 3600)  # До 1 часа
                    logger.warning(f"⏳ Превышение лимитов, пауза {wait_time / 60:.1f} мин: {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

                # Сетевые ошибки
                elif any(keyword in error_message for keyword in ['connection', 'timeout', 'network']):
                    wait_time = 20 * (2 ** attempt)  # Увеличенные паузы
                    logger.warning(f"🌐 Сетевая ошибка, пауза {wait_time}с: {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

                # Прочие ошибки
                else:
                    wait_time = random.uniform(60, 120)  # Увеличено
                    logger.warning(f"⚠️ Ошибка запроса (попытка {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)

                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise e

    async def simulate_human_activity(self, activity_type: HumanActivity, duration_minutes: int = None):
        """Имитация человеческой активности"""
        if not duration_minutes:
            duration_minutes = random.randint(5, 25)  # Увеличено время

        duration_seconds = duration_minutes * 60
        logger.info(f"🧑‍💻 Имитация активности: {activity_type.value} на {duration_minutes} мин")

        try:
            if activity_type == HumanActivity.EXPLORE:
                await self._simulate_explore(duration_seconds)
            elif activity_type == HumanActivity.WATCH_REELS:
                await self._simulate_watch_reels(duration_seconds)
            elif activity_type == HumanActivity.VIEW_STORIES:
                await self._simulate_view_stories(duration_seconds)
            elif activity_type == HumanActivity.BROWSE_FEED:
                await self._simulate_browse_feed(duration_seconds)
            elif activity_type == HumanActivity.SEARCH_HASHTAGS:
                await self._simulate_search_hashtags(duration_seconds)
            elif activity_type == HumanActivity.VIEW_PROFILES:
                await self._simulate_view_profiles(duration_seconds)

        except Exception as e:
            logger.warning(f"Ошибка имитации активности {activity_type.value}: {e}")

    async def _simulate_explore(self, duration_seconds: int):
        """Имитация просмотра ленты Explore"""
        start_time = time.time()

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                # Получаем explore медиа
                explore_medias = await self.safe_request(
                    self.client.explore_medias, amount=random.randint(3, 8)  # Уменьшено количество
                )

                # "Просматриваем" случайные посты
                for media in random.sample(explore_medias, min(2, len(explore_medias))):  # Меньше постов
                    if not self.is_running:
                        break

                    # Получаем информацию о посте (имитация просмотра)
                    await self.safe_request(self.client.media_info, media.pk)

                    # Очень редко лайкаем (2% вероятность)
                    if random.random() < 0.02 and self.check_rate_limits('like'):
                        await self.safe_request(self.client.media_like, media.pk)
                        logger.info(f"👍 Случайный лайк в Explore")

                    # Увеличенная пауза между просмотрами
                    await asyncio.sleep(random.uniform(30, 90))

            except Exception as e:
                logger.warning(f"Ошибка в explore: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def _simulate_watch_reels(self, duration_seconds: int):
        """Имитация просмотра Reels"""
        start_time = time.time()

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                # Получаем reels
                reels = await self.safe_request(
                    self.client.clips_explore, amount=random.randint(2, 5)  # Меньше reels
                )

                for reel in reels:
                    if not self.is_running:
                        break

                    # "Смотрим" reel (реалистичное время просмотра)
                    watch_time = random.uniform(15, 45)  # Увеличено время просмотра
                    logger.info(f"🎬 Смотрим Reel {watch_time:.1f}с")
                    await asyncio.sleep(watch_time)

                    # Очень редко лайкаем (1% вероятность)
                    if random.random() < 0.01 and self.check_rate_limits('like'):
                        await self.safe_request(self.client.media_like, reel.pk)
                        logger.info(f"👍 Лайк Reels")

                    # Увеличенная пауза между reels
                    await asyncio.sleep(random.uniform(10, 30))

            except Exception as e:
                logger.warning(f"Ошибка в reels: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def _simulate_browse_feed(self, duration_seconds: int):
        """Имитация просмотра основной ленты"""
        start_time = time.time()

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                # Получаем ленту
                feed = await self.safe_request(
                    self.client.feed_timeline, amount=random.randint(3, 8)
                )

                for media in feed:
                    if not self.is_running:
                        break

                    # "Просматриваем" пост
                    await asyncio.sleep(random.uniform(15, 40))  # Увеличено время

                    # Редко лайкаем (3% вероятность)
                    if random.random() < 0.03 and self.check_rate_limits('like'):
                        await self.safe_request(self.client.media_like, media.pk)
                        logger.info(f"👍 Лайк в ленте")

                    # Пауза между постами
                    await asyncio.sleep(random.uniform(10, 25))

            except Exception as e:
                logger.warning(f"Ошибка в ленте: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def _simulate_search_hashtags(self, duration_seconds: int):
        """Имитация поиска по хештегам с чешскими тегами"""
        start_time = time.time()

        # Чешские и международные хештеги
        hashtags = [
            'czech', 'prague', 'brno', 'ostrava', 'ceska', 'praha',
            'travel', 'food', 'art', 'music', 'photography', 'nature',
            'fashion', 'tech', 'ai', 'crypto', 'fitness', 'lifestyle'
        ]

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                hashtag = random.choice(hashtags)

                # Поиск по хештегу
                results = await self.safe_request(
                    self.client.hashtag_medias_recent, hashtag, amount=random.randint(2, 5)
                )

                # Просматриваем результаты
                for media in random.sample(results, min(2, len(results))):
                    if not self.is_running:
                        break

                    # "Просматриваем" пост
                    await asyncio.sleep(random.uniform(10, 25))

                    # Очень редко лайкаем (1% вероятность)
                    if random.random() < 0.01 and self.check_rate_limits('like'):
                        await self.safe_request(self.client.media_like, media.pk)
                        logger.info(f"👍 Лайк через хештег #{hashtag}")

                    await asyncio.sleep(random.uniform(15, 35))

            except Exception as e:
                logger.warning(f"Ошибка поиска хештегов: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def _simulate_view_stories(self, duration_seconds: int):
        """Имитация просмотра Stories"""
        start_time = time.time()

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                # Получаем story feed
                story_feed = await self.safe_request(self.client.story_feed)

                if story_feed and hasattr(story_feed, 'tray'):
                    for story_reel in random.sample(story_feed.tray, min(2, len(story_feed.tray))):
                        if not self.is_running:
                            break

                        # "Смотрим" stories пользователя
                        stories = await self.safe_request(
                            self.client.user_stories, story_reel.user.pk
                        )

                        for story in stories[:random.randint(1, 2)]:  # Меньше stories
                            # Имитация просмотра story
                            await asyncio.sleep(random.uniform(5, 12))

                        # Увеличенная пауза между пользователями
                        await asyncio.sleep(random.uniform(20, 45))

            except Exception as e:
                logger.warning(f"Ошибка в stories: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def _simulate_view_profiles(self, duration_seconds: int):
        """Имитация просмотра профилей"""
        start_time = time.time()

        while time.time() - start_time < duration_seconds and self.is_running:
            try:
                # Получаем suggested users
                suggested = await self.safe_request(
                    self.client.suggested_users, amount=random.randint(2, 5)
                )

                for user in suggested:
                    if not self.is_running:
                        break

                    # Просматриваем профиль
                    user_info = await self.safe_request(self.client.user_info, user.pk)
                    await asyncio.sleep(random.uniform(10, 25))

                    # Просматриваем несколько постов
                    user_medias = await self.safe_request(
                        self.client.user_medias, user.pk, amount=random.randint(1, 2)  # Меньше постов
                    )

                    for media in user_medias:
                        await asyncio.sleep(random.uniform(5, 15))

                    # Увеличенная пауза между профилями
                    await asyncio.sleep(random.uniform(25, 50))

            except Exception as e:
                logger.warning(f"Ошибка просмотра профилей: {e}")
                await asyncio.sleep(random.uniform(60, 120))

    async def random_distraction(self):
        """Случайное отвлечение во время работы"""
        if random.random() < 0.15:  # Увеличена вероятность до 15%
            distraction_type = random.choice([
                "profile_check",
                "notifications_check",
                "random_browse",
                "short_break"
            ])

            distraction_time = random.uniform(120, 600)  # 2-10 минут
            logger.info(f"🤔 Отвлечение: {distraction_type} на {distraction_time / 60:.1f} мин")

            await asyncio.sleep(distraction_time)
            return True
        return False

    def _decide_actions_randomly(self) -> List[str]:
        """Рандомное определение действий для выполнения"""
        actions = []

        # Лайк выполняем в 60% случаев (уменьшено с 70%)
        if random.random() < 0.6:
            actions.append('like')

            # Подписка только если лайкнули, и в 25% случаев (уменьшено с 40%)
            if random.random() < 0.25:
                actions.append('follow')

                # Сообщение только если подписались, и в 20% случаев (уменьшено с 30%)
                if random.random() < 0.2:
                    actions.append('message')

        # Если ничего не выбрали, иногда просто пропускаем пользователя
        if not actions and random.random() < 0.3:  # 30% шанс вообще ничего не делать
            return []
        elif not actions:
            actions.append('like')  # Хотя бы лайк

        return actions

    async def get_users_from_interactions(self, target_account: str, limit: int = 20) -> List[str]:  # Уменьшен лимит
        """Получение пользователей из лайков и комментариев"""
        try:
            logger.info(f"🎯 Получение пользователей из взаимодействий с @{target_account}")

            # Увеличенная начальная пауза
            await asyncio.sleep(random.uniform(45, 90))

            user_id = await self.safe_request(
                self.client.user_id_from_username, target_account
            )
            logger.info(f"✅ ID аккаунта @{target_account}: {user_id}")

            await asyncio.sleep(random.uniform(20, 40))

            # Получаем медиа с fallback
            medias = []
            try:
                medias = await self.safe_request(
                    self.client.user_medias, user_id, amount=self.config.posts_to_analyze
                )
            except Exception as e:
                logger.warning(f"⚠️ Основной метод получения медиа не сработал: {e}")
                try:
                    await asyncio.sleep(random.uniform(90, 180))  # Увеличенная пауза
                    medias = await self.safe_request(
                        self.client.user_medias, user_id, amount=1  # Только 1 пост при ошибке
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

                await asyncio.sleep(random.uniform(30, 60))  # Увеличенная пауза

                # Получаем лайкеров
                if InteractionType.LIKERS in self.config.interaction_types or InteractionType.BOTH in self.config.interaction_types:
                    try:
                        logger.info(f"👥 Получаем лайкеров поста...")
                        await asyncio.sleep(random.uniform(20, 40))

                        likers = await self.safe_request(
                            self.client.media_likers, media.id
                        )
                        logger.info(f"✅ Получено {len(likers)} лайкеров")

                        # Берем меньше лайкеров
                        for liker in likers[:min(8, len(likers))]:  # Уменьшено с 15 до 8
                            target_users.add(str(liker.pk))
                            if len(target_users) >= limit:
                                break

                    except Exception as e:
                        logger.warning(f"❌ Ошибка получения лайкеров: {e}")
                        await asyncio.sleep(random.uniform(120, 240))  # Увеличенная пауза при ошибке

                # Получаем комментаторов (реже)
                if (InteractionType.COMMENTERS in self.config.interaction_types or
                    InteractionType.BOTH in self.config.interaction_types) and len(target_users) < limit:

                    # Пропускаем комментаторов в 50% случаев для уменьшения активности
                    if random.random() < 0.5:
                        continue

                    try:
                        await asyncio.sleep(random.uniform(40, 80))  # Увеличенная пауза

                        logger.info(f"💬 Получаем комментаторов...")
                        comments = await self.safe_request(
                            self.client.media_comments, media.id, amount=5  # Уменьшено с 8 до 5
                        )
                        logger.info(f"✅ Получено {len(comments)} комментариев")

                        for comment in comments:
                            target_users.add(str(comment.user.pk))
                            if len(target_users) >= limit:
                                break

                    except Exception as e:
                        logger.warning(f"❌ Ошибка получения комментариев: {e}")

                # Увеличенная пауза между постами
                if i < len(medias) - 1:
                    pause_time = random.uniform(90, 180)  # Увеличено с 60-120
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
        """Взаимодействие с пользователем с максимальной рандомизацией"""
        results = {'like': False, 'follow': False, 'message': False}

        try:
            if self.db.is_user_processed(self.config.bot_id, user_id):
                return results

            if not self.check_user_basic_filters(user_id):
                return results

            user_info = await self.safe_request(self.client.user_info, user_id)
            logger.info(f"👤 Обрабатываем: @{user_info.username}")

            # Случайное отвлечение перед началом работы
            if await self.random_distraction():
                pass

            await asyncio.sleep(random.uniform(45, 90))  # Увеличенная пауза

            # Получаем посты пользователя
            try:
                user_medias = await self.safe_request(
                    self.client.user_medias, user_id, amount=self.config.posts_to_like
                )
            except:
                logger.warning(f"Не удалось получить посты @{user_info.username}")
                return results

            # РАНДОМИЗАЦИЯ ДЕЙСТВИЙ - определяем что будем делать
            actions_to_perform = self._decide_actions_randomly()

            if not actions_to_perform:
                logger.info(f"🎲 Пропускаем пользователя @{user_info.username} (случайное решение)")
                return results

            logger.info(f"🎲 Планируемые действия: {', '.join(actions_to_perform)}")

            # Лайкаем посты (если решили лайкать)
            if 'like' in actions_to_perform and self.check_rate_limits('like') and user_medias:
                try:
                    # Рандомное количество лайков (не всегда все посты)
                    likes_count = random.randint(1, min(len(user_medias), self.config.posts_to_like))
                    selected_medias = random.sample(user_medias, likes_count)

                    for i, media in enumerate(selected_medias):
                        if not self.is_running:
                            break

                        # Случайное отвлечение перед лайком
                        if await self.random_distraction():
                            pass

                        # Увеличенная пауза перед лайком
                        pre_like_delay = random.uniform(45, 120)  # Увеличено с 20-60
                        await asyncio.sleep(pre_like_delay)

                        await self.safe_request(self.client.media_like, media.id)
                        self.db.log_activity(self.config.bot_id, 'like', user_id, True)
                        logger.info(f"👍 Лайк {i + 1}/{likes_count} @{user_info.username}")

                        if i < likes_count - 1:
                            # Значительно увеличенная пауза между лайками
                            inter_like_delay = random.uniform(60, 180)  # Увеличено с 30-90
                            await asyncio.sleep(inter_like_delay)

                    results['like'] = True

                except Exception as e:
                    logger.warning(f"Ошибка лайка @{user_info.username}: {e}")
                    self.db.log_activity(self.config.bot_id, 'like', user_id, False, str(e))

            # Подписываемся (только если лайкнули и решили подписаться)
            if ('follow' in actions_to_perform and results['like'] and
                    self.check_rate_limits('follow') and self.is_running):

                # Случайное отвлечение перед подпиской
                if await self.random_distraction():
                    pass

                # МАКСИМАЛЬНО увеличенная пауза перед подпиской
                await asyncio.sleep(random.uniform(300, 600))  # 5-10 минут, было 3-5

                try:
                    await self.safe_request(self.client.user_follow, user_id)
                    self.db.log_activity(self.config.bot_id, 'follow', user_id, True)
                    results['follow'] = True
                    logger.info(f"➕ Подписка на @{user_info.username}")

                except Exception as e:
                    logger.warning(f"Ошибка подписки @{user_info.username}: {e}")
                    self.db.log_activity(self.config.bot_id, 'follow', user_id, False, str(e))

            # Отправляем сообщение (только если подписались и решили писать)
            if ('message' in actions_to_perform and results['follow'] and
                    self.check_rate_limits('message') and self.is_running):

                # Случайное отвлечение перед сообщением
                if await self.random_distraction():
                    pass

                # ЭКСТРЕМАЛЬНО увеличенная пауза перед сообщением
                await asyncio.sleep(random.uniform(600, 1200))  # 10-20 минут, было 5-10

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

            # МАКСИМАЛЬНО увеличенная пауза между пользователями
            if self.is_running:
                delay = random.uniform(1200, 2400)  # 20-40 минут, было 10-20
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
        if not self.session_locked:
            if not self.acquire_session_lock():
                logger.warning(
                    f"⚠️ Сессия {self.config.username} уже используется, но продолжаем (управляется backend)")
                self.session_locked = True  # Принудительно устанавливаем флаг

        self.login_attempts += 1

        try:
            self._setup_client()

            await asyncio.sleep(random.uniform(10, 30))  # Увеличенная пауза

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

            await asyncio.sleep(random.uniform(30, 60))  # Увеличенная пауза

            success = self.client.login(self.config.username, self.config.password)

            if success:
                try:
                    account_info = self.client.account_info()
                    logger.info(f"✅ Успешный новый вход: @{self.config.username}")
                    self.is_logged_in = True
                    self.login_attempts = 0

                    self._save_session_safely()
                    await asyncio.sleep(random.uniform(60, 120))  # Увеличенная пауза после входа
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
        """Основной цикл работы бота с человеческой активностью"""
        try:
            logger.info(f"🎯 === НАЧАЛО ЦИКЛА для {self.config.username} ===")

            # Имитация человеческого поведения в начале - ОБЯЗАТЕЛЬНО
            if random.random() < 0.5:  # 50% вероятность
                activity = random.choice(list(HumanActivity))
                await self.simulate_human_activity(activity, random.randint(5, 15))

            if not self.config.target_accounts:
                logger.error("❌ ОШИБКА: Список целевых аккаунтов пуст!")
                return

            for i, target_account in enumerate(self.config.target_accounts):
                if not self.is_running:
                    logger.info("🛑 Бот остановлен, прерываем цикл")
                    break

                logger.info(f"🎯 === АККАУНТ {i + 1}/{len(self.config.target_accounts)}: @{target_account} ===")

                try:
                    target_users = await self.get_users_from_interactions(target_account, limit=10)  # Уменьшен лимит

                    if not target_users:
                        logger.warning(f"⚠️ Не удалось получить пользователей из @{target_account}")
                        continue

                    logger.info(f"✅ Получено {len(target_users)} пользователей из @{target_account}")

                    # Рандомизируем порядок и количество пользователей
                    random.shuffle(target_users)

                    # Берем случайное количество пользователей (40-70% от общего)
                    take_count = random.randint(
                        int(len(target_users) * 0.4),
                        int(len(target_users) * 0.7)
                    )
                    target_users = target_users[:take_count]
                    logger.info(f"🎲 Обрабатываем {len(target_users)} из {len(target_users)} пользователей")

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

                            # Рандомные перерывы каждые 2-3 пользователя
                            if (j + 1) % random.randint(2, 3) == 0 and self.is_running:
                                # Случайная человеческая активность
                                if random.random() < 0.6:  # 60% вероятность
                                    activity = random.choice([
                                        HumanActivity.BROWSE_FEED,
                                        HumanActivity.WATCH_REELS,
                                        HumanActivity.EXPLORE
                                    ])
                                    await self.simulate_human_activity(activity, random.randint(3, 10))
                                else:
                                    # Обычный перерыв
                                    break_time = random.uniform(1200, 2400)  # 20-40 минут
                                    logger.info(f"☕ Большой перерыв {break_time / 60:.1f} минут")

                                    while break_time > 0 and self.is_running:
                                        sleep_time = min(60, break_time)
                                        await asyncio.sleep(sleep_time)
                                        break_time -= sleep_time

                        except Exception as e:
                            logger.error(f"❌ Ошибка обработки пользователя {user_id}: {e}")
                            skipped_count += 1
                            await asyncio.sleep(random.uniform(300, 600))  # Увеличенная пауза при ошибке

                    logger.info(f"📊 Результаты для @{target_account}:")
                    logger.info(f"   ✅ Обработано: {processed_count}")
                    logger.info(f"   ⏭️ Пропущено: {skipped_count}")

                    # Большая человеческая активность между аккаунтами
                    if i < len(self.config.target_accounts) - 1 and self.is_running:
                        if random.random() < 0.8:  # 80% вероятность
                            activity = random.choice(list(HumanActivity))
                            await self.simulate_human_activity(activity, random.randint(10, 25))

                        pause_minutes = random.uniform(90, 180)  # 1.5-3 часа, было 45-90 минут
                        logger.info(f"😴 БОЛЬШАЯ пауза {pause_minutes:.1f} мин перед следующим аккаунтом")

                        pause_seconds = pause_minutes * 60
                        while pause_seconds > 0 and self.is_running:
                            sleep_time = min(60, pause_seconds)
                            await asyncio.sleep(sleep_time)
                            pause_seconds -= sleep_time

                except Exception as e:
                    logger.error(f"❌ Критическая ошибка при обработке @{target_account}: {e}")
                    await asyncio.sleep(random.uniform(1800, 3600))  # 30-60 минут при ошибке

            logger.info(f"🏁 === ЦИКЛ ЗАВЕРШЕН для {self.config.username} ===")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле: {e}")
            await asyncio.sleep(random.uniform(3600, 7200))  # 1-2 часа при критической ошибке

    async def start(self):
        """Запуск бота"""
        try:
            logger.info(f"🚀 Запуск CZECH OPTIMIZED бота: {self.config.username}")
            logger.info(f"🖥️ Платформа: {platform.system()} {platform.release()}")
            logger.info(
                f"🇨🇿 Устройство: {self.device['brand']} {self.device['name']} (Android {self.device['android_version']})")

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

                    # ЭКСТРЕМАЛЬНО увеличенная пауза между циклами
                    if self.is_running and self.config.active:
                        if cycle_count == 1:
                            pause_hours = random.uniform(3, 6)  # 3-6 часов, было 1-2
                            logger.info(f"😴 Пауза {pause_hours:.1f} часов после первого цикла")
                        else:
                            pause_hours = random.uniform(12, 24)  # 12-24 часа, было 6-12
                            logger.info(f"😴 ОГРОМНАЯ пауза {pause_hours:.1f} часов до следующего цикла")

                        pause_seconds = pause_hours * 3600
                        while pause_seconds > 0 and self.is_running and self.config.active:
                            sleep_time = min(300, pause_seconds)  # Проверяем каждые 5 минут
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

                    await asyncio.sleep(random.uniform(3600, 7200))  # 1-2 часа при ошибке

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
                'device': f"{self.device['brand']} {self.device['name']}",
                'proxy': self.config.proxy.to_dict() if self.config.proxy else None
            }


# Обновляем основные классы для использования нового бота
FixedInstagramBot = CzechInstagramBot  # Алиас для совместимости


def create_config_for_czech_users() -> BotConfig:
    """Создание конфигурации для чешских пользователей"""
    filters = UserFilter(
        min_followers=20,  # Еще более мягкие фильтры
        max_followers=5000,  # Уменьшен максимум
        min_following=5,
        max_following=1000,  # Уменьшен максимум
        min_posts=1,
        has_profile_pic=False,
        private_account=False,
        countries=[],
        languages=[],
        exclude_business_accounts=False,
        exclude_verified_accounts=True,
        required_keywords_in_bio=[],
        excluded_keywords_in_bio=['bot', 'spam', 'fake', 'business']
    )

    config = BotConfig(
        bot_id="czech_optimized_bot",
        username="artem_lotariev_",  # 🔧 ЗАМЕНИТЕ НА ВАШ USERNAME
        password="Artem1702L",  # 🔧 ЗАМЕНИТЕ НА ВАШ ПАРОЛЬ

        target_accounts=[
            "natgeo",
            "nasa",
            "techcrunch"
        ],

        filters=filters,
        message_template="Ahoj! Zajímavý obsah na @{main_account} 🇨🇿",
        main_account="pschol",  # 🔧 ЗАМЕНИТЕ НА ВАШ ОСНОВНОЙ АККАУНТ

        interaction_types=[InteractionType.LIKERS],
        posts_to_analyze=2,  # Уменьшено
        posts_to_like=1,  # Уменьшено

        # ЭКСТРЕМАЛЬНО мягкие лимиты для избежания банов
        max_likes_per_hour=3,  # Было 4
        max_follows_per_hour=1,  # Было 2
        max_messages_per_hour=1,  # Без изменений

        # ЭКСТРЕМАЛЬНО увеличенные паузы
        min_delay=1800,  # 30 минут, было 20
        max_delay=3600,  # 60 минут, было 40

        message_variants=[
            "Ahoj {name}! Zajímavý obsah na @{main_account} 🇨🇿",
            "Zdravím! Doporučuji navštívit @{main_account} ✨",
            "Ahoj! AI a novinky na @{main_account} 🤖"
        ],

        personalized_messages=True
    )

    return config


async def test_czech_optimized_bot():
    """Тест чешского оптимизированного бота"""
    print("🧪 ТЕСТ CZECH OPTIMIZED INSTAGRAM БОТА")
    print("=" * 60)
    print(f"🖥️ Платформа: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print()

    config = create_config_for_czech_users()

    if config.password == "YOUR_PASSWORD_HERE" or config.main_account == "YOUR_MAIN_ACCOUNT":
        print("❌ ОШИБКА: Настройте конфигурацию!")
        print("🔧 Откройте launcher.py и измените:")
        print('   username="your_instagram_username"')
        print('   password="your_password"')
        print('   main_account="your_main_account"')
        return

    async with CzechInstagramBot(config) as bot:
        try:
            print(f"🔑 Тестируем авторизацию @{config.username}...")
            print(f"🇨🇿 Устройство: {bot.device['brand']} {bot.device['name']}")

            if await bot.login():
                print("✅ Авторизация успешна!")
                print("🚀 Запуск оптимизированной работы...")
                await bot.start()
            else:
                print("❌ Ошибка авторизации")

        except KeyboardInterrupt:
            print("\n🛑 Получена команда остановки (Ctrl+C)")
            bot.stop()
        except Exception as e:
            print(f"❌ Ошибка: {e}")


def show_czech_optimization_info():
    """Показать информацию об оптимизации для Чехии"""
    print("🇨🇿 CZECH OPTIMIZATION INFO")
    print("=" * 50)

    # Показываем примеры устройств
    devices = CzechDeviceManager.get_czech_devices()
    print("📱 ПОПУЛЯРНЫЕ УСТРОЙСТВА В ЧЕХИИ:")
    for device in devices[:5]:
        print(f"   {device['brand']} {device['name']} (Android {device['android_version']})")
    print()

    print("🔧 ОПТИМИЗАЦИИ:")
    print("   ✅ Чешские User-Agent строки")
    print("   ✅ Локализация cs_CZ (Чехия)")
    print("   ✅ Timezone Europe/Prague (UTC+1)")
    print("   ✅ Реалистичные устройства Samsung/Xiaomi")
    print("   ✅ ЭКСТРЕМАЛЬНО увеличенные паузы")
    print("   ✅ Максимальная рандомизация действий")
    print("   ✅ Имитация человеческой активности")
    print("   ✅ Случайные отвлечения и перерывы")
    print()

    print("⚡ НОВЫЕ ЛИМИТЫ (АНТИ-БАН):")
    print("   📊 Лайков в час: 3 (было 6)")
    print("   👥 Подписок в час: 1 (было 2)")
    print("   💬 Сообщений в час: 1 (без изменений)")
    print("   ⏱️ Мин. пауза: 30 мин (было 20)")
    print("   ⏱️ Макс. пауза: 60 мин (было 40)")
    print()

    print("🎲 РАНДОМИЗАЦИЯ:")
    print("   • Только 60% пользователей получают лайки")
    print("   • Только 25% лайкнутых получают подписку")
    print("   • Только 20% подписанных получают сообщение")
    print("   • 15% шанс случайного отвлечения")
    print("   • Человеческая активность между пользователями")
    print()

    print("🧑‍💻 ИМИТАЦИЯ ЧЕЛОВЕКА:")
    print("   🔍 Просмотр Explore")
    print("   🎬 Просмотр Reels")
    print("   📸 Просмотр Stories")
    print("   📱 Просмотр ленты")
    print("   🔎 Поиск по хештегам")
    print("   👤 Просмотр профилей")


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


if __name__ == "__main__":
    print("🇨🇿 CZECH OPTIMIZED INSTAGRAM BOT v3.0.2025")
    print("=" * 65)
    print("🔧 КЛЮЧЕВЫЕ УЛУЧШЕНИЯ:")
    print("   ✅ Реальные чешские устройства (Samsung, Xiaomi, OnePlus)")
    print("   ✅ Аутентичные User-Agent строки для Чехии")
    print("   ✅ ЭКСТРЕМАЛЬНО увеличенные задержки (анти-бан)")
    print("   ✅ Максимальная рандомизация всех действий")
    print("   ✅ Имитация реального человеческого поведения")
    print("   ✅ Случайные отвлечения и активности")
    print("   ✅ Чешская локализация и временная зона")
    print("   ✅ Мягчайшие лимиты активности")
    print()

    if len(sys.argv) > 1:
        if sys.argv[1] == '--info':
            show_czech_optimization_info()
        elif sys.argv[1] == '--test':
            asyncio.run(test_czech_optimized_bot())
        elif sys.argv[1] == '--devices':
            print("📱 ДОСТУПНЫЕ ЧЕШСКИЕ УСТРОЙСТВА:")
            for i, device in enumerate(CzechDeviceManager.get_czech_devices(), 1):
                print(f"{i:2d}. {device['brand']} {device['name']} (Android {device['android_version']})")
                print(f"     Разрешение: {device['resolution']}, DPI: {device['dpi']}")
                print()
        else:
            print("❓ Доступные команды:")
            print("   --info    : Информация об оптимизации")
            print("   --test    : Тестовый запуск")
            print("   --devices : Список чешских устройств")
    else:
        print("🚀 Для запуска используйте:")
        print("   python launcher.py --test")
        print()
        print("⚠️ ВНИМАНИЕ: Новые экстремальные задержки!")
        print("   • Пауза между пользователями: 20-40 минут")
        print("   • Пауза между аккаунтами: 1.5-3 часа")
        print("   • Пауза между циклами: 12-24 часа")
        print("   • Это НОРМАЛЬНО для избежания банов!")
        print()
        asyncio.run(test_czech_optimized_bot())
