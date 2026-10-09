import sqlite3
import sys
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatMemberStatus

TOKEN = "8897693294:AAGE6yfAy2e2L9oPdGo5uOK5fjxTM3KuFa4"
DEFAULT_ADMINS = [1537665613, 6369115613]

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    replies_enabled INTEGER DEFAULT 1,
    delete_message TEXT DEFAULT 'ممنوع إرسال الردود'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER,
    user_id INTEGER,
    name TEXT,
    messages INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, user_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS auto_replies (
    chat_id INTEGER,
    keyword TEXT,
    response TEXT,
    PRIMARY KEY(chat_id, keyword)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS subscription (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    channel TEXT DEFAULT '',
    group_link TEXT DEFAULT ''
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS bot_admins (
    user_id INTEGER PRIMARY KEY
)
""")

db.commit()

for adm in DEFAULT_ADMINS:
    cur.execute("INSERT OR IGNORE INTO bot_admins(user_id) VALUES(?)", (adm,))
db.commit()


def ensure_group(chat_id):
    cur.execute(
        "INSERT OR IGNORE INTO groups(chat_id) VALUES(?)",
        (chat_id,)
    )
    db.commit()


async def is_bot_admin(user_id):
    cur.execute("SELECT user_id FROM bot_admins WHERE user_id=?", (user_id,))
    return cur.fetchone() is not None


def is_owner(user_id):
    return user_id in DEFAULT_ADMINS


async def send_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not await is_bot_admin(user.id):
        return

    keyboard = [
        [KeyboardButton("تعيين كليشة الحذف 📝"), KeyboardButton("تعيين اشتراك إجباري 🔗")],
        [KeyboardButton("حذف اشتراك إجباري 🗑️"), KeyboardButton("إضافة رد 💬")],
        [KeyboardButton("رفع مشرف 👤+"), KeyboardButton("الردود المضافة 📋")],
        [KeyboardButton("إعادة تشغيل البوت 🔄")]
    ]
    
    if is_owner(user.id):
        keyboard.append([KeyboardButton("تنزيل مشرف 👤-")])

    await update.message.reply_text(
        "أهلاً بك في لوحة تحكم البوت (الخاص).\nاختر من الأزرار أدناه للتحكم بجميع إعدادات البوت:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    
    if update.effective_chat.type == "private" and await is_bot_admin(user.id):
        await send_control_panel(update, context)
    else:
        await update.message.reply_text("أهلاً بك في البوت.")
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    chat_id = query.message.chat.id

    if not await is_bot_admin(user.id) and query.data != "check_subscription":
        await query.answer(
            "هذه اللوحة للمشرفين المعتمدين فقط.",
            show_alert=True
        )
        return

    data = query.data

    if data.startswith("del_rep_"):
        kw_to_delete = data.replace("del_rep_", "")
        cur.execute(
            "DELETE FROM auto_replies WHERE chat_id=0 AND keyword=?",
            (kw_to_delete,)
        )
        db.commit()
        await query.answer(f"تم حذف الرد ({kw_to_delete}) بنجاح.", show_alert=True)
        try:
            await query.message.edit_text(f"تم حذف الرد ({kw_to_delete}) بنجاح من القائمة العامة.")
        except Exception:
            pass

    elif data.startswith("del_adm_"):
        if not is_owner(user.id):
            await query.answer("هذا الإجراء مخصص للمالكين الأساسيين فقط!", show_alert=True)
            return
        
        adm_to_del = int(data.replace("del_adm_", ""))
        if adm_to_del in DEFAULT_ADMINS:
            await query.answer("لا يمكنك تنزيل المالك الأساسي للبوت!", show_alert=True)
            return

        cur.execute("DELETE FROM bot_admins WHERE user_id=?", (adm_to_del,))
        db.commit()
        await query.answer(f"تم تنزيل الأيدي ({adm_to_del}) من المشرفين بنجاح.", show_alert=True)
        try:
            await query.message.edit_text(f"تم تنزيل المشرف ذو الأيدي ({adm_to_del}) بنجاح وإزالة صلاحياته.")
        except Exception:
            pass


async def send_top(message, chat_id):
    cur.execute("""
    SELECT name, messages
    FROM users
    WHERE chat_id=?
    ORDER BY messages DESC
    LIMIT 10
    """, (chat_id,))

    rows = cur.fetchall()

    if not rows:
        await message.reply_text(
            "لا توجد إحصائيات تفاعل حتى الآن."
        )
        return

    text = "🏆 توب 10 المتفاعلين:\n\n"

    for i, (name, messages) in enumerate(rows, 1):
        text += f"{i}. {name} - {messages} رسالة\n"

    await message.reply_text(text)
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat:
        return

    chat_id = chat.id
    is_group = chat.type in ["group", "supergroup"]
    is_private = chat.type == "private"

    if is_group:
        ensure_group(chat_id)

        if message.text == "/إيقاف" and user and await is_bot_admin(user.id):
            cur.execute("UPDATE groups SET replies_enabled=0 WHERE chat_id=?", (chat_id,))
            db.commit()
            await message.reply_text("تم إيقاف مسح الردود في هذه المجموعة.")
            return

        elif message.text == "/تفعيل" and user and await is_bot_admin(user.id):
            cur.execute("UPDATE groups SET replies_enabled=1 WHERE chat_id=?", (chat_id,))
            db.commit()
            await message.reply_text("تم تفعيل مسح الردود في هذه المجموعة.")
            return

        elif message.text and message.text.strip() == "توب":
            await send_top(message, chat_id)
            return

    action = context.user_data.get("action")

    if is_private and action and user and await is_bot_admin(user.id):
        if action == "set_delete_message":
            if message.text:
                cur.execute("""
                INSERT INTO groups(chat_id, delete_message) VALUES(0, ?)
                ON CONFLICT(chat_id) DO UPDATE SET delete_message=excluded.delete_message
                """, (message.text.strip(),))
                db.commit()
                context.user_data.pop("action", None)
                await message.reply_text("✅ تم تحديث وحفظ كليشة الحذف العامة بنجاح.")
            return

        elif action == "set_subscription_link":
            if message.text:
                text_input = message.text.strip()
                parts = text_input.split()
                channel_name = parts[0]
                group_link = text_input if len(parts) > 1 else f"https://t.me/{channel_name.replace('@', '')}"
                
                cur.execute("""
                INSERT INTO subscription(chat_id, enabled, channel, group_link)
                VALUES(0, 1, ?, ?)
                ON CONFLICT(chat_id)
                DO UPDATE SET enabled=1, channel=excluded.channel, group_link=excluded.group_link
                """, (channel_name, group_link))
                db.commit()
                context.user_data.pop("action", None)
                await message.reply_text(f"✅ تم تفعيل وحفظ الاشتراك الإجباري بنجاح!\nالقناة: {channel_name}")
            return

        elif action == "add_admin":
            if message.text:
                inp = message.text.strip()
                new_adm_id = None
                if inp.isdigit():
                    new_adm_id = int(inp)
                else:
                    clean_user = inp.replace("@", "")
                    try:
                        chat_info = await context.bot.get_chat(f"@{clean_user}")
                        new_adm_id = chat_info.id
                    except Exception:
                        pass

                if new_adm_id:
                    cur.execute("INSERT OR IGNORE INTO bot_admins(user_id) VALUES(?)", (new_adm_id,))
                    db.commit()
                    context.user_data.pop("action", None)
                    await message.reply_text(f"✅ تم رفع الأيدي ({new_adm_id}) مشرفاً جديداً بنجاح وأصبحت لديه صلاحيات التحكم!")
                else:
                    await message.reply_text("❌ لم يتم التعرف على المستخدم، أرسل أيدي صحيح أو يوزرنيم صحيح.")
            return

        elif action == "remove_admin":
            if message.text and is_owner(user.id):
                inp = message.text.strip()
                target_adm_id = None
                if inp.isdigit():
                    target_adm_id = int(inp)
                else:
                    clean_user = inp.replace("@", "")
                    try:
                        chat_info = await context.bot.get_chat(f"@{clean_user}")
                        target_adm_id = chat_info.id
                    except Exception:
                        pass

                if target_adm_id:
                    if target_adm_id in DEFAULT_ADMINS:
                        await message.reply_text("❌ لا يمكنك تنزيل المالك الأساسي للبوت!")
                        context.user_data.pop("action", None)
                        return

                    cur.execute("DELETE FROM bot_admins WHERE user_id=?", (target_adm_id,))
                    db.commit()
                    context.user_data.pop("action", None)
                    await message.reply_text(f"✅ تم تنزيل الأيدي ({target_adm_id}) من قائمة المشرفين بنجاح.")
                else:
                    await message.reply_text("❌ لم يتم التعرف على المستخدم، أرسل أيدي صحيح.")
            return

        elif action == "add_reply_keyword":
            if message.text:
                context.user_data["reply_keyword"] = message.text.strip()
                context.user_data["action"] = "add_reply_text"
                await message.reply_text("ارسل الرد الآن:")
            return

        elif action == "add_reply_text":
            keyword = context.user_data.get("reply_keyword")
            if keyword and message.text:
                cur.execute("""
                INSERT OR REPLACE INTO auto_replies
                (chat_id, keyword, response)
                VALUES(0, ?, ?)
                """, (keyword, message.text.strip()))
                db.commit()

            context.user_data.pop("action", None)
            context.user_data.pop("reply_keyword", None)
            await message.reply_text("✅ تم حفظ الرد العام بنجاح.")
            return

    if is_private and user and await is_bot_admin(user.id) and message.text in ["تعيين كليشة الحذف 📝", "تعيين اشتراك إجباري 🔗", "حذف اشتراك إجباري 🗑️", "رفع مشرف 👤+", "تنزيل مشرف 👤-", "إضافة رد 💬", "الردود المضافة 📋", "إعادة تشغيل البوت 🔄"]:
        if message.text == "تعيين كليشة الحذف 📝":
            context.user_data["action"] = "set_delete_message"
            await message.reply_text("ارسل كليشة الحذف الجديدة الآن:")
            return
        elif message.text == "تعيين اشتراك إجباري 🔗":
            context.user_data["action"] = "set_subscription_link"
            await message.reply_text("ارسل معرف القناة ورابطها (مثال: @ChannelName https://t.me/ChannelName):")
            return
        elif message.text == "حذف اشتراك إجباري 🗑️":
            cur.execute("DELETE FROM subscription WHERE chat_id=0")
            db.commit()
            await message.reply_text("🗑 تم حذف وتعطيل الاشتراك الإجباري العام بنجاح.")
            return
        elif message.text == "إعادة تشغيل البوت 🔄":
            await message.reply_text("🔄 جاري إعادة تشغيل البوت الآن...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
            return
        elif message.text == "رفع مشرف 👤+":
            context.user_data["action"] = "add_admin"
            await message.reply_text("ارسل أيدي الشخص أو يوزرنيم الشخص لرفعه مشرفاً:")
            return
        elif message.text == "تنزيل مشرف 👤-":
            if not is_owner(user.id):
                await message.reply_text("هذا الأمر مخصص للمالكين الأساسيين فقط.")
                return
            context.user_data["action"] = "remove_admin"
            cur.execute("SELECT user_id FROM bot_admins")
            admins_rows = cur.fetchall()
            txt = "قائمة المشرفين الحاليين في البوت:\n\n"
            kb = []
            for (adm_id,) in admins_rows:
                txt += f"• أيدي: {adm_id}\n"
                if adm_id not in DEFAULT_ADMINS:
                    kb.append([InlineKeyboardButton(f"تنزيل: {adm_id}", callback_data=f"del_adm_{adm_id}")])
            
            txt += "\nأو أرسل أيدي الشخص مباشرة هنا لتنزيله:"
            if kb:
                await message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message.reply_text(txt)
            return
        elif message.text == "إضافة رد 💬":
            context.user_data["action"] = "add_reply_keyword"
            await message.reply_text("ارسل كلمة مفتاحية للرد:")
            return
        elif message.text == "الردود المضافة 📋":
            cur.execute("SELECT keyword, response FROM auto_replies WHERE chat_id=0")
            rows = cur.fetchall()
            if not rows:
                await message.reply_text("لا توجد ردود عامة مضافة.")
                return
            kb = []
            txt = "الردود المضافة العامة:\n\n"
            for idx, (kw, resp) in enumerate(rows, 1):
                txt += f"{idx}. {kw} -> {resp}\n"
                kb.append([InlineKeyboardButton(f"حذف: {kw}", callback_data=f"del_rep_{kw}")])
            await message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
            return
    if user and is_group:
        is_user_group_admin = False
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user.id)
            is_user_group_admin = chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception:
            pass

        if not is_user_group_admin and not await is_bot_admin(user.id) and not is_owner(user.id):
            cur.execute("""
            SELECT enabled, channel, group_link
            FROM subscription
            WHERE chat_id=0 AND enabled=1
            """)
            sub = cur.fetchone()

            if sub:
                channel = sub[1]
                g_link = sub[2] or f"https://t.me/{channel.replace('@', '')}"
                subscribed = False

                try:
                    member = await context.bot.get_chat_member(channel, user.id)
                    if member.status in [
                        ChatMemberStatus.MEMBER,
                        ChatMemberStatus.ADMINISTRATOR,
                        ChatMemberStatus.OWNER,
                        ChatMemberStatus.RESTRICTED
                    ]:
                        subscribed = True
                except Exception as e:
                    print(f"Subscription Check Error: {e}")
                    subscribed = False

                if not subscribed:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "اشتراك بالقناة 🔗",
                                url=g_link
                            )
                        ]
                    ]

                    await context.bot.send_message(
                        chat_id,
                        f"عذراً {user.mention_html()}، عليك الاشتراك بالقناة التالية لتتمكن من النشر هنا:\n{channel}",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return

    if user and is_group:
        cur.execute("""
        INSERT INTO users(chat_id, user_id, name, messages)
        VALUES(?,?,?,1)
        ON CONFLICT(chat_id,user_id)
        DO UPDATE SET
            name=excluded.name,
            messages=messages+1
        """, (
            chat_id,
            user.id,
            user.full_name
        ))
        db.commit()

    if is_group and message.reply_to_message:
        replied_user = message.reply_to_message.from_user

        if replied_user and user and replied_user.id != user.id:
            cur.execute(
                "SELECT replies_enabled, delete_message "
                "FROM groups WHERE chat_id=?",
                (chat_id,)
            )
            row = cur.fetchone()

            replies_en = 1
            delete_text = None

            if row:
                replies_en = row[0]
                delete_text = row[1]

            if not delete_text or delete_text == 'ممنوع إرسال الردود':
                cur.execute("SELECT delete_message FROM groups WHERE chat_id=0")
                g_row = cur.fetchone()
                if g_row and g_row[0]:
                    delete_text = g_row[0]

            if replies_en == 1:
                final_delete_text = delete_text or "ممنوع الرد"

                try:
                    await message.delete()
                except Exception:
                    return

                await context.bot.send_message(
                    chat_id,
                    f"{user.mention_html()} {final_delete_text}",
                    parse_mode="HTML"
                )
                return

    if is_group and message.text:
        cur.execute("""
        SELECT response
        FROM auto_replies
        WHERE (chat_id=? OR chat_id=0) AND keyword=?
        ORDER BY chat_id DESC
        LIMIT 1
        """, (
            chat_id,
            message.text.strip()
        ))
        reply = cur.fetchone()

        if reply:
            await message.reply_text(
                reply[0]
            )
app = Application.builder().token(TOKEN).build()

app.add_handler(
    CommandHandler(
        "start",
        start
    )
)

app.add_handler(
    CallbackQueryHandler(
        buttons
    )
)

app.add_handler(
    MessageHandler(
        filters.ALL,
        messages
    )
)

print("البوت يعمل الآن...")
app.run_polling()
