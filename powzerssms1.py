import logging
import asyncio
import httpx
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# === AYARLAR ===
API_TOKEN = "7609911275:AAE09KGvE09dMZ87rb4VMHMLXM4JCCgBkjo"  # <-- Bot API Token buraya
SMSHUB_API_KEY = "226791Ub8f14d65149d14338c92c86894072ae1"  # <-- SMSHub API Key buraya
TRX_ADDRESS = "TYDBGuxXay6EKhjv1inFr3uzpNAwcxHyXV"
ADMIN_ID = 6834995171

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BALANCE_FILE = "balances.json"
user_balances = {}
user_numbers = {}

# === Dosya oku ===
try:
    with open(BALANCE_FILE, "r") as f:
        user_balances = json.load(f)
except FileNotFoundError:
    pass

# === Ülkeler, servisler, fiyatlar, operatörler ===
COUNTRIES = {
    "62": "Turkey",
    "4": "Philippines",
    "6": "Indonesia",
    "10": "Vietnam",
    "16": "England",
    "151": "Chile",
}

PLATFORMS = {
    "wa": "WhatsApp",
    "tg": "Telegram",
}

PRICES = {
    ("62", "wa"): 350,
    ("62", "tg"): 100,
    ("4", "wa"): 60,
    ("4", "tg"): 60,
    ("6", "wa"): 60,
    ("6", "tg"): 55,
    ("10", "wa"): 65,
    ("10", "tg"): 65,
    ("16", "wa"): 85,
    ("16", "tg"): 80,
    ("151", "wa"): 65,
    ("151", "tg"): 60,
}

OPERATORS = {
    "62": ["any", "turkcell", "turk_telekom", "vodafone"],
    "4": ["any", "dito", "globe_telecom", "smart", "tm"],
    "6": ["any", "axis", "byu", "indosat", "smartfren", "telkomsel", "three"],
    "10": ["any", "itelecom", "mobifone", "vietnamobile", "viettel", "vinaphone", "wintel"],
    "16": ["any", "airtel", "cmlink", "ee", "ezmobile", "giffgaff", "lebara", "lycamobile",
           "o2", "orange", "talk_telecom", "tata_communications", "teleena",
           "tesco", "three", "tmobile", "vectone", "vodafone"],
    "151": ["any", "claro", "entel", "movistar", "vodafone", "wom"],
}

# === Yardımcı Fonksiyonlar ===
def get_balance(uid):
    return user_balances.get(str(uid), 0)

def update_balance(uid, amount):
    uid = str(uid)
    user_balances[uid] = get_balance(uid) + amount
    with open(BALANCE_FILE, "w") as f:
        json.dump(user_balances, f)

def is_admin(uid):
    return uid == ADMIN_ID

async def get_prices():
    url = f"https://smshub.org/stubs/handler_api.php?api_key={SMSHUB_API_KEY}&action=getPrices"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json()

# === Komutlar ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mesaj gönderilecek nesne belirle
    if update.message:
        send_target = update.message
    elif update.callback_query:
        send_target = update.callback_query.message
        await update.callback_query.answer()
    else:
        return

    keyboard = [
        [InlineKeyboardButton("📲 SMS Onay", callback_data="menu_sms")],
        [InlineKeyboardButton("💰 Bakiye Yükle", callback_data="menu_balance")],
        [InlineKeyboardButton("📑 Numaralarım", callback_data="menu_numbers")],
        [InlineKeyboardButton("❓ Yardım / Destek", url="https://t.me/PowzersFakenoAccount")],
    ]
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("👑 Admin Menüsü", callback_data="menu_admin")])

    await send_target.reply_text(
        f"✅ Powzers Bot\n💰 Bakiye: {get_balance(update.effective_user.id):.2f}₺",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "menu_sms":
        keyboard = []
        for cid, cname in COUNTRIES.items():
            keyboard.append([InlineKeyboardButton(cname, callback_data=f"country_{cid}")])
        await query.message.delete()
        await query.message.reply_text(
            "🌍 Ülke Seç:",
            reply_markup=InlineKeyboardMarkup(keyboard + [[InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]])
        )

    elif query.data.startswith("country_"):
        cid = query.data.split("_")[1]
        keyboard = []
        for sid, sname in PLATFORMS.items():
            price = PRICES.get((cid, sid), 0)
            keyboard.append([InlineKeyboardButton(f"{sname} - {price}₺", callback_data=f"getnum_{cid}_{sid}")])
        await query.message.delete()
        await query.message.reply_text(
            f"📱 Platform Seç ({COUNTRIES[cid]}):",
            reply_markup=InlineKeyboardMarkup(keyboard + [[InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]])
        )

    elif query.data.startswith("getnum_"):
        _, cid, sid = query.data.split("_")
        price = PRICES.get((cid, sid), 0)
        if get_balance(uid) < price and not is_admin(uid):
            await query.message.reply_text(f"❌ Yetersiz bakiye. Gerekli: {price}₺")
            return

        success = False
        for operator in OPERATORS[cid]:
            url = f"https://smshub.org/stubs/handler_api.php?api_key={SMSHUB_API_KEY}&action=getNumber&service={sid}&country={cid}&operator={operator}"
            async with httpx.AsyncClient() as client:
                r = await client.get(url)
                if "ACCESS_NUMBER" in r.text:
                    _, order_id, num = r.text.strip().split(":")
                    if not is_admin(uid):
                        update_balance(uid, -price)
                    user_numbers.setdefault(str(uid), []).append((order_id, num, price))
                    await query.message.delete()
                    await query.message.reply_text(
                        f"📞 Numara: `{num}`\n\n⏳ Kod bekleniyor...",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("❌ İptal Et", callback_data=f"cancel_{order_id}")],
                             [InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]]
                        )
                    )
                    asyncio.create_task(check_code(context, uid, order_id))
                    success = True
                    break
        if not success:
            await query.message.reply_text("❌ Stok yok veya operatörlerde numara bulunamadı.")

    elif query.data.startswith("cancel_"):
        order_id = query.data.split("_")[1]
        url = f"https://smshub.org/stubs/handler_api.php?api_key={SMSHUB_API_KEY}&action=setStatus&status=8&id={order_id}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            if "ACCESS_CANCEL" in r.text:
                nums = user_numbers.get(str(uid), [])
                for num in nums:
                    if num[0] == order_id:
                        update_balance(uid, num[2])
                user_numbers[str(uid)] = [n for n in nums if n[0] != order_id]
                await query.message.reply_text("✅ Numara iptal edildi, ücret iade edildi.")
            else:
                await query.message.reply_text("❌ İptal edilemedi.")

    elif query.data == "menu_balance":
        await query.message.delete()
        await query.message.reply_text(
            f"💸 TRX Adresi:\n`{TRX_ADDRESS}`\n\nÖdeme yaptıktan sonra işlem ID gönderin.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]])
        )

    elif query.data == "menu_numbers":
        nums = user_numbers.get(str(uid), [])
        if not nums:
            await query.message.reply_text("Henüz numaran yok.")
        else:
            text = "\n".join([f"{n[1]}" for n in nums])
            await query.message.reply_text(f"📑 Numaraların:\n{text}",
                                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]]))

    elif query.data == "menu_admin":
        if not is_admin(uid):
            await query.message.reply_text("❌ Bu menüye erişim yetkiniz yok.")
            return
        await query.message.delete()
        keyboard = [
            [InlineKeyboardButton("📊 Kullanıcı Listesi", callback_data="admin_userlist")],
            [InlineKeyboardButton("💰 Bakiye Yükle", callback_data="admin_add_balance")],
            [InlineKeyboardButton("🔙 Ana Menü", callback_data="main_menu")]
        ]
        await query.message.reply_text(
            "👑 Admin Menüsü:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "admin_userlist":
        if not is_admin(uid):
            await query.message.reply_text("❌ Yetkiniz yok.")
            return
        text = "👥 Kayıtlı kullanıcılar:\n"
        for user_id, balance in user_balances.items():
            text += f"ID: {user_id} - Bakiye: {balance:.2f}₺\n"
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="menu_admin")]]))

    elif query.data == "admin_add_balance":
        if not is_admin(uid):
            await query.message.reply_text("❌ Yetkiniz yok.")
            return
        # Buraya adminin kullanıcıya bakiye yüklemesi için ilave kod eklenebilir
        await query.message.reply_text("💰 Bakiye yükleme işlemi yakında eklenecek.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="menu_admin")]]))

    elif query.data == "main_menu":
        await query.message.delete()
        await start(update, context)

async def check_code(context, uid, order_id):
    for _ in range(30):
        await asyncio.sleep(10)
        url = f"https://smshub.org/stubs/handler_api.php?api_key={SMSHUB_API_KEY}&action=getStatus&id={order_id}"
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            if "STATUS_OK" in r.text:
                _, code = r.text.strip().split(":")
                await context.bot.send_message(uid, f"✅ Kod: `{code}`", parse_mode="Markdown")
                break

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    if len(update.message.text.strip()) > 20:
        update_balance(uid, 50)
        await update.message.reply_text("✅ Ödeme onaylandı, 50₺ bakiye eklendi.")

def main():
    app = ApplicationBuilder().token(API_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("Bot Aktif 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()