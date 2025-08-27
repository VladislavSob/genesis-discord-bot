"""
Модуль обработчиков для бота Genesis
Содержит функции для работы с ролями, форумом, Twitch и YouTube
"""

import discord
import json
import os
import re
import time
import logging
from urllib.parse import urljoin, urlparse
import aiohttp
import asyncio
import traceback
from discord.ext import tasks
from bs4 import BeautifulSoup

# Основной логгер и отдельный для парсинга форума
logger = logging.getLogger("genesis_bot")
forum_logger = logging.getLogger("genesis_bot.forum")
orders_logger = logging.getLogger("genesis_bot.orders")

# =============================================================================
# КОНСТАНТЫ И НАСТРОЙКИ
# =============================================================================

# Файлы для хранения данных
REACTION_ROLES_FILE = "reaction_roles.json"      # Роли для реакций
REACTION_MESSAGE_FILE = "reaction_message.json"  # ID сообщения с ролями
TRACKING_FILE = "channels.json"                  # Отслеживаемые каналы
NOTIFIED_FILE = "notified.json"                  # Уже отправленные уведомления

# URL форума для мониторинга
FORUM_URL = "https://forum.gta5rp.com/threads/sa-gov-postanovlenija-ofisa-generalnogo-prokurora-shtata-san-andreas.3311595"
ORDERS_URL = "https://forum.gta5rp.com/threads/sa-gov-avtorizovannye-ordera-ofisa-generalnogo-prokurora.3311604"
FORUM_BASE = "https://forum.gta5rp.com"

# API ключ для YouTube
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Конфликтующие роли (нельзя иметь одновременно)
CONFLICTING_ROLES = {
    "GOS": ["Crime"],
    "Crime": ["GOS"]
}

# =============================================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ С JSON
# =============================================================================

def load_json(file_path, default_data):
    """Загружает данные из JSON файла или создает новый с данными по умолчанию"""
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return default_data
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(file_path, data):
    """Сохраняет данные в JSON файл"""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_reaction_roles():
    """Загружает роли для реакций из файла"""
    return load_json(REACTION_ROLES_FILE, {})

def load_reaction_message_id():
    """Загружает ID сообщения с ролями из файла"""
    data = load_json(REACTION_MESSAGE_FILE, {})
    return data.get("message_id")

def load_tracking():
    """Загружает список отслеживаемых каналов, убирая дубликаты"""
    data = load_json(TRACKING_FILE, {"twitch": [], "youtube": []})
    data["twitch"] = list(dict.fromkeys([s.lower() for s in data.get("twitch", [])]))
    data["youtube"] = list(dict.fromkeys(data.get("youtube", [])))
    return data

def save_tracking(data):
    """Сохраняет список отслеживаемых каналов"""
    save_json(TRACKING_FILE, data)

def load_notified():
    """Загружает список уже отправленных уведомлений"""
    return load_json(NOTIFIED_FILE, {"twitch": {}, "youtube": {}, "forum": {}})

def save_notified(data):
    """Сохраняет список уже отправленных уведомлений"""
    save_json(NOTIFIED_FILE, data)

# --------------------------
# Reaction roles setup
# --------------------------

def check_role_conflicts(member: discord.Member, new_role_name: str) -> tuple[bool, str]:
    """
    Проверяет конфликты ролей для пользователя.
    Возвращает (можно_выдать_роль, сообщение_об_ошибке).
    """
    try:
        member_role_names = {r.name for r in member.roles}
        
        # Проверяем конфликты для новой роли
        for conflict_name in CONFLICTING_ROLES.get(new_role_name, []):
            if conflict_name in member_role_names:
                return False, f"❌ Нельзя получить роль **{new_role_name}**, так как у вас уже есть роль **{conflict_name}**"
        
        # Проверяем конфликты от существующих ролей
        for existing_role_name in member_role_names:
            if existing_role_name in CONFLICTING_ROLES:
                for conflict_name in CONFLICTING_ROLES[existing_role_name]:
                    if conflict_name == new_role_name:
                        return False, f"❌ Нельзя получить роль **{new_role_name}**, так как у вас уже есть роль **{existing_role_name}**"
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Ошибка при проверке конфликтующих ролей: {e}")
        return True, ""  # В случае ошибки разрешаем действие

async def ensure_roles_message(guild: discord.Guild, channel_id: int):
	roles_data = load_reaction_roles()
	desired_text = "Выберите роль, нажав на соответствующую реакцию:\n" + "\n".join(
		f"{emoji} — {role}" for emoji, role in roles_data.items()
	)

	channel = guild.get_channel(channel_id)
	if channel is None:
		try:
			channel = await guild.fetch_channel(channel_id)
		except Exception:
			return

	if os.path.exists(REACTION_MESSAGE_FILE):
		try:
			with open(REACTION_MESSAGE_FILE, "r", encoding="utf-8") as f:
				msg_id = json.load(f).get("message_id")
			if msg_id:
				msg = await channel.fetch_message(msg_id)
				if msg and msg.content.strip() == desired_text.strip():
					return
				else:
					await msg.edit(content=desired_text)
					try:
						await msg.clear_reactions()
					except Exception:
						pass
					for emoji in roles_data:
						try:
							await msg.add_reaction(emoji)
						except Exception:
							pass
					return
		except Exception:
			pass

	async for m in channel.history(limit=300):
		try:
			if m.content.strip() == desired_text.strip() and (guild.me is None or m.author == guild.me):
				with open(REACTION_MESSAGE_FILE, "w", encoding="utf-8") as f:
					json.dump({"message_id": m.id}, f, ensure_ascii=False, indent=2)
				return
		except Exception:
			continue

	new_msg = await channel.send(desired_text)
	for emoji in roles_data:
		try:
			await new_msg.add_reaction(emoji)
		except Exception:
			pass
	with open(REACTION_MESSAGE_FILE, "w", encoding="utf-8") as f:
		json.dump({"message_id": new_msg.id}, f, ensure_ascii=False, indent=2)

# --------------------------
# Reaction handling
# --------------------------

async def fix_conflicting_roles(guild: discord.Guild) -> tuple[int, list[str]]:
    """
    Проверяет всех участников сервера на наличие конфликтующих ролей.
    Возвращает (количество_нарушений, список_сообщений).
    """
    violation_count = 0
    messages = []
    
    try:
        for member in guild.members:
            if member.bot:
                continue
                
            member_roles = list(member.roles)
            violations = []
            
            # Проверяем каждую роль пользователя на конфликты
            for role in member_roles:
                if role.name in CONFLICTING_ROLES:
                    for conflict_name in CONFLICTING_ROLES[role.name]:
                        conflict_role = discord.utils.get(guild.roles, name=conflict_name)
                        if conflict_role and conflict_role in member_roles:
                            violations.append(f"У пользователя {member.display_name} обнаружены конфликтующие роли: {role.name} и {conflict_name}")
                            violation_count += 1
            
            if violations:
                messages.extend(violations)
                    
    except Exception as e:
        logger.error(f"Ошибка при проверке конфликтующих ролей: {e}")
        messages.append(f"Ошибка при проверке: {e}")
    
    return violation_count, messages
async def handle_reaction_add(payload, bot):
	msg_id = load_reaction_message_id()
	if msg_id is None or payload.message_id != msg_id:
		return

	roles_data = load_reaction_roles()
	guild = bot.get_guild(payload.guild_id)
	if guild is None:
		return

	if payload.member is None or (hasattr(payload.member, "bot") and payload.member.bot):
		try:
			member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
		except Exception:
			return
	else:
		member = payload.member

	emoji = str(payload.emoji)
	role_name = roles_data.get(emoji)
	if role_name:
		role = discord.utils.get(guild.roles, name=role_name)
		if role:
			# Проверяем конфликты ролей
			can_add_role, error_message = check_role_conflicts(member, role_name)
			
			if not can_add_role:
				# Удаляем реакцию пользователя, так как роль не может быть выдана
				try:
					message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
					await message.remove_reaction(payload.emoji, member)
					logger.info(f"Отклонена попытка получения роли {role_name} пользователем {member}: {error_message}")
					
					# Отправляем личное сообщение пользователю
					try:
						await member.send(error_message)
					except discord.Forbidden:
						# Если личные сообщения закрыты, игнорируем
						pass
					except Exception as e:
						logger.error(f"Ошибка при отправке личного сообщения: {e}")
				except Exception as e:
					logger.error(f"Ошибка при удалении реакции: {e}")
				return
			
			try:
				await member.add_roles(role)
				logger.info(f"Выдана роль {role_name} пользователю {member}")
			except Exception as e:
				logger.error(f"Ошибка при выдаче роли: {e}")

async def handle_reaction_remove(payload, bot):
	msg_id = load_reaction_message_id()
	if msg_id is None or payload.message_id != msg_id:
		return

	roles_data = load_reaction_roles()
	guild = bot.get_guild(payload.guild_id)
	if guild is None:
		return

	emoji = str(payload.emoji)
	role_name = roles_data.get(emoji)
	if role_name:
		role = discord.utils.get(guild.roles, name=role_name)
		member = guild.get_member(payload.user_id)
		if role and member:
			try:
				# Просто снимаем роль без дополнительных проверок
				await member.remove_roles(role)
				logger.info(f"Снята роль {role_name} у пользователя {member}")
			except Exception as e:
				logger.error(f"Ошибка при снятии роли: {e}")

# --------------------------
# Forum parsing + notifier (re-send if deleted)
# --------------------------
async def parse_forum():
	timeout = aiohttp.ClientTimeout(total=15)
	headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

	async def fetch_soup(session, url):
		async with session.get(url) as resp:
			if resp.status != 200:
				logger.error(f"Ошибка загрузки форума: {resp.status}")
				return None
			html = await resp.text()
			return BeautifulSoup(html, "html.parser")

	async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
		forum_logger.debug("�� Проверяем форум: %s", FORUM_URL)
		soup = await fetch_soup(session, FORUM_URL)
		if soup is None:
			logger.error("❌ Не удалось загрузить страницу форума")
			return None

		last_page_href = None
		nav = soup.select_one("nav.pageNav") or soup
		for a in nav.select("a[href*='page-']"):
			m = re.search(r"page-(\d+)", a.get("href", ""))
			if m:
				last_page_href = a["href"]

		thread_page_url = FORUM_URL
		if last_page_href:
			thread_page_url = urljoin(FORUM_BASE, last_page_href)
			forum_logger.debug("📄 Переходим на последнюю страницу: %s", thread_page_url)
			soup = await fetch_soup(session, thread_page_url)
			if soup is None:
				return None

		posts = soup.select("article.message")
		if not posts:
			logger.error("❌ Не найдено сообщений на странице")
			return None

		last_post = posts[-1]
		forum_logger.debug("📝 Найдено сообщений: %d", len(posts))

		post_id = None
		for attr_name in ("id", "data-content"):
			attr_val = last_post.get(attr_name) or ""
			m = re.search(r"post-(\d+)", attr_val)
			if m:
				post_id = m.group(1)
				break
		if not post_id:
			link = last_post.select_one("a[href*='#post-']")
			if link and link.has_attr("href"):
				m = re.search(r"#post-(\d+)", link["href"])
				if m:
					post_id = m.group(1)

		url = thread_page_url
		if post_id:
			url = f"{thread_page_url}#post-{post_id}"

		body = last_post.select_one(".message-content .bbWrapper") or last_post.select_one(".bbWrapper")
		if body:
			text = body.get_text("\n", strip=True)
		else:
			text = last_post.get_text(" ", strip=True)

		text = re.sub(r"\s+\n", "\n", text)
		text = re.sub(r"\n{3,}", "\n\n", text)

		overhead = len("Новый пост на форуме:\n") + len(url) + 2
		max_len = max(0, 2000 - overhead)
		if len(text) > max_len:
			text = (text[: max(0, max_len - 3)] + "...") if max_len >= 3 else text[:max_len]

		result = {"text": text, "url": url, "post_id": post_id or url}
		forum_logger.debug("✅ Получен пост ID: %s, URL: %s", post_id, url)
		return result

async def parse_orders():
	timeout = aiohttp.ClientTimeout(total=15)
	headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

	async def fetch_soup(session, url):
		async with session.get(url) as resp:
			if resp.status != 200:
				logger.error(f"Ошибка загрузки ордеров: {resp.status}")
				return None
			html = await resp.text()
			return BeautifulSoup(html, "html.parser")

	async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
		orders_logger.debug("🔍 Проверяем ордера: %s", ORDERS_URL)
		soup = await fetch_soup(session, ORDERS_URL)
		if soup is None:
			logger.error("❌ Не удалось загрузить страницу ордеров")
			return None

		last_page_href = None
		nav = soup.select_one("nav.pageNav") or soup
		for a in nav.select("a[href*='page-']"):
			m = re.search(r"page-(\d+)", a.get("href", ""))
			if m:
				last_page_href = a["href"]

		thread_page_url = ORDERS_URL
		if last_page_href:
			thread_page_url = urljoin(FORUM_BASE, last_page_href)
			orders_logger.debug("📄 Переходим на последнюю страницу: %s", thread_page_url)
			soup = await fetch_soup(session, thread_page_url)
			if soup is None:
				return None

		posts = soup.select("article.message")
		if not posts:
			logger.error("❌ Не найдено сообщений на странице ордеров")
			return None

		last_post = posts[-1]
		orders_logger.debug("📝 Найдено сообщений: %d", len(posts))

		post_id = None
		for attr_name in ("id", "data-content"):
			attr_val = last_post.get(attr_name) or ""
			m = re.search(r"post-(\d+)", attr_val)
			if m:
				post_id = m.group(1)
				break
		if not post_id:
			link = last_post.select_one("a[href*='#post-']")
			if link and link.has_attr("href"):
				m = re.search(r"#post-(\d+)", link["href"])
				if m:
					post_id = m.group(1)

		url = thread_page_url
		if post_id:
			url = f"{thread_page_url}#post-{post_id}"

		body = last_post.select_one(".message-content .bbWrapper") or last_post.select_one(".bbWrapper")
		if body:
			text = body.get_text("\n", strip=True)
		else:
			text = last_post.get_text(" ", strip=True)

		text = re.sub(r"\s+\n", "\n", text)
		text = re.sub(r"\n{3,}", "\n\n", text)

		overhead = len("Новый ордер:\n") + len(url) + 2
		max_len = max(0, 2000 - overhead)
		if len(text) > max_len:
			text = (text[: max(0, max_len - 3)] + "...") if max_len >= 3 else text[:max_len]

		result = {"text": text, "url": url, "post_id": post_id or url}
		orders_logger.debug("✅ Получен ордер ID: %s, URL: %s", post_id, url)
		return result

async def _forum_message_exists(channel: discord.TextChannel, url: str, text: str) -> bool:
	async for m in channel.history(limit=200):
		if m.author.bot and url in (m.content or ""):
			return True
	return False

@tasks.loop(minutes=5)
async def check_forum(bot, forum_channel_id: int):
	try:
		forum_logger.debug("🔄 Проверка форума (канал: %s)", forum_channel_id)
		post = await parse_forum()
		if not post:
			logger.error("❌ Не удалось получить пост с форума")
			return

		channel = bot.get_channel(forum_channel_id)
		if channel is None:
			logger.error(f"❌ Канал {forum_channel_id} не найден")
			return

		exists = await _forum_message_exists(channel, post["url"], post["text"])

		notified = load_notified()
		forum_state = notified.get("forum", {})
		last_post_id = forum_state.get("last_post_id")

		forum_logger.debug("📊 Текущий ID поста: %s, Последний известный: %s", post['post_id'], last_post_id)

		if not exists and last_post_id != post["post_id"]:
			logger.info(f"📢 Отправляем уведомление о новом посте: {post['post_id']}")
			await channel.send(f"Новый пост на форуме:\n{post['url']}\n\n{post['text']}")
			forum_state["last_post_id"] = post["post_id"]
			notified["forum"] = forum_state
			save_notified(notified)
			logger.info("✅ Уведомление отправлено и сохранено")
			return
		elif exists:
			forum_logger.debug("ℹ️ Пост уже был отправлен ранее")
		elif last_post_id == post["post_id"]:
			forum_logger.debug("ℹ️ Пост не изменился")

		if last_post_id != post["post_id"]:
			forum_state["last_post_id"] = post["post_id"]
			notified["forum"] = forum_state
			save_notified(notified)
			forum_logger.debug("📝 Обновлен ID последнего поста")
	except Exception as e:
		logger.error(f"❌ Ошибка при проверке форума: {e}")
		traceback.print_exc()

@tasks.loop(minutes=5)
async def check_orders(bot, orders_channel_id: int):
	try:
		orders_logger.debug("🔄 Проверка ордеров (канал: %s)", orders_channel_id)
		order = await parse_orders()
		if not order:
			logger.error("❌ Не удалось получить ордер")
			return

		channel = bot.get_channel(orders_channel_id)
		if channel is None:
			logger.error(f"❌ Канал {orders_channel_id} не найден")
			return

		exists = await _forum_message_exists(channel, order["url"], order["text"])

		notified = load_notified()
		orders_state = notified.get("orders", {})
		last_order_id = orders_state.get("last_order_id")

		orders_logger.debug("📊 Текущий ID ордера: %s, Последний известный: %s", order['post_id'], last_order_id)

		if not exists and last_order_id != order["post_id"]:
			logger.info(f"📢 Отправляем уведомление о новом ордере: {order['post_id']}")
			await channel.send(f"Новый ордер:\n{order['url']}\n\n{order['text']}")
			orders_state["last_order_id"] = order["post_id"]
			notified["orders"] = orders_state
			save_notified(notified)
			logger.info("✅ Уведомление об ордере отправлено и сохранено")
			return
		elif exists:
			orders_logger.debug("ℹ️ Ордер уже был отправлен ранее")
		elif last_order_id == order["post_id"]:
			orders_logger.debug("ℹ️ Ордер не изменился")

		if last_order_id != order["post_id"]:
			orders_state["last_order_id"] = order["post_id"]
			notified["orders"] = orders_state
			save_notified(notified)
			orders_logger.debug("📝 Обновлен ID последнего ордера")
	except Exception as e:
		logger.error(f"❌ Ошибка при проверке ордеров: {e}")
		traceback.print_exc()

async def diagnose_forum(bot, forum_channel_id: int):
	"""Диагностика состояния форума"""
	try:
		logger.info("🔍 Диагностика форума...")
		
		# Проверяем канал
		channel = bot.get_channel(forum_channel_id)
		if channel is None:
			return "❌ Канал форума не найден"
		
		# Проверяем права бота
		permissions = channel.permissions_for(bot.user)
		if not permissions.send_messages:
			return "❌ Бот не может отправлять сообщения в канал"
		
		# Получаем текущий пост
		post = await parse_forum()
		if not post:
			return "❌ Не удалось получить данные с форума"
		
		# Проверяем состояние уведомлений
		notified = load_notified()
		forum_state = notified.get("forum", {})
		last_post_id = forum_state.get("last_post_id")
		
		# Проверяем, существует ли уже сообщение
		exists = await _forum_message_exists(channel, post["url"], post["text"])
		
		result = f"✅ Диагностика завершена:\n"
		result += f"📝 Текущий пост ID: {post['post_id']}\n"
		result += f"📝 Последний известный ID: {last_post_id}\n"
		result += f"📢 Сообщение уже отправлено: {'Да' if exists else 'Нет'}\n"
		result += f"🔗 URL: {post['url']}\n"
		result += f"📄 Текст: {post['text'][:100]}..."
		
		return result
		
	except Exception as e:
		return f"❌ Ошибка диагностики: {e}"

async def diagnose_orders(bot, orders_channel_id: int):
	"""Диагностика состояния ордеров"""
	try:
		# Проверяем канал
		channel = bot.get_channel(orders_channel_id)
		if channel is None:
			return "❌ Канал ордеров не найден"
		
		channel_status = "✅ Доступен"
		
		# Проверяем последний ордер
		notified = load_notified()
		orders_state = notified.get("orders", {})
		last_order_id = orders_state.get("last_order_id")
		
		# Пытаемся получить текущий ордер
		try:
			order = await parse_orders()
			if order:
				current_id = order.get("post_id", "неизвестен")
				if last_order_id == current_id:
					status_msg = "✅ Актуален"
				else:
					status_msg = f"⚠️ Обновление доступно (текущий: {current_id})"
			else:
				status_msg = "❌ Ошибка получения"
		except Exception as e:
			status_msg = f"❌ Ошибка: {e}"
		
		return f"Ордера: {status_msg} | Последний ордер: {last_order_id or 'неизвестен'} | Канал: {channel_status}"
	except Exception as e:
		return f"❌ Ошибка диагностики: {e}"

# --------------------------
# Twitch tracking (2 минуты) + token refresh
# --------------------------
_twitch_access_token = None
_twitch_token_expires_at = 0.0

async def _refresh_twitch_token(session: aiohttp.ClientSession) -> bool:
	global _twitch_access_token, _twitch_token_expires_at
	client_id = os.getenv("TWITCH_CLIENT_ID")
	client_secret = os.getenv("TWITCH_CLIENT_SECRET") or os.getenv("TWITCH_TOKEN")
	if not client_id or not client_secret:
		logger.warning("Twitch: не задан TWITCH_CLIENT_ID или TWITCH_CLIENT_SECRET")
		return False
	data = {"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"}
	async with session.post("https://id.twitch.tv/oauth2/token", data=data) as resp:
		js = await resp.json()
		if resp.status != 200:
			logger.error(f"Twitch token error {resp.status}: {js}")
			return False
		_twitch_access_token = js.get("access_token")
		expires_in = js.get("expires_in", 3600)
		_twitch_token_expires_at = time.time() + max(60, int(expires_in) - 60)
		return True

async def _twitch_headers(session: aiohttp.ClientSession):
	global _twitch_access_token, _twitch_token_expires_at
	if _twitch_access_token is None or time.time() >= _twitch_token_expires_at:
		ok = await _refresh_twitch_token(session)
		if not ok:
			return None
	client_id = os.getenv("TWITCH_CLIENT_ID")
	return {"Client-ID": client_id, "Authorization": f"Bearer {_twitch_access_token}"}

async def _fetch_twitch_streams(session: aiohttp.ClientSession, logins):
	headers = await _twitch_headers(session)
	if not headers:
		return []
	streams = []
	for i in range(0, len(logins), 100):
		chunk = logins[i:i+100]
		params = "&".join(f"user_login={login}" for login in chunk)
		url = f"https://api.twitch.tv/helix/streams?{params}"
		async def do_request(hdrs):
			async with session.get(url, headers=hdrs) as resp:
				if resp.status == 401:
					return {"unauthorized": True}
				if resp.status != 200:
					return None
				return await resp.json()
		data = await do_request(headers)
		if data == {"unauthorized": True}:
			if await _refresh_twitch_token(session):
				headers = await _twitch_headers(session)
				data = await do_request(headers)
			else:
				data = None
		if data and "data" in data:
			streams.extend(data["data"])
	return streams

def _missing_send_perms(channel) -> list[str]:
	try:
		guild = getattr(channel, "guild", None)
		if guild is None:
			return ["View Channel", "Send Messages"]
		me = guild.me
		perms = channel.permissions_for(me)  # type: ignore[attr-defined]
		missing = []
		if not perms.view_channel:
			missing.append("View Channel")
		if not perms.send_messages:
			missing.append("Send Messages")
		if not perms.embed_links:
			missing.append("Embed Links")
		return missing
	except Exception:
		return ["unknown"]

@tasks.loop(seconds=120)  # Изменено с 10 секунд на 2 минуты
async def poll_twitch(bot, notifications_channel_id: int):
	try:
		tracking = load_tracking()
		logins = tracking.get("twitch", [])
		if not logins:
			return

		timeout = aiohttp.ClientTimeout(total=8)
		async with aiohttp.ClientSession(timeout=timeout) as session:
			live_streams = await _fetch_twitch_streams(session, logins)

		channel = bot.get_channel(notifications_channel_id)
		if channel is None:
			return

		missing = _missing_send_perms(channel)
		if missing:
			logger.warning(f"Twitch: нет прав в канале уведомлений ({notifications_channel_id}): {', '.join(missing)}")
			return

		notified = load_notified()
		notified_twitch = notified.get("twitch", {})

		for stream in live_streams:
			login = (stream.get("user_login") or "").lower()
			stream_id = stream.get("id")
			title = stream.get("title", "")
			if not login or not stream_id:
				continue
			if notified_twitch.get(login) == stream_id:
				continue
			notified_twitch[login] = stream_id
			url = f"https://twitch.tv/{login}"
			try:
				await channel.send(f"В эфире на Twitch: {url}\n{title[:1900]}")
			except Exception as e:
				logger.error(f"Ошибка отправки сообщения Twitch: {e}")

		notified["twitch"] = notified_twitch
		save_notified(notified)
	except Exception as e:
		logger.error(f"Twitch loop error: {e}")

async def twitch_check_and_notify(bot: discord.Client, notifications_channel_id: int, login: str):
	login_norm = login.strip().lower()
	timeout = aiohttp.ClientTimeout(total=8)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		streams = await _fetch_twitch_streams(session, [login_norm])
	if not streams:
		return True, f"{login_norm}: офлайн или не найден."

	stream = streams[0]
	stream_id = stream.get("id")
	title = stream.get("title", "")
	url = f"https://twitch.tv/{login_norm}"

	channel = bot.get_channel(notifications_channel_id)
	if channel is None:
		return False, f"Не найден канал уведомлений {notifications_channel_id}."

	missing = _missing_send_perms(channel)
	if missing:
		return False, f"Недостаточно прав в канале уведомлений: {', '.join(missing)}"

	notified = load_notified()
	notified_twitch = notified.get("twitch", {})
	if notified_twitch.get(login_norm) == stream_id:
		return True, f"{login_norm}: уже уведомлено для текущего эфира ({stream_id})."

	notified_twitch[login_norm] = stream_id
	notified["twitch"] = notified_twitch
	save_notified(notified)

	try:
		await channel.send(f"В эфире на Twitch: {url}\n{title[:1900]}")
		return True, f"{login_norm}: live, отправлено уведомление."
	except Exception as e:
		logger.error(f"Ошибка отправки уведомления Twitch: {e}")
		return False, f"{login_norm}: ошибка отправки уведомления."

# --------------------------
# YouTube tracking (2 минуты), поддержка @handle/URL/UC
# --------------------------
def _extract_channel_id_from_url(url: str) -> str | None:
	try:
		parsed = urlparse(url)
		parts = [p for p in parsed.path.split("/") if p]
		for i, p in enumerate(parts):
			if p == "channel" and i + 1 < len(parts) and re.fullmatch(r"UC[0-9A-Za-z_-]{21,}", parts[i+1]):
				return parts[i+1]
		for p in parts:
			if p.startswith("@"):
				return p
	except Exception:
		return None
	return None

async def _resolve_youtube_channel_id(session: aiohttp.ClientSession, input_str: str) -> str | None:
	s = input_str.strip()
	if re.fullmatch(r"UC[0-9A-Za-z_-]{21,}", s):
		return s
	if s.startswith("http://") or s.startswith("https://"):
		extracted = _extract_channel_id_from_url(s)
		if extracted and extracted.startswith("UC"):
			return extracted
		if extracted and extracted.startswith("@"):
			s = extracted
	handle = s if s.startswith("@") else "@" + s
	if not YOUTUBE_API_KEY:
		return None
	params = {"part": "id", "forHandle": handle, "key": YOUTUBE_API_KEY}
	async with session.get("https://www.googleapis.com/youtube/v3/channels", params=params) as resp:
		data = await resp.json()
		if resp.status == 200 and data.get("items"):
			cid = data["items"][0].get("id")
			if isinstance(cid, str) and cid.startswith("UC"):
				return cid
	params = {"part": "snippet", "type": "channel", "q": handle.lstrip("@"), "maxResults": "1", "key": YOUTUBE_API_KEY}
	async with session.get("https://www.googleapis.com/youtube/v3/search", params=params) as resp:
		data = await resp.json()
		items = data.get("items", [])
		if resp.status == 200 and items:
			cid = (items[0].get("id") or {}).get("channelId")
			if cid and cid.startswith("UC"):
				return cid
	return None

async def _youtube_latest_video(session: aiohttp.ClientSession, channel_id: str):
	if not YOUTUBE_API_KEY:
		return None
	params = {"key": YOUTUBE_API_KEY, "channelId": channel_id, "part": "snippet", "order": "date", "maxResults": "1", "type": "video", "safeSearch": "none"}
	async with session.get("https://www.googleapis.com/youtube/v3/search", params=params) as resp:
		if resp.status != 200:
			return None
		data = await resp.json()
		items = data.get("items", [])
		if not items:
			return None
		it = items[0]
		vid = (it.get("id") or {}).get("videoId")
		title = (it.get("snippet") or {}).get("title", "")
		if not vid:
			return None
		return {"video_id": vid, "title": title}

@tasks.loop(seconds=120)  # Изменено с 10 секунд на 2 минуты
async def poll_youtube(bot, notifications_channel_id: int):
	try:
		if not YOUTUBE_API_KEY:
			return
		tracking = load_tracking()
		channels = tracking.get("youtube", [])
		if not channels:
			return

		timeout = aiohttp.ClientTimeout(total=8)
		async with aiohttp.ClientSession(timeout=timeout) as session:
			notified = load_notified()
			notified_youtube = notified.get("youtube", {})
			channel = bot.get_channel(notifications_channel_id)
			if channel is None:
				return

			missing = _missing_send_perms(channel)
			if missing:
				return

			for channel_id in channels:
				latest = await _youtube_latest_video(session, channel_id)
				if not latest:
					continue
				vid = latest["video_id"]
				title = latest.get("title", "")
				last_vid = notified_youtube.get(channel_id)
				if last_vid != vid:
					notified_youtube[channel_id] = vid
					url = f"https://youtu.be/{vid}"
					try:
						await channel.send(f"Новое видео на YouTube: {url}\n{title[:1900]}")
					except Exception as e:
						logger.error(f"Ошибка отправки сообщения YouTube: {e}")

			notified["youtube"] = notified_youtube
			save_notified(notified)
	except Exception as e:
		logger.error(f"YouTube loop error: {e}")

async def youtube_check_and_notify(bot: discord.Client, notifications_channel_id: int, channel_input: str):
	timeout = aiohttp.ClientTimeout(total=8)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		cid = await _resolve_youtube_channel_id(session, channel_input)
		if not cid:
			return False, "Не удалось определить channelId. Укажите @handle или ссылку вида https://www.youtube.com/@handle"
		latest = await _youtube_latest_video(session, cid)

	if not latest:
		return True, f"{cid}: новых видео не найдено."

	channel = bot.get_channel(notifications_channel_id)
	if channel is None:
		return False, f"Не найден канал уведомлений {notifications_channel_id}."

	missing = _missing_send_perms(channel)
	if missing:
		return False, f"Недостаточно прав в канале уведомлений: {', '.join(missing)}"

	notified = load_notified()
	notified_youtube = notified.get("youtube", {})
	if notified_youtube.get(cid) == latest["video_id"]:
		return True, f"{cid}: уже уведомлено об этом видео ({latest['video_id']})."

	notified_youtube[cid] = latest["video_id"]
	notified["youtube"] = notified_youtube
	save_notified(notified)

	url = f"https://youtu.be/{latest['video_id']}"
	title = latest.get("title", "")[:1900]
	try:
		await channel.send(f"Новое видео на YouTube: {url}\n{title}")
		return True, f"{cid}: найдено новое видео, уведомление отправлено."
	except Exception as e:
		logger.error(f"Ошибка отправки уведомления YouTube: {e}")
		return False, f"{cid}: ошибка отправки уведомления."

def start_tracking_tasks(bot: discord.Client, notifications_channel_id: int):
	if not poll_twitch.is_running():
		poll_twitch.start(bot, notifications_channel_id)
	if not poll_youtube.is_running():
		poll_youtube.start(bot, notifications_channel_id)

# --------------------------
# Manage tracking lists
# --------------------------
def add_twitch_channel(login: str):
	login_norm = login.strip().lower()
	if not re.fullmatch(r"[a-z0-9_]{3,25}", login_norm):
		return False, "Некорректный Twitch-логин."
	data = load_tracking()
	if login_norm in data["twitch"]:
		return False, "Такой Twitch-канал уже добавлен."
	data["twitch"].append(login_norm)
	save_tracking(data)
	return True, f"Twitch-канал добавлен: {login_norm}"

def remove_twitch_channel(login: str):
	login_norm = login.strip().lower()
	data = load_tracking()
	if login_norm not in data["twitch"]:
		return False, "Такого Twitch-канала нет в списке."
	data["twitch"] = [l for l in data["twitch"] if l != login_norm]
	save_tracking(data)
	notified = load_notified()
	notified.get("twitch", {}).pop(login_norm, None)
	save_notified(notified)
	return True, f"Twitch-канал удалён: {login_norm}"

def list_twitch_channels():
	return load_tracking().get("twitch", [])

async def add_youtube_channel(channel: str):
	timeout = aiohttp.ClientTimeout(total=8)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		cid = await _resolve_youtube_channel_id(session, channel)
	if not cid:
		return False, "Укажите @handle или ссылку вида https://www.youtube.com/@handle"
	data = load_tracking()
	if cid in data["youtube"]:
		return False, "Канал уже добавлен."
	data["youtube"].append(cid)
	save_tracking(data)
	return True, f"YouTube-канал добавлен: {cid}"

async def remove_youtube_channel(channel: str):
	timeout = aiohttp.ClientTimeout(total=8)
	cid = None
	try:
		async with aiohttp.ClientSession(timeout=timeout) as session:
			cid = await _resolve_youtube_channel_id(session, channel)
	except Exception:
		cid = None
	data = load_tracking()
	target = cid or channel.strip()
	if target in data["youtube"]:
		data["youtube"] = [c for c in data["youtube"] if c != target]
		save_tracking(data)
		notified = load_notified()
		notified.get("youtube", {}).pop(target, None)
		save_notified(notified)
		return True, f"YouTube-канал удалён: {target}"
	return False, "Такого YouTube-канала нет в списке."

def list_youtube_channels():
	return load_tracking().get("youtube", [])