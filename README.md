# 🤖 Genesis Bot

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.5.2-blue.svg)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://github.com/yourusername/genesis-discord-bot/workflows/CI/badge.svg)](https://github.com/yourusername/genesis-discord-bot/actions)

Discord бот для мониторинга форума, Twitch стримов и YouTube видео с системой ролей через реакции.

## ✨ Возможности

- **📋 Мониторинг форума** - автоматическое отслеживание новых постов
- **🎮 Twitch интеграция** - уведомления о начале стримов
- **📺 YouTube интеграция** - уведомления о новых видео
- **👥 Система ролей** - выдача ролей через реакции на сообщение
- **🔒 Административные команды** - управление через слэш-команды

## 🚀 Быстрый старт

### 1. Клонирование репозитория
```bash
git clone https://github.com/yourusername/genesis-discord-bot.git
cd genesis-discord-bot
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка конфигурации
Скопируйте пример конфигурации:
```bash
cp examples/env.example .env
```

Отредактируйте файл `.env` и заполните необходимые значения.

## ⚙️ Настройка

### Переменные окружения (.env)

```env
# Основные настройки Discord
DISCORD_TOKEN=your_discord_bot_token
GUILD_ID=your_guild_id
ROLES_CHANNEL_ID=channel_id_for_roles
FORUM_CHANNEL_ID=channel_id_for_forum_notifications
NOTIFICATIONS_CHANNEL_ID=channel_id_for_stream_video_notifications

# API ключи
YOUTUBE_API_KEY=your_youtube_api_key
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
```

### Файлы конфигурации

- `reaction_roles.json` - настройка ролей для реакций
- `channels.json` - список отслеживаемых каналов
- `notified.json` - история отправленных уведомлений

## 🚀 Запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Настройте переменные окружения в файле `.env`

3. Запустите бота:
```bash
python bot.py
```

## 📋 Команды

### Административные
- `/sync` - Пересинхронизировать слэш-команды

### Форум
- `/force_forum_check` - Проверить форум вручную

### Twitch
- `/twitch_add <login>` - Добавить Twitch-канал
- `/twitch_remove <login>` - Удалить Twitch-канал
- `/twitch_list` - Список отслеживаемых каналов
- `/twitch_check <login>` - Проверить канал вручную

### YouTube
- `/youtube_add <channel>` - Добавить YouTube-канал
- `/youtube_remove <channel>` - Удалить YouTube-канал
- `/youtube_list` - Список отслеживаемых каналов
- `/youtube_check <channel>` - Проверить канал вручную

## ⏰ Интервалы проверки

- **Форум**: каждые 5 минут
- **Twitch стримы**: каждые 2 минуты
- **YouTube видео**: каждые 2 минуты

## 🔧 Последние изменения

### v2.0 - Улучшения и оптимизация

✅ **Изменен интервал проверки**:
- Twitch и YouTube: с 10 секунд до 2 минут
- Снижена нагрузка на API и улучшена производительность

✅ **Улучшен код**:
- Добавлены подробные комментарии и документация
- Улучшена структура и читаемость кода
- Добавлены эмодзи для лучшего UX
- Улучшена обработка ошибок

✅ **Улучшен пользовательский интерфейс**:
- Более информативные сообщения об ошибках
- Красивое форматирование списков
- Эмодзи для статусов (✅, ❌, ⚠️, 📋, 🎮, 📺)

## 📁 Структура проекта

```
genesis-discord-bot/
├── bot.py                    # Основной файл бота
├── handlers.py               # Обработчики событий
├── requirements.txt          # Зависимости Python
├── setup.py                  # Конфигурация установки
├── pyproject.toml           # Современная конфигурация проекта
├── README.md                # Документация
├── LICENSE                  # MIT лицензия
├── CHANGELOG.md             # История изменений
├── CONTRIBUTING.md          # Руководство для контрибьюторов
├── .gitignore               # Исключения Git
├── .github/                 # GitHub конфигурация
│   ├── workflows/           # GitHub Actions
│   ├── ISSUE_TEMPLATE/      # Шаблоны issues
│   └── PULL_REQUEST_TEMPLATE.md
├── examples/                # Примеры конфигурации
│   ├── env.example          # Пример .env файла
│   ├── reaction_roles.example.json
│   └── channels.example.json
├── tests/                   # Тесты (будущие)
└── docs/                    # Документация (будущая)
```

## 🔧 Разработка

### Установка для разработки
```bash
git clone https://github.com/yourusername/genesis-discord-bot.git
cd genesis-discord-bot
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
pip install -e ".[dev]"
```

### Запуск тестов
```bash
pytest
```

### Проверка кода
```bash
flake8 .
black .
isort .
mypy .
```

## 🤝 Вклад в проект

Мы приветствуем вклад от сообщества! Пожалуйста, прочитайте [CONTRIBUTING.md](CONTRIBUTING.md) для получения подробной информации о том, как внести свой вклад.

## 📄 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для подробностей.

## 🔗 Ссылки

- [Документация Discord.py](https://discordpy.readthedocs.io/)
- [Discord Developer Portal](https://discord.com/developers/applications)
- [Twitch Developer Portal](https://dev.twitch.tv/)
- [YouTube Data API](https://developers.google.com/youtube/v3)

## ⭐ Поддержка проекта

Если этот проект помог вам, поставьте звезду ⭐ на GitHub!

## 🤝 Поддержка

При возникновении проблем проверьте:
1. Правильность настройки переменных окружения
2. Права бота в Discord каналах
3. Валидность API ключей
4. Логи в консоли для диагностики ошибок
5. [Issues на GitHub](https://github.com/yourusername/genesis-discord-bot/issues)


