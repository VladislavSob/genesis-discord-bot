import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv

# Загружаем переменные окружения ДО импорта handlers
load_dotenv(override=True)

import discord
from discord.ext import commands
from discord.ext import tasks
from discord import app_commands
import handlers
import traceback

# =============================================================================
# НАСТРОЙКА ЛОГГИРОВАНИЯ
# =============================================================================

def setup_logging():
    """Настройка системы логирования"""
    # Создаем папку для логов если её нет
    os.makedirs("logs", exist_ok=True)

    # Полная очистка корневого логгера и установка уровня
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)

    # Настраиваем логгер бота
    logger = logging.getLogger("genesis_bot")
    logger.setLevel(logging.DEBUG)

    # Форматтер для логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Хендлер для файла (ротация по времени, хранить ~24 часа истории)
    file_handler = TimedRotatingFileHandler(
        "logs/genesis.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=False
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Хендлер для консоли (только важные сообщения)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    # Добавляем хендлеры к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False  # не пускать записи вверх к root

    # Отдельный логгер для парсинга форума -> logs/forum.log
    forum_logger = logging.getLogger("genesis_bot.forum")
    forum_logger.setLevel(logging.DEBUG)
    forum_logger.propagate = False

    forum_handler = TimedRotatingFileHandler(
        "logs/forum.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=False
    )
    forum_handler.setLevel(logging.DEBUG)
    forum_handler.setFormatter(formatter)
    forum_logger.addHandler(forum_handler)

    # Отдельный логгер для парсинга ордеров -> logs/orders.log
    orders_logger = logging.getLogger("genesis_bot.orders")
    orders_logger.setLevel(logging.DEBUG)
    orders_logger.propagate = False

    orders_handler = TimedRotatingFileHandler(
        "logs/orders.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=False
    )
    orders_handler.setLevel(logging.DEBUG)
    orders_handler.setFormatter(formatter)
    orders_logger.addHandler(orders_handler)

    # Приглушаем логгеры discord.py и других библиотек и чистим их хендлеры
    for name in ["discord", "discord.client", "discord.gateway", "discord.http",
                 "aiohttp", "aiohttp.access", "aiohttp.client", "asyncio"]:
        lib_logger = logging.getLogger(name)
        lib_logger.handlers.clear()
        lib_logger.setLevel(logging.ERROR)  # можно поставить WARNING при необходимости
        lib_logger.propagate = False

    return logger

# Инициализируем логирование
logger = setup_logging()

# =============================================================================
# КОНФИГУРАЦИЯ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# =============================================================================

def load_environment():
    """Загрузка и валидация переменных окружения"""
    required_vars = {
        "DISCORD_TOKEN": "Токен Discord бота",
        "GUILD_ID": "ID сервера Discord",
        "ROLES_CHANNEL_ID": "ID канала для ролей",
        "FORUM_CHANNEL_ID": "ID канала для форума",
        "NOTIFICATIONS_CHANNEL_ID": "ID канала для уведомлений",
        "ORDERS_CHANNEL_ID": "ID канала для ордеров"
    }
    
    config = {}
    missing_vars = []
    
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if not value:
            missing_vars.append(f"{var_name} ({description})")
        else:
            try:
                # Конвертируем ID в целые числа
                if var_name.endswith("_ID"):
                    config[var_name] = int(value)
                else:
                    config[var_name] = value
            except ValueError:
                logger.error(f"❌ Неверный формат {var_name}: должно быть число")
                missing_vars.append(var_name)
    
    if missing_vars:
        logger.error("❌ Отсутствуют обязательные переменные окружения:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        raise SystemExit(1)
    
    logger.info("✅ Все обязательные переменные окружения загружены")
    return config

# Загружаем конфигурацию
config = load_environment()
TOKEN = config["DISCORD_TOKEN"]
GUILD_ID = config["GUILD_ID"]
ROLES_CHANNEL_ID = config["ROLES_CHANNEL_ID"]
FORUM_CHANNEL_ID = config["FORUM_CHANNEL_ID"]
NOTIFICATIONS_CHANNEL_ID = config["NOTIFICATIONS_CHANNEL_ID"]
ORDERS_CHANNEL_ID = config["ORDERS_CHANNEL_ID"]

# =============================================================================
# НАСТРОЙКА INTENTS
# =============================================================================

def setup_intents():
    """Настройка Discord intents"""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.reactions = True
    return intents

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ХЕЛПЕРЫ
# =============================================================================

async def ensure_deferred(interaction: discord.Interaction, *, ephemeral: bool = True):
    """Безопасно подтверждает взаимодействие, если оно ещё не подтверждено."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=ephemeral)


# =============================================================================
# HEARTBEAT ДЛЯ РОТАЦИИ ЛОГОВ
# =============================================================================

@tasks.loop(minutes=10)
async def heartbeat_log():
    try:
        logger.debug("heartbeat: bot alive")
    except Exception:
        pass

# =============================================================================
# ФУНКЦИИ ПРОВЕРКИ ПРАВ ДОСТУПА
# =============================================================================

def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    """Проверяет, является ли пользователь администратором или владельцем сервера"""
    if interaction.guild is None:
        return False
    return (interaction.user.id == interaction.guild.owner_id or 
            interaction.user.guild_permissions.administrator)

def admin_only():
    """Декоратор для ограничения доступа только администраторам и владельцам"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "🚫 Доступ запрещён. Нужны права администратора или владельца сервера.", 
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# =============================================================================
# КЛАСС БОТА
# =============================================================================

class GenesisBot(commands.Bot):
    """Основной класс бота Genesis"""
    
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=setup_intents(),
            help_command=None  # Отключаем встроенную команду help
        )
        self.logger = logger
    
    async def setup_hook(self) -> None:
        """Инициализация бота при запуске"""
        try:
            # Регистрируем команды глобально и копируем их в нужную гильдию
            await self.tree.sync()
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            self.logger.info("✅ Слэш-команды успешно синхронизированы")
        except Exception as e:
            self.logger.error(f"❌ Ошибка при синхронизации команд: {e}")
            traceback.print_exc()
        
        # Heartbeat: чтобы ротация логов срабатывала сразу после полуночи
        try:
            if not heartbeat_log.is_running():
                heartbeat_log.start()
        except Exception:
            pass

# Создаем экземпляр бота
bot = GenesisBot()

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

async def check_channel_permissions(channel_id: int, label: str) -> bool:
    """Проверяет права бота в указанном канале"""
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            logger.warning(f"⚠️  {label}: Канал {channel_id} не найден")
            return False
        
        # Проверяем, что канал имеет guild (серверный канал)
        if not hasattr(channel, 'guild') or channel.guild is None:
            logger.warning(f"⚠️  {label}: Канал {channel_id} не является серверным каналом")
            return False
            
        # Получаем права бота в канале
        permissions = channel.permissions_for(channel.guild.me)
        required_perms = ["view_channel", "send_messages"]
        missing_perms = [perm for perm in required_perms if not getattr(permissions, perm)]
        
        if missing_perms:
            logger.warning(f"⚠️  {label}: Недостаточно прав: {', '.join(missing_perms)}")
            return False
        
        logger.info(f"✅ {label}: Права в порядке")
        return True
        
    except Exception as e:
        logger.error(f"❌ {label}: Ошибка проверки прав: {e}")
        return False

# =============================================================================
# СОБЫТИЯ БОТА
# =============================================================================

@bot.event
async def on_ready():
    """Событие запуска бота"""
    logger.info(f"🤖 Бот {bot.user} успешно запущен!")
    logger.info(f"🆔 ID бота: {bot.user.id}")
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        logger.info(f"🏠 Сервер: {guild.name}")
    else:
        logger.warning(f"⚠️  Сервер {GUILD_ID} не найден")

    # Диагностика прав в каналах
    logger.info("🔍 Проверка прав доступа к каналам:")
    await check_channel_permissions(NOTIFICATIONS_CHANNEL_ID, "Notifications")
    await check_channel_permissions(FORUM_CHANNEL_ID, "Forum")
    await check_channel_permissions(ROLES_CHANNEL_ID, "Roles")
    await check_channel_permissions(ORDERS_CHANNEL_ID, "Orders")

    # Инициализируем сообщение с ролями
    try:
        await handlers.ensure_roles_message(guild, ROLES_CHANNEL_ID)
        logger.info("✅ Сообщение с ролями инициализировано")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации сообщения с ролями: {e}")

    # Запускаем проверку форума, если она еще не запущена
    if not handlers.check_forum.is_running():
        handlers.check_forum.start(bot, FORUM_CHANNEL_ID)
        logger.info("✅ Проверка форума запущена")

    # Запускаем проверку ордеров, если она еще не запущена
    if not handlers.check_orders.is_running():
        handlers.check_orders.start(bot, ORDERS_CHANNEL_ID)
        logger.info("✅ Проверка ордеров запущена")

    # Запускаем отслеживание стримов и видео
    handlers.start_tracking_tasks(bot, NOTIFICATIONS_CHANNEL_ID)
    logger.info("✅ Отслеживание Twitch и YouTube запущено")
    logger.info("⏰ Интервал проверки: 2 минуты")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Обработка добавления реакции"""
    await handlers.handle_reaction_add(payload, bot)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Обработка удаления реакции"""
    await handlers.handle_reaction_remove(payload, bot)

# =============================================================================
# КОМАНДЫ УПРАВЛЕНИЯ
# =============================================================================

@bot.tree.command(name="sync", description="Пересинхронизировать слэш-команды")
@admin_only()
async def sync_cmd(interaction: discord.Interaction):
    """Пересинхронизирует слэш-команды"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        await bot.tree.sync()
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
        await interaction.followup.send(
            "✅ Слэш-команды успешно пересинхронизированы!", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Ошибка при синхронизации: {e}", 
            ephemeral=True
        )

@bot.tree.command(name="fix_roles", description="Исправить конфликтующие роли на сервере")
@admin_only()
async def fix_roles_cmd(interaction: discord.Interaction):
    """Проверяет и исправляет все конфликтующие роли на сервере"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Не удалось получить информацию о сервере", ephemeral=True)
            return
            
        await interaction.followup.send("🔍 Проверяю конфликтующие роли...", ephemeral=True)
        
        violation_count, messages = await handlers.fix_conflicting_roles(guild)
        
        if violation_count == 0:
            await interaction.followup.send("✅ Конфликтующих ролей не найдено!", ephemeral=True)
        else:
            # Формируем сообщение с результатами
            result_message = f"⚠️ Найдено {violation_count} нарушений правил ролей:\n\n"
            
            # Добавляем первые 10 сообщений (чтобы не превысить лимит Discord)
            for i, msg in enumerate(messages[:10]):
                result_message += f"• {msg}\n"
            
            if len(messages) > 10:
                result_message += f"\n... и еще {len(messages) - 10} нарушений"
            
            result_message += "\n\n💡 Используйте команды администратора Discord для снятия лишних ролей."
            
            await interaction.followup.send(result_message, ephemeral=True)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при исправлении ролей: {e}", ephemeral=True)



# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С ФОРУМОМ
# =============================================================================

@bot.tree.command(name="force_forum_check", description="Проверить форум вручную")
@admin_only()
async def force_forum_check(interaction: discord.Interaction):
    """Принудительно проверяет форум и показывает последний пост"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        post = await handlers.parse_forum()
        if post and post.get("text"):
            await interaction.followup.send(
                f"📋 Последний пост на форуме:\n{post['url']}", 
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Не удалось получить пост.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="forum_diagnose", description="Диагностика состояния форума")
@admin_only()
async def forum_diagnose(interaction: discord.Interaction):
    """Показывает диагностическую информацию о состоянии форума"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        result = await handlers.diagnose_forum(bot, FORUM_CHANNEL_ID)
        await interaction.followup.send(f"🔍 {result}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка диагностики: {e}", ephemeral=True)

@bot.tree.command(name="reset_forum_state", description="Сбросить состояние форума (если удалили сообщение)")
@admin_only()
async def reset_forum_state(interaction: discord.Interaction):
    """Сбрасывает состояние форума, чтобы бот отправил последний пост заново"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        notified = handlers.load_notified()
        forum_state = notified.get("forum", {})
        old_post_id = forum_state.get("last_post_id")
        
        # Сбрасываем ID последнего поста
        forum_state["last_post_id"] = None
        notified["forum"] = forum_state
        handlers.save_notified(notified)
        
        await interaction.followup.send(
            f"✅ Состояние форума сброшено!\n"
            f"📝 Предыдущий ID поста: {old_post_id}\n"
            f"🔄 Бот отправит последний пост при следующей проверке.", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при сбросе состояния: {e}", ephemeral=True)

# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С ОРДЕРАМИ
# =============================================================================

@bot.tree.command(name="force_orders_check", description="Проверить ордера вручную")
@admin_only()
async def force_orders_check(interaction: discord.Interaction):
    """Принудительно проверяет ордера и показывает последний ордер"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        order = await handlers.parse_orders()
        if order and order.get("text"):
            await interaction.followup.send(
                f"📋 Последний ордер:\n{order['url']}", 
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Не удалось получить ордер.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="orders_diagnose", description="Диагностика состояния ордеров")
@admin_only()
async def orders_diagnose(interaction: discord.Interaction):
    """Показывает диагностическую информацию о состоянии ордеров"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        result = await handlers.diagnose_orders(bot, ORDERS_CHANNEL_ID)
        await interaction.followup.send(f"🔍 {result}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка диагностики: {e}", ephemeral=True)

@bot.tree.command(name="reset_orders_state", description="Сбросить состояние ордеров (если удалили сообщение)")
@admin_only()
async def reset_orders_state(interaction: discord.Interaction):
    """Сбрасывает состояние ордеров, чтобы бот отправил последний ордер заново"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        notified = handlers.load_notified()
        orders_state = notified.get("orders", {})
        old_order_id = orders_state.get("last_order_id")
        
        # Сбрасываем ID последнего ордера
        orders_state["last_order_id"] = None
        notified["orders"] = orders_state
        handlers.save_notified(notified)
        
        await interaction.followup.send(
            f"✅ Состояние ордеров сброшено!\n"
            f"📝 Предыдущий ID ордера: {old_order_id}\n"
            f"🔄 Бот отправит последний ордер при следующей проверке.", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при сбросе состояния: {e}", ephemeral=True)

# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С TWITCH
# =============================================================================

@bot.tree.command(name="twitch_add", description="Добавить Twitch-канал для отслеживания")
@admin_only()
async def twitch_add(interaction: discord.Interaction, login: str):
    """Добавляет Twitch-канал в список отслеживаемых"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = handlers.add_twitch_channel(login)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="twitch_remove", description="Удалить Twitch-канал из отслеживания")
@admin_only()
async def twitch_remove(interaction: discord.Interaction, login: str):
    """Удаляет Twitch-канал из списка отслеживаемых"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = handlers.remove_twitch_channel(login)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="twitch_list", description="Показать список отслеживаемых Twitch-каналов")
@admin_only()
async def twitch_list(interaction: discord.Interaction):
    """Показывает список всех отслеживаемых Twitch-каналов"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        channels = handlers.list_twitch_channels()
        if channels:
            channel_list = "\n".join(f"• {channel}" for channel in channels)
            await interaction.followup.send(f"📺 Отслеживаемые Twitch-каналы:\n{channel_list}", ephemeral=True)
        else:
            await interaction.followup.send("📺 Нет отслеживаемых Twitch-каналов", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="twitch_check", description="Проверить Twitch-канал вручную")
@admin_only()
async def twitch_check(interaction: discord.Interaction, login: str):
    """Проверяет Twitch-канал и отправляет уведомление если онлайн"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = await handlers.twitch_check_and_notify(bot, NOTIFICATIONS_CHANNEL_ID, login)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С YOUTUBE
# =============================================================================

@bot.tree.command(name="youtube_add", description="Добавить YouTube-канал (@handle, URL https://youtube.com/@..., или channelId UC...)")
@admin_only()
async def youtube_add(interaction: discord.Interaction, channel: str):
    """Добавляет YouTube-канал в список отслеживаемых"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = await handlers.add_youtube_channel(channel)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="youtube_remove", description="Удалить YouTube-канал из отслеживания")
@admin_only()
async def youtube_remove(interaction: discord.Interaction, channel: str):
    """Удаляет YouTube-канал из списка отслеживаемых"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = await handlers.remove_youtube_channel(channel)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="youtube_list", description="Показать список отслеживаемых YouTube-каналов")
@admin_only()
async def youtube_list(interaction: discord.Interaction):
    """Показывает список всех отслеживаемых YouTube-каналов"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        channels = handlers.list_youtube_channels()
        if channels:
            channel_list = "\n".join(f"• {channel}" for channel in channels)
            await interaction.followup.send(f"📺 Отслеживаемые YouTube-каналы:\n{channel_list}", ephemeral=True)
        else:
            await interaction.followup.send("📺 Нет отслеживаемых YouTube-каналов", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="youtube_check", description="Проверить YouTube-канал вручную")
@admin_only()
async def youtube_check(interaction: discord.Interaction, channel: str):
    """Проверяет YouTube-канал и отправляет уведомление если есть новое видео"""
    await ensure_deferred(interaction, ephemeral=True)
    
    try:
        success, message = await handlers.youtube_check_and_notify(bot, NOTIFICATIONS_CHANNEL_ID, channel)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

# =============================================================================
# ЗАПУСК БОТА
# =============================================================================

if __name__ == "__main__":
    try:
        logger.info("🚀 Запуск бота Genesis...")
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")
        traceback.print_exc()

def main():
    """Entry point для setup.py/pyproject console_scripts."""
    try:
        logger.info("🚀 Запуск бота Genesis (entry point)...")
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")
        traceback.print_exc()