import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# Загружаем переменные окружения ДО импорта handlers
load_dotenv(override=True)

import discord
from discord.ext import commands
from discord import app_commands
import handlers
import traceback

# =============================================================================
# НАСТРОЙКА ЛОГГИРОВАНИЯ
# =============================================================================

# Создаем папку для логов если её нет
os.makedirs("logs", exist_ok=True)

# Настраиваем логгер
logger = logging.getLogger("genesis_bot")
logger.setLevel(logging.DEBUG)

# Форматтер для логов
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Хендлер для файла (ротация по размеру)
file_handler = RotatingFileHandler(
    "logs/genesis.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding="utf-8"
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

# Настраиваем логгер discord.py (убираем спам)
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.WARNING)

# =============================================================================
# КОНФИГУРАЦИЯ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# =============================================================================

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_STR = os.getenv("GUILD_ID")
ROLES_CHANNEL_ID_STR = os.getenv("ROLES_CHANNEL_ID")
FORUM_CHANNEL_ID_STR = os.getenv("FORUM_CHANNEL_ID")
NOTIFICATIONS_CHANNEL_ID_STR = os.getenv("NOTIFICATIONS_CHANNEL_ID")

# Проверяем наличие всех необходимых переменных окружения
if not TOKEN or not GUILD_ID_STR or not ROLES_CHANNEL_ID_STR or not FORUM_CHANNEL_ID_STR or not NOTIFICATIONS_CHANNEL_ID_STR:
    logger.error("❌ Ошибка: Заполните все необходимые переменные в .env файле:")
    logger.error("   - DISCORD_TOKEN")
    logger.error("   - GUILD_ID") 
    logger.error("   - ROLES_CHANNEL_ID")
    logger.error("   - FORUM_CHANNEL_ID")
    logger.error("   - NOTIFICATIONS_CHANNEL_ID")
    raise SystemExit(1)

# Конвертируем строковые ID в целые числа
GUILD_ID = int(GUILD_ID_STR)
ROLES_CHANNEL_ID = int(ROLES_CHANNEL_ID_STR)
FORUM_CHANNEL_ID = int(FORUM_CHANNEL_ID_STR)
NOTIFICATIONS_CHANNEL_ID = int(NOTIFICATIONS_CHANNEL_ID_STR)

# =============================================================================
# НАСТРОЙКА INTENTS
# =============================================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

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
    
    async def setup_hook(self) -> None:
        """Инициализация бота при запуске"""
        try:
            # Регистрируем команды глобально и копируем их в нужную гильдию
            await self.tree.sync()
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            logger.info("✅ Слэш-команды успешно синхронизированы")
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации команд: {e}")
            traceback.print_exc()

# Создаем экземпляр бота
bot = GenesisBot(command_prefix="!", intents=intents)

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

async def _log_channel_perms(bot_client: discord.Client, channel_id: int, label: str):
    """Логирует права бота в указанном канале"""
    try:
        channel = bot_client.get_channel(channel_id)
        if channel is None:
            logger.warning(f"⚠️  {label}: Канал {channel_id} не найден")
            return
        
        # Проверяем, что канал имеет guild (серверный канал)
        if not hasattr(channel, 'guild') or channel.guild is None:
            logger.warning(f"⚠️  {label}: Канал {channel_id} не является серверным каналом")
            return
            
        # Получаем права бота в канале
        permissions = channel.permissions_for(channel.guild.me)
        if permissions.send_messages and permissions.view_channel:
            logger.info(f"✅ {label}: Права в порядке")
        else:
            missing_perms = []
            if not permissions.view_channel:
                missing_perms.append("View Channel")
            if not permissions.send_messages:
                missing_perms.append("Send Messages")
            logger.warning(f"⚠️  {label}: Недостаточно прав. Дайте роли бота View Channel и Send Messages в этом канале.")
    except Exception as e:
        logger.error(f"❌ {label}: Ошибка проверки прав: {e}")

# =============================================================================
# СОБЫТИЯ БОТА
# =============================================================================

@bot.event
async def on_ready():
    """Событие запуска бота"""
    logger.info(f"🤖 Бот {bot.user} успешно запущен!")
    logger.info(f"🆔 ID бота: {bot.user.id}")
    logger.info(f"🏠 Сервер: {bot.get_guild(GUILD_ID).name if bot.get_guild(GUILD_ID) else 'Не найден'}")

    # Диагностика прав в каналах
    logger.info("🔍 Проверка прав доступа к каналам:")
    await _log_channel_perms(bot, NOTIFICATIONS_CHANNEL_ID, "Notifications")
    await _log_channel_perms(bot, FORUM_CHANNEL_ID, "Forum")

    # Получаем объект гильдии
    guild = bot.get_guild(GUILD_ID) or await bot.fetch_guild(GUILD_ID)

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
    await interaction.response.defer(ephemeral=True)
    
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

# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С ФОРУМОМ
# =============================================================================

@bot.tree.command(name="force_forum_check", description="Проверить форум вручную")
@admin_only()
async def force_forum_check(interaction: discord.Interaction):
    """Принудительно проверяет форум и показывает последний пост"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        post = await handlers.parse_forum()
        if post and post.get("text"):
            await interaction.followup.send(
                f"📋 Последний пост на форуме:\n{post['url']}\n\n{post['text']}", 
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
    await interaction.response.defer(ephemeral=True)
    
    try:
        result = await handlers.diagnose_forum(bot, FORUM_CHANNEL_ID)
        await interaction.followup.send(f"🔍 {result}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка диагностики: {e}", ephemeral=True)

# =============================================================================
# КОМАНДЫ ДЛЯ РАБОТЫ С TWITCH
# =============================================================================

@bot.tree.command(name="twitch_add", description="Добавить Twitch-канал для отслеживания")
@admin_only()
async def twitch_add(interaction: discord.Interaction, login: str):
    """Добавляет Twitch-канал в список отслеживаемых"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        success, message = handlers.add_twitch_channel(login)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="twitch_remove", description="Удалить Twitch-канал из отслеживания")
@admin_only()
async def twitch_remove(interaction: discord.Interaction, login: str):
    """Удаляет Twitch-канал из списка отслеживаемых"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        success, message = handlers.remove_twitch_channel(login)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="twitch_list", description="Показать список отслеживаемых Twitch-каналов")
@admin_only()
async def twitch_list(interaction: discord.Interaction):
    """Показывает список всех отслеживаемых Twitch-каналов"""
    await interaction.response.defer(ephemeral=True)
    
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
    await interaction.response.defer(ephemeral=True)
    
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
    await interaction.response.defer(ephemeral=True)
    
    try:
        success, message = await handlers.add_youtube_channel(channel)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="youtube_remove", description="Удалить YouTube-канал из отслеживания")
@admin_only()
async def youtube_remove(interaction: discord.Interaction, channel: str):
    """Удаляет YouTube-канал из списка отслеживаемых"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        success, message = await handlers.remove_youtube_channel(channel)
        await interaction.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="youtube_list", description="Показать список отслеживаемых YouTube-каналов")
@admin_only()
async def youtube_list(interaction: discord.Interaction):
    """Показывает список всех отслеживаемых YouTube-каналов"""
    await interaction.response.defer(ephemeral=True)
    
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
    await interaction.response.defer(ephemeral=True)
    
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