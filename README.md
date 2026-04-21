# Kaworai Watcher

Sizning shaxsiy Telegram akauntingiz orqali kanallarni kuzatib, yangi video
postlarni **Kaworai anime bot** ma'lumotlar bazasiga avtomatik qism sifatida
qo'shadi.

**Bot hech qayerda admin emas.** U sizning akauntingizga ulangan 2-foydalanuvchi
kabi ishlaydi va faqat siz bilan private chatda aloqa qiladi.

## Qanday ishlaydi

1. **Userbot (Telethon)** — sizning akauntingiz bilan ulanadi. Siz obuna
   bo'lgan kanallardagi yangi postlarni kuzatadi.
2. Yangi video post kelsa va kanal `/link` orqali aniq anime-ga bog'langan
   bo'lsa, userbot videoni **control bot bilan private chatga** yuboradi
   (JSON-metadata caption bilan). Userbot = sizning akauntingiz, shuning
   uchun bot bu xabarni xuddi siz shaxsan yuborganday ko'radi.
3. **Control bot (aiogram)** private xabarni qabul qiladi, bot-API `file_id`
   ni oladi va `series` jadvaliga yangi qism qilib yozadi.
4. Dublikat bo'lmasligi uchun `file_unique_id` bo'yicha dedup qilinadi.

### Nega shunday?

Userbot (MTProto) va bot (Bot API) `file_id`lari o'zaro mos kelmaydi. Kaworai
bot foydalanuvchilarga video yuborishi uchun **bot-API file_id** kerak.
Shuning uchun userbot videoni bot bilan private chatga jo'natadi → bot o'zining
`file_id` sini oladi va DB-ga yozadi.

## O'rnatish

```bash
pip install -r requirements.txt
cp .env.example .env
# .env ni to'ldiring (quyiga qarang)
```

### .env

| Key | Ma'no |
| --- | --- |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | https://my.telegram.org/apps dan |
| `TELEGRAM_STRING_SESSION` | `python scripts/create_session.py` chiqargan qator |
| `CONTROL_BOT_TOKEN` | @BotFather dan yangi bot |
| `OWNER_ID` | Sizning Telegram ID (faqat siz komandalar chaqira olasiz) |
| `DB_URL` | Kaworai bilan bir xil Postgres URL |

### StringSession yaratish

```bash
python scripts/create_session.py
```

Telefon raqam va kodni kiritgandan keyin bitta qator chiqadi — uni `.env` ga
`TELEGRAM_STRING_SESSION=...` shaklida joylashtiring.

### Control botni ishga tayyorlash

1. @BotFather orqali yangi bot yarating; tokenni `.env` ga yozing.
2. O'z akauntingiz bilan shu botni ochib, **bir marta `/start`** bosing. Bu
   userbot-ga botga xabar yubora olish imkonini beradi.

### DB migration

Kaworai_bot DB-ga quyidagini bir marta ishlating:

```bash
psql "$DB_URL" -f migrations/001_initial.sql
```

Bu:
- `series.file_unique_id` ustunini qo'shadi (eski qatorlar NULL qoladi)
- `watcher_channel_links` va `watcher_processed_files` jadvallarini yaratadi

### Ishga tushirish

```bash
python main.py
```

yoki Docker bilan:

```bash
docker compose up -d --build
```

## Control bot komandalari

Komandalar faqat `OWNER_ID` foydalanuvchi uchun, private chatda:

| Komanda | Tavsif |
| --- | --- |
| `/start` | yordam |
| `/status` | userbot + bog'lanishlar holati |
| `/resolve <@username\|link>` | kanal IDsini aniqlash |
| `/subscribe <@username\|invite link>` | userbot kanalga obuna bo'ladi |
| `/unsubscribe <@username\|id>` | obunadan chiqish |
| `/link <kanal> <anime_id>` | kanalni anime-ga bog'lash |
| `/unlink <kanal_id> [<anime_id>]` | bog'lanishni o'chirish |
| `/channels` | barcha bog'lanishlar |

### Namuna ish oqimi

```
/resolve @my_anime_channel   → -1001234567890, "My Anime Channel"
/subscribe @my_anime_channel
/link -1001234567890 42       # kanal → anime #42
/channels
```

Endi o'sha kanalga yangi video post chiqqanda, u avtomatik Kaworai bot-da
anime #42 ning keyingi qismi sifatida qo'shiladi.

## Moslashtirish mantig'i

1. Kanal `watcher_channel_links` da bo'lishi kerak.
2. Video davomiyligi `MIN_VIDEO_DURATION` dan katta (default 60s).
3. `file_unique_id`:
   - `watcher_processed_files` da bo'lsa → skip
   - `series.file_unique_id` da bo'lsa → skip va processed deb belgilash
4. Qism raqami: caption/fayl nomidan (`qism 5`, `Ep 05`, `S01E05`, ...).
   Topilmasa → `max(episode)+1`.
5. `(anime_id, episode)` allaqachon bor bo'lsa → skip.
6. Aks holda userbot videoni control bot bilan private chatga yuboradi →
   control bot DB ga yozadi.

## Xavfsizlik

- `.env`, `*.session` git-ga tushmasligi kerak (`.gitignore` da).
- Userbot sessiyasini hech kimga bermang — bu sizning akauntingiz.
- Control bot faqat `OWNER_ID` dan kelgan xabarlarni qabul qiladi.
- Agar bot tokeni oshkor bo'lsa — @BotFather `/revoke` orqali qayta generatsiya
  qiling va `.env` ni yangilang.
