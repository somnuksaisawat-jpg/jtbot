import asyncio
import logging
import datetime
import re
import random
from pyrogram import Client, filters, idle
from pyrogram.handlers import MessageHandler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from core.database import db
from core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - Worker - %(levelname)s - %(message)s")
logger = logging.getLogger("Worker")

# 缓存结构
KEYWORDS_CACHE = {} 
ADS_CACHE = []
FILTER_CACHE = {} 

bot = Bot(token=settings.BOT_TOKEN)

# AI 评分逻辑 (保留不变)
def is_spam_ai(text: str) -> bool:
    score = 0
    emoji_count = len(re.findall(r'[\U0001f600-\U0001f64f]', text))
    if emoji_count > 5: score += 30
    if emoji_count > 10: score += 50
    spam_words = ["博彩", "首存", "网址", "点击链接", "刷单", "兼职", "AV", "裸聊"]
    for w in spam_words:
        if w in text: score += 40
    links = text.count("http") + text.count("t.me")
    if links > 3: score += 40
    return score >= 60

async def load_settings():
    """加载配置 (保留不变)"""
    global KEYWORDS_CACHE, ADS_CACHE, FILTER_CACHE
    if not db.pg_pool: await db.connect()
    
    async with db.pg_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT k.word, u.tg_id, u.is_paused, u.notify_simple_mode, u.notify_target_id,
                   u.fuzzy_limit, u.ai_filter_enabled
            FROM keywords k
            JOIN users u ON k.user_id = u.id
            WHERE u.is_banned = FALSE AND (u.expire_at IS NULL OR u.expire_at > NOW())
        """)
        
        new_kw = {}
        for r in rows:
            word = r['word']
            user_config = {
                'uid': r['tg_id'],
                'paused': r['is_paused'],
                'simple': r['notify_simple_mode'],
                'target': r['notify_target_id'],
                'limit': r['fuzzy_limit'],
                'ai': r['ai_filter_enabled']
            }
            if word not in new_kw: new_kw[word] = []
            exists = False
            for u in new_kw[word]:
                if u['uid'] == user_config['uid']:
                    exists = True
                    break
            if not exists:
                new_kw[word].append(user_config)
        KEYWORDS_CACHE = new_kw
        
        f_rows = await conn.fetch("SELECT u.tg_id, f.word FROM filter_words f JOIN users u ON f.user_id = u.id")
        new_filter = {}
        for r in f_rows:
            uid = r['tg_id']
            if uid not in new_filter: new_filter[uid] = []
            new_filter[uid].append(r['word'])
        FILTER_CACHE = new_filter
        
        ads = await conn.fetch("SELECT key, value FROM system_settings WHERE key LIKE 'btn_ad_%' ORDER BY description::int")
        new_ads = []
        row_btns = []
        for r in ads:
            text = r['key'].split('_', 3)[3]
            row_btns.append(InlineKeyboardButton(text=text, url=r['value']))
            if len(row_btns) == 2:
                new_ads.append(row_btns)
                row_btns = []
        if row_btns: new_ads.append(row_btns)
        ADS_CACHE = new_ads
        
    logger.info(f"♻️ 配置刷新: {len(KEYWORDS_CACHE)} 关键词")

async def get_user_history(user_id, chat_id, current_keyword):
    if not user_id: return "无"
    async with db.pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT keyword, msg_link FROM message_history WHERE user_id = $1 ORDER BY id DESC LIMIT 5", user_id)
    if not rows: return "无"
    links = []
    seen = set()
    for r in rows:
        if r['keyword'] == current_keyword or r['keyword'] in seen: continue
        seen.add(r['keyword'])
        links.append(f"<a href='{r['msg_link']}'>{r['keyword']}</a>")
    return "、".join(links) if links else "无"

async def save_history(user_id, chat_id, keyword, msg_link):
    if not user_id: return
    async with db.pg_pool.acquire() as conn:
        await conn.execute("INSERT INTO message_history (user_id, chat_id, keyword, msg_link) VALUES ($1, $2, $3, $4)", user_id, chat_id, keyword, msg_link)

# 🟢 [新增] 执行私信任务函数
async def perform_dm_task(session_str, target_username, text, owner_db_id):
    """启动一次性客户端发送私信"""
    client = None
    try:
        # 使用随机名称防止冲突
        client = Client(
            name=f"dm_worker_{random.randint(10000,99999)}", 
            api_id=settings.API_ID, 
            api_hash=settings.API_HASH, 
            session_string=session_str, 
            in_memory=True,
            no_updates=True # 不接收更新，只发送
        )
        await client.start()
        
        # 发送
        await client.send_message(target_username, text)
        
        # 记录日志/扣费 (简单实现)
        if db.pg_pool:
            async with db.pg_pool.acquire() as conn:
                await conn.execute("UPDATE dm_accounts SET daily_sent = daily_sent + 1 WHERE session_string = $1", session_str)
                # 扣除积分逻辑可在此添加
        
        logger.info(f"✈️ [AutoDM] 已发送私信给 @{target_username}")
        
    except Exception as e:
        logger.error(f"❌ [AutoDM] 发送失败: {e}")
    finally:
        if client: 
            try: await client.stop()
            except: pass

async def handle_new_message(client: Client, message):
    try:
        content = message.text or message.caption
        if not content: return

        matched_configs = [] 
        hit_word = ""
        
        for kw, users in KEYWORDS_CACHE.items():
            if kw in content:
                matched_configs = users
                hit_word = kw
                break 
        
        if not matched_configs: return

        chat = message.chat
        sender = message.from_user
        source_title = chat.title or "私聊"
        msg_link = message.link if chat.username else "私有群/无链接"
        user_name = sender.first_name if sender else "未知"
        if sender and sender.last_name: user_name += f" {sender.last_name}"
        user_id = sender.id if sender else 0
        user_username = f"@{sender.username}" if sender and sender.username else "无"
        target_username = sender.username # 用于私信
        
        history_tags = await get_user_history(user_id, chat.id, hit_word)
        asyncio.create_task(save_history(user_id, chat.id, hit_word, msg_link))
        
        utc_now = datetime.datetime.utcnow()
        bj_time = utc_now + datetime.timedelta(hours=8)
        now_str = bj_time.strftime("%Y-%m-%d %H:%M:%S")
        
        text = (
            f"<b>监听关键词</b>\n"
            f"🎯 <b>命中关键词：</b>#{hit_word}\n\n"
            f"用户ID：<code>{user_id}</code>\n"
            f"用户昵称：{user_name}\n"
            f"用户名：{user_username}\n"
            f"来自于：<a href='{msg_link}'>{source_title}</a>\n"
            f"用户历史搜索：{history_tags}\n"
            f"捕捉时间：{now_str}\n"
            f"发送内容：{content[:200]}"
        )
        
        for conf in matched_configs:
            uid = conf['uid']
            
            # [原有过滤逻辑]
            if conf['paused']: continue
            limit = conf['limit']
            if limit > 0 and len(content) > limit: continue 
            
            if uid in FILTER_CACHE:
                has_bad_word = False
                for bad in FILTER_CACHE[uid]:
                    if bad in content:
                        has_bad_word = True
                        break
                if has_bad_word: continue
            
            if conf['ai'] and is_spam_ai(content): continue

            # --- 推送消息 (原有逻辑) ---
            user_kb_list = []
            if not conf['simple']: 
                user_kb_list = ADS_CACHE + [] 
            
            fixed_btns = [
                [InlineKeyboardButton(text="🧐 消息定位 🧐", url=msg_link)] if message.link else [],
                [InlineKeyboardButton(text="❌ 关闭", callback_data="menu_monitor"), InlineKeyboardButton(text="🔊 拉黑ID", callback_data=f"ban:{user_id}")]
            ]
            final_kb = InlineKeyboardMarkup(inline_keyboard=user_kb_list + fixed_btns)
            
            target_chat_id = conf['target'] if conf['target'] else conf['uid']

            try:
                await bot.send_message(chat_id=target_chat_id, text=text, parse_mode="HTML", reply_markup=final_kb)
                logger.info(f"✅ 推送 -> {target_chat_id} (词:{hit_word})")
                
                # ==========================================
                # 🟢 [新增] 自动私信触发逻辑
                # ==========================================
                if target_username: # 必须有用户名才能私信
                    try:
                        async with db.pg_pool.acquire() as conn:
                            # 1. 查找该用户的私信配置 (owner_id 对应 users.id)
                            # 联表查询: users.tg_id -> users.id -> dm_settings & dm_accounts & dm_templates
                            dm_data = await conn.fetchrow("""
                                SELECT s.is_auto_reply, 
                                       (SELECT session_string FROM dm_accounts WHERE owner_id = u.id AND status='ready' ORDER BY RANDOM() LIMIT 1) as session,
                                       (SELECT text_content FROM dm_content_templates WHERE user_id = u.id AND is_active=TRUE LIMIT 1) as content
                                FROM users u
                                JOIN dm_settings s ON s.user_id = u.id
                                WHERE u.tg_id = $1
                            """, uid)
                        
                        # 2. 判断是否满足发送条件
                        if dm_data and dm_data['is_auto_reply'] and dm_data['session'] and dm_data['content']:
                            # 异步执行，不阻塞主流程
                            asyncio.create_task(
                                perform_dm_task(
                                    dm_data['session'], 
                                    target_username, 
                                    dm_data['content'], 
                                    uid # owner_id (这里没用到，可用于日志)
                                )
                            )
                            logger.info(f"⚖️ 触发自动私信 -> @{target_username}")
                            
                    except Exception as e:
                        logger.error(f"AutoDM Check Error: {e}")
                # ==========================================

            except TelegramForbiddenError:
                pass
            except Exception as e:
                logger.error(f"推送失败: {e}")

    except Exception as e:
        logger.error(f"Error: {e}")

async def main():
    await load_settings()
    async with db.pg_pool.acquire() as conn:
        sessions = await conn.fetch("SELECT phone, session_string FROM worker_sessions WHERE status='online'")
    
    if not sessions:
        logger.error("❌ 无可用监听账号")
        return

    clients = []
    for s in sessions:
        try:
            c = Client(name=f"w_{s['phone']}", api_id=settings.API_ID, api_hash=settings.API_HASH, session_string=s['session_string'], in_memory=True)
            c.add_handler(MessageHandler(handle_new_message, filters.group | filters.channel))
            clients.append(c)
        except Exception as e:
            logger.error(f"加载失败: {e}")

    if clients:
        logger.info(f"⚡️ 启动 {len(clients)} 个监听账号...")
        await asyncio.gather(*[c.start() for c in clients])
        
        async def loop_reload():
            while True:
                await asyncio.sleep(30)
                try: await load_settings()
                except: pass
        asyncio.create_task(loop_reload())
        
        await idle()
        await asyncio.gather(*[c.stop() for c in clients])

if __name__ == "__main__":
    asyncio.run(main())