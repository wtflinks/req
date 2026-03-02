# auto_accepter_full_ui.py
import asyncio
import logging
import random
import time
import os
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional
from pyrogram import enums
from pyrogram import Client, errors, enums, filters
from pyrogram.handlers import ChatJoinRequestHandler
from pyrogram.types import (
    ChatJoinRequest,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# local imports - keep your existing config & database modules
from config import cfg
from database import (
    add_user,
    add_group,
    all_users,
    all_groups,
    users,
    remove_user,
    get_setting,
    set_setting,
    delete_setting,
)

# -------------------------- Logging --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger("AutoAccepter")

# -------------------------- Clients --------------------------
app = Client(
    name="AutoAccepter",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN,
    workers=getattr(cfg, "WORKERS", 200),
)

# User client (for approving pending requests). session_string must be in cfg.SESSION
User = Client(name="PendingAccepter", session_string=getattr(cfg, "SESSION", None))

# track user client status (simple flag)
_USER_STARTED = False

# -------------------------- Media / defaults --------------------------
gif = ["https://envs.sh/V1B.jpg"]

# -------------------------- Helpers / UI builders --------------------------
def get_readable_time(seconds: float) -> str:
    seconds = int(seconds)
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for name, sec in periods:
        if seconds >= sec:
            val, seconds = divmod(seconds, sec)
            result += f"{val}{name}"
    return result or "0s"


def get_update_link() -> str:
    """
    Priority:
      1. DB (settings -> 'updates')
      2. cfg.INLINE_BUTTON_LINK
      3. environment variable UPDATE_LINK
      4. fallback default: https://t.me/tojimaster
    """
    try:
        val = get_setting("updates")
        if val:
            return val
    except Exception:
        logger.exception("Failed to read 'updates' from DB (settings).")

    if getattr(cfg, "INLINE_BUTTON_LINK", None):
        return cfg.INLINE_BUTTON_LINK

    if os.environ.get("UPDATE_LINK"):
        return os.environ.get("UPDATE_LINK")

    return "https://t.me/tojimaster"


def build_primary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("𝖬𝖸 𝖴𝖯𝖣𝖠𝖳𝖤𝖲 🧿", url=get_update_link())],
            [
                InlineKeyboardButton("➕ 𝖠𝖣𝖣 𝖳𝖮 𝖦𝖱𝖯", url="https://t.me/Bdreqbot?startgroup"),
                InlineKeyboardButton("📣 𝖠𝖣𝖣 𝖳𝖮 CHNL", url="https://t.me/Bdreqbot?startchannel"),
            ],
            # [InlineKeyboardButton("🆘 Help", callback_data="help_menu")],
        ]
    )


def build_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Message Me", url="https://t.me/Tojimaster")],
        ]
    )


def welcome_caption(user_mention: str) -> str:
    return (
        f"🦋 **𝖧𝖾𝗒 {user_mention}!**\n\n"
        "𝖨'𝗆 𝖠𝗎𝗍𝗈𝖠𝖼𝖼𝖾𝗉𝗍𝖾𝗋 — 𝖨 𝖺𝗎𝗍𝗈-𝖺𝗉𝗉𝗋𝗈𝗏𝖾 𝗃𝗈𝗂𝗇 𝗋𝖾𝗊𝗎𝖾𝗌𝗍𝗌 𝖿𝗈𝗋 𝗒𝗈𝗎𝗋 𝗀𝗋𝗈𝗎𝗉𝗌/𝖼𝗁𝖺𝗓𝗇𝗇𝖾𝗅𝗌.\n\n"
        "🔒 Add me as admin with **Add Members** permission, then I'll handle requests automatically.\n\n"
    )


def auto_approve_caption(user_mention: str, chat_title: Optional[str] = None) -> str:
    title_part = f" for **{chat_title}**" if chat_title else ""
    return (
        f"🦋 {user_mention}\n\n"
        "✅ Your request has been approved" + title_part + "!\n\n"
    )


def progress_status(total: int, success: int, failed: int, deact: int, blocked: int) -> str:
    return (
        f"📣 Broadcast Status\n\n"
        f"✅ Sent: `{success}` / `{total}`\n"
        f"❌ Failed: `{failed}`\n"
        f"👻 Deactivated: `{deact}`\n"
        f"⛔ Blocked: `{blocked}`\n\n"
        "⏱ Time: " + time.strftime("%Y-%m-%d %H:%M:%S")
    )


# -------------------------- User client control --------------------------
async def safe_start_user_client() -> None:
    global _USER_STARTED
    if _USER_STARTED:
        return
    try:
        await User.start()
        _USER_STARTED = True
        logger.info("User client started.")
    except Exception as e:
        # if already started or session issue, log and raise
        msg = str(e)
        if "already" in msg.lower():
            _USER_STARTED = True
            logger.info("User client already started (ignored).")
        else:
            logger.exception("Failed to start user client.")
            raise e


async def safe_stop_user_client() -> None:
    global _USER_STARTED
    if not _USER_STARTED:
        return
    try:
        await User.stop()
        _USER_STARTED = False
        logger.info("User client stopped.")
    except Exception as e:
        msg = str(e)
        if "not running" in msg.lower() or "closed" in msg.lower():
            _USER_STARTED = False
            logger.info("User client already stopped (ignored).")
        else:
            logger.exception("Failed to stop user client.")
            raise e


# -------------------------- Auto-approve handler --------------------------
async def auto_approve(app: Client, m: ChatJoinRequest) -> None:
    chat = m.chat
    requester = m.from_user

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎀 𝖩𝖮𝖨𝖭 𝖴𝖯𝖣𝖠𝖳𝖤𝖲", url=get_update_link())],
            [InlineKeyboardButton("🍃 𝖦𝖤𝖳 𝟨𝟨𝖪 𝖵𝖨𝖣𝖮 𝖢𝖧𝖭𝖫", url="https://t.me/TojiReqBot?start=start")],
        ]
    )

    img = random.choice(gif)

    try:
        caption = auto_approve_caption(
            requester.mention,
            getattr(chat, "title", None)
        )

        await app.send_photo(
            requester.id,
            img,
            caption=caption,
            reply_markup=keyboard
        )

    except errors.RPCError:
        logger.debug("Could not DM user %s", requester.id)
    except Exception:
        logger.exception("Unexpected DM error for %s", requester.id)

    try:
        await app.approve_chat_join_request(
            chat_id=chat.id,
            user_id=requester.id
        )

        add_group(chat.id)
        add_user(requester.id)

        logger.info(
            "Approved join request: chat=%s user=%s",
            chat.id,
            requester.id
        )

    except Exception as e:
        logger.exception("Approval error: %s", e)

    # 🔥 10 sec delay then forward promo message
    await asyncio.sleep(10)

    try:
        data = get_setting("forward_msg")
        if data:
            await app.forward_messages(
                chat_id=requester.id,
                from_chat_id=data["chat_id"],
                message_ids=data["message_id"]
            )
    except Exception as e:
        logger.exception("Forward message error: %s", e)

app.add_handler(ChatJoinRequestHandler(auto_approve, (filters.group | filters.channel)))


# -------------------------- /setforward

@app.on_message(filters.command("setforward") & filters.user(cfg.SUDO))
async def set_forward_message(app: Client, m: Message):

    if not m.reply_to_message:
        return await m.reply_text("Reply to a forwarded channel post.")

    reply = m.reply_to_message

    chat_id = None
    message_id = None

    # If normal forward
    if reply.forward_from_chat and reply.forward_from_message_id:
        chat_id = reply.forward_from_chat.id
        message_id = reply.forward_from_message_id

    # If sent via channel as sender_chat
    elif reply.sender_chat:
        chat_id = reply.sender_chat.id
        message_id = reply.id

    if not chat_id or not message_id:
        return await m.reply_text("❌ Please forward a real channel post.")

    data = {
        "chat_id": chat_id,
        "message_id": message_id
    }

    set_setting("forward_msg", data)

    await m.reply_text("✅ Forward message saved successfully.")
# -------------------------- /approve command --------------------------
APPROVEALL_MSG = [
    "<b>Approving Started</b>\nCHAT_ID: <code>{}</code>",
    "<b>Please provide two parameters.</b>\n<b>Format:</b> <code>/approve [batches] {}</code>\n\n⚠️<b>Note: 1 batch = 100 accepting (approx)</b>\n<i>eg: to attempt accepting 5000 requests use batches as <b>50</b> ([5000÷100=50])</i>",
]
ERROR_MSG = ["<b>Approving Stopped ❌\nReason:</b> <i>{}</i>"]


@app.on_message(filters.command("approve") & filters.user(cfg.SUDO))
async def approve_command(app: Client, m: Message) -> None:
    chat = m.chat
    args = m.text.split()
    if len(args) != 3:
        return await app.send_message(chat.id, APPROVEALL_MSG[1].format("-100xxxxx..."))

    # parse arguments safely
    try:
        batches = int(args[1])
        target_chat_id = int(args[2])
    except ValueError:
        return await app.send_message(chat.id, "<b>Invalid arguments.</b> Use integers.")

    if batches <= 0:
        return await app.send_message(chat.id, "<b>Batch count must be >= 1.</b>")

    info_msg = await app.send_message(chat.id, "<i>Starting user-client and approve process...</i>")
    start_time = time.time()
    approved_batches = 0

    # ensure User client is running
    try:
        await safe_start_user_client()
    except Exception as e:
        logger.exception("Cannot start user client.")
        return await info_msg.edit(f"<b>Can't start user client:</b> <i>{e}</i>")

    await app.send_message(chat.id, APPROVEALL_MSG[0].format(target_chat_id))

    try:
        for batch_index in range(batches):
            try:
                logger.info("Batch %d/%d - Approving for chat %s", batch_index + 1, batches, target_chat_id)
                await User.approve_all_chat_join_requests(chat_id=target_chat_id)
                approved_batches += 1
                await asyncio.sleep(0.7)
            except errors.FloodWait as fw:
                wait_seconds = int(getattr(fw, "value", getattr(fw, "x", 30)))
                logger.warning("FloodWait: sleeping %d seconds", wait_seconds)
                await app.send_message(chat.id, f"FloodWait — sleeping {get_readable_time(wait_seconds)}")
                await asyncio.sleep(wait_seconds + 5)
                logger.info("Resuming after FloodWait.")
            except Exception as e:
                logger.exception("Error while approving batch %d: %s", batch_index + 1, e)
                if "HIDE_REQUESTER_MISSING" in str(e) or "USER_NOT_PARTICIPANT" in str(e).upper():
                    await app.send_message(chat.id, ERROR_MSG[0].format(e))
                    break
                await asyncio.sleep(1)
    finally:
        try:
            await safe_stop_user_client()
        except Exception:
            logger.warning("Failed to stop user client cleanly.")

    time_taken = get_readable_time(time.time() - start_time)
    await app.send_message(
        chat.id,
        f"<b>Task Completed ✓</b>\n"
        f"Approved batches: <code>{approved_batches}</code>\n"
        f"Time taken: <i>{time_taken}</i>",
    )


# -------------------------- /start handler --------------------------
@app.on_message(filters.command("start"))
async def start_handler(app: Client, m: Message):

    user = m.from_user
    chat_type = m.chat.type
    param = m.command[1] if len(m.command) > 1 else None

    # ---------------- PRIVATE ----------------
    if chat_type == enums.ChatType.PRIVATE:

        add_user(user.id)

        # Deep link: /start mom
        if param == "mom":

            button = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "𝐅ᴜʟʟ 𝐃ᴇᴍᴏ 500+ 𝐌ᴇɢᴀ 𝐋ɪɴᴋ𝐬 🔗",
                            url="https://t.me/DemoTukerBot?start=BQADAQADVAoAAhuCMUXYYk6pDI-5yxYE"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "𝐅ᴜʟʟ 𝐃ᴇᴍᴏ 300+ 𝐆ʙ 𝐙ɪᴘ 💾",
                            url="https://t.me/DemoTukerBot?start=BQADAQADbAoAAhuCMUXWvveIygE_mxYE"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "𝐃ᴏᴡɴʟᴏᴀᴅ 𝐍ᴏᴡ 🍫",
                            url="http://t.me/Tojicandybot?start=start"
                        )
                    ]
                ]
            )

            await m.reply_text(
                "<b>𝐂ʜᴏᴏsᴇ 𝐚 𝐃ᴇᴍᴏ 𝐨ʀ 𝐃ᴏᴡɴʟᴏᴀᴅ:</b>",
                reply_markup=button,
                parse_mode=enums.ParseMode.HTML
            )
            return

        # Normal start
        await m.reply_photo(
            "https://envs.sh/V1B.jpg",
            caption=welcome_caption(user.mention),
            reply_markup=private_keyboard,
        )

    # ---------------- GROUP ----------------
    else:
        add_group(m.chat.id)
        await m.reply_text(
            "🦊 Hello! write me private for more details"
        )

    logger.info("%s started the bot.", user.first_name)
# -------------------------- callback handlers --------------------------
@app.on_callback_query(filters.regex(r"^chk$"))
async def check_callback(app: Client, cb: CallbackQuery) -> None:
    user = cb.from_user
    try:
        if getattr(cfg, "FORCESUB", None) is not None:
            await app.get_chat_member(cfg.FSUB_CHAT_ID, user.id)
        add_user(user.id)
        private_keyboard = build_primary_keyboard()
        await cb.message.edit(
            "**🦊 Hello! I'm AutoAccepter — add me to your chat & promote me as admin with Add Members permission.**",
            reply_markup=private_keyboard,
            disable_web_page_preview=True,
        )
    except errors.UserNotParticipant:
        await cb.answer("🙅‍♂️ You have not joined the channel. Join and try again. 🙅‍♂️", show_alert=True)
    except Exception:
        logger.exception("Error in chk callback")
        await cb.answer("An error occurred, please try again later.")


@app.on_callback_query(filters.regex(r"^help_menu$"))
async def help_menu_callback(app: Client, cb: CallbackQuery) -> None:
    # small interactive help card for users
    text = (
        "<b>🛠 AutoAccepter — Help</b>\n\n"
        "• <b>/approve <b>batches</b> <chat_id></b> — Bulk approve pending requests.\n"
        "• <b>/stats</b> — DB stats.\n"
        "• <b>/broadcast</b> — Reply to a message to copy to all users.\n"
        "• <b>/fbroadcast</b> — Reply to a message to forward to all users.\n"
        "• <b>/stop</b> — Stop the user client.\n\n"
        "⚠️ Make sure the User Bot is admin in the target chat for /approve to work."
    )
    await cb.answer()
    await cb.message.edit(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Support", url="https://t.me/Bdreqbot")]]))


# -------------------------- /stats command --------------------------
@app.on_message(filters.command("stats") & filters.user(cfg.SUDO))
async def stats_command(app: Client, m: Message) -> None:
    xx = all_users()
    x = all_groups()
    tot = int(xx + x)
    await m.reply_text(
        text=(
            "🍀 Chats Stats 🍀\n"
            f"🙋‍♂️ Users : `{xx}`\n"
            f"👥 Groups : `{x}`\n"
            f"🚧 Total users & groups : `{tot}`"
        )
    )


# -------------------------- broadcast (copy) --------------------------
@app.on_message(filters.command("broadcast") & filters.user(cfg.SUDO))
async def broadcast(app: Client, m: Message) -> None:
    if not m.reply_to_message:
        return await m.reply_text("Reply to a message to broadcast (copy).")

    lel = await m.reply_text("`⚡️ Processing broadcast...`")
    success = failed = deactivated = blocked = 0

    user_list = list(users.find({}, {"user_id": 1}))
    total = len(user_list)
    logger.info("Broadcast to %d users", total)

    # dynamic delay from DB settings (fallback 0.05)
    try:
        delay = float(get_setting("broadcast_delay") or 0.05)
    except Exception:
        delay = 0.05

    for doc in user_list:
        uid = doc.get("user_id")
        if not uid:
            continue
        try:
            await m.reply_to_message.copy(int(uid))
            success += 1
            await asyncio.sleep(delay)
        except errors.FloodWait as ex:
            logger.warning("FloodWait during broadcast: %s", ex)
            await asyncio.sleep(ex.value)
            try:
                await m.reply_to_message.copy(int(uid))
                success += 1
            except Exception as e:
                logger.exception("Retry failed for user %s: %s", uid, e)
                failed += 1
        except errors.InputUserDeactivated:
            deactivated += 1
            remove_user(uid)
        except errors.UserIsBlocked:
            blocked += 1
        except Exception:
            logger.exception("Failed to send broadcast to %s", uid)
            failed += 1

    await lel.edit(progress_status(total=total, success=success, failed=failed, deact=deactivated, blocked=blocked))


# -------------------------- fbroadcast (forward) --------------------------
@app.on_message(filters.command("fbroadcast") & filters.user(cfg.SUDO))
async def fbroadcast(app: Client, m: Message) -> None:
    if not m.reply_to_message:
        return await m.reply_text("Reply to a message to broadcast (forward).")

    lel = await m.reply_text("`⚡️ Processing forward broadcast...`")
    success = failed = deactivated = blocked = 0

    user_list = list(users.find({}, {"user_id": 1}))
    total = len(user_list)

    # dynamic delay from DB settings (fallback 0.05)
    try:
        delay = float(get_setting("broadcast_delay") or 0.05)
    except Exception:
        delay = 0.05

    for doc in user_list:
        uid = doc.get("user_id")
        if not uid:
            continue
        try:
            await m.reply_to_message.forward(int(uid))
            success += 1
            await asyncio.sleep(delay)
        except errors.FloodWait as ex:
            logger.warning("FloodWait during fbroadcast: %s", ex)
            await asyncio.sleep(ex.value)
            try:
                await m.reply_to_message.forward(int(uid))
                success += 1
            except Exception as e:
                logger.exception("Retry forward failed for user %s: %s", uid, e)
                failed += 1
        except errors.InputUserDeactivated:
            deactivated += 1
            remove_user(uid)
        except errors.UserIsBlocked:
            blocked += 1
        except Exception:
            logger.exception("Failed to forward to %s", uid)
            failed += 1

    await lel.edit(progress_status(total=total, success=success, failed=failed, deact=deactivated, blocked=blocked))


# -------------------------- /stop command --------------------------
@app.on_message(filters.command("stop") & filters.user(cfg.SUDO))
async def stop_user_command(app: Client, m: Message) -> None:
    a = await m.reply_text("Stopping user client...")
    try:
        await safe_stop_user_client()
        await a.edit("User client stopped.")
    except Exception as e:
        logger.exception("Can't stop user client")
        await a.edit(f"<b>Can't Stop User Bot ❌\nReason:</b> <i>{e}</i>")


# -------------------------- /setupdates command (SUDO only) --------------------------
@app.on_message(filters.command("setupdates") & filters.user(cfg.SUDO))
async def set_updates_cmd(app: Client, m: Message) -> None:
    """
    Usage:
      /setupdates <invite_or_channel_link>
      /setupdates reset
    Stores the link in DB collection 'settings' under _id == 'updates'.
    """
    args = m.text.split(maxsplit=1)
    if len(args) == 1:
        return await m.reply_text(
            "Usage: /setupdates <t.me or https:// link>  — or `/setupdates reset` to clear override."
        )

    payload = args[1].strip()
    if payload.lower() == "reset":
        try:
            delete_setting("updates")
        except Exception as e:
            logger.exception("Failed to delete 'updates' setting")
            return await m.reply_text(f"❌ Failed to reset: {e}")
        return await m.reply_text("✅ Update link cleared from DB. Falling back to config/default.")

    # basic validation
    if not (payload.startswith("http://") or payload.startswith("https://") or payload.startswith("t.me/")):
        return await m.reply_text("❌ Invalid link. Provide full invite/link starting with https:// or t.me/")

    try:
        set_setting("updates", payload)
    except Exception as e:
        logger.exception("Failed to save 'updates' to DB")
        return await m.reply_text(f"❌ Failed to save update link: {e}")

    return await m.reply_text(f"✅ Update link set (DB):\n`{payload}`")


# -------------------------- main --------------------------
if __name__ == "__main__":
    logger.info("Starting AutoAccepter bot...")
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Shutting down (keyboard).")
    except Exception:
        logger.exception("Bot crashed.")
