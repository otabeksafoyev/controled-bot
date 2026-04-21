# Kaworai Controled Bot

Telegram userbot + control bot. **Sizning shaxsiy akauntingiz orqali** kanallarni
kuzatadi va topilgan videolarni to'g'ri formatda `kaworai_bot`'ning **SECRET_CHANNEL**
iga post qiladi. Kaworai_bot o'zining mavjud handleri bilan qismni DB ga qo'shib qo'yadi.

## Tamoyil

```
Kanallar ────(MTProto)───▶ Userbot (sizning akauntingiz)
                                 │
                    /link <kanal> <anime_id>
                                 │
                                 ▼
              Userbot SECRET_CHANNEL ga post qiladi
              caption: "ID: <anime_id>\nQism: <episode>"
                                 │
                                 ▼
                kaworai_bot mavjud handleri ishlaydi
                  va series jadvaliga qismni qo'shadi
```

**Bot hech qayerda admin bo'lishi shart emas.** Kanalda video siz (userbot)
tomonidan post qilinadi — SECRET_CHANNEL siz kaworai_bot uchun yaratgan
kanalingiz bo'lgani uchun sizda u erga post qilish huquqi bor.

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `userbot/client.py`, `userbot/handlers.py` | Telethon — kanallarni kuzatish |
| `userbot/matcher.py` | Caption/filename dan qism raqamini ajratib olish |
| `bot/client.py`, `bot/handlers/admin.py` | Aiogram control bot — komandalar |
| `db/models.py`, `db/queries.py` | Mahalliy SQLite (kanal→anime map + dedup) |
| `config.py` | Sozlamalar (.env orqali) |
| `main.py` | Userbot + control botni birga ishga tushiradi |
| `scripts/create_session.py` | StringSession yaratuvchi (bir martalik) |

## Sozlash

1. Repository clone qilib, requirements o'rnating:
   ```bash
   git clone https://github.com/otabeksafoyev/controled-bot
   cd controled-bot
   pip install -r requirements.txt
   ```

2. `.env` faylini yarating (`.env.example` dan ko'chiring) va to'ldiring:
   - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` — https://my.telegram.org/apps
   - `CONTROL_BOT_TOKEN` — @BotFather dan yangi bot
   - `OWNER_ID` — sizning Telegram user IDingiz (@userinfobot)
   - `SECRET_CHANNEL_ID` — kaworai_bot `.env` dan `SECRET_CHANNEL_ID` qiymati
   - `TELEGRAM_STRING_SESSION` — keyingi qadamda

3. StringSession yarating (bir marta):
   ```bash
   python scripts/create_session.py
   ```
   Telefon raqami va SMS kod so'raladi. Chiqqan stringni `.env` ga yozing.

4. Ishga tushiring:
   ```bash
   python main.py
   ```
   Birinchi startda `watcher.db` (SQLite) avtomatik yaratiladi.

## Foydalanish

Control bot bilan private chatda (sizdan boshqa hech kim komanda yubora olmaydi):

- `/start` — yordam
- `/status` — userbot va konfiguratsiya holati
- `/resolve @kanal` — kanal IDsini olish
- `/subscribe @kanal` yoki `/subscribe <invite_link>` — userbot obuna bo'ladi
- `/unsubscribe @kanal`
- `/link <kanal_id> <anime_id>` — kanalni kaworai anime-ga bog'lash
- `/unlink <kanal_id> [<anime_id>]`
- `/channels` — barcha bog'lanishlar
- `/forwarded` — so'nggi yuborilgan fayllar

## Ish oqimi (misol)

1. Kaworai admin panelda yangi anime qo'shdingiz — ID: 388
2. Shu anime chiqib turadigan kanalni bilasiz: `@naruto_uploads`
3. Control botga `/subscribe @naruto_uploads` — userbot obuna bo'ldi
4. `/resolve @naruto_uploads` → ID olasiz (masalan `-1002345678901`)
5. `/link -1002345678901 388` — bog'lash
6. O'sha kanalga yangi video post qilinganda (caption: "qism 13"):
   - Userbot file_unique_id bo'yicha dedup tekshiradi
   - Qism raqamini caption dan ajratadi (13)
   - Kaworai SECRET_CHANNEL ga post qiladi: caption `ID: 388\nQism: 13`
   - kaworai_bot avtomatik series jadvaliga qo'shadi va sizga bildirishnoma yuboradi

## Dedup

Mahalliy SQLite `watcher_forwarded` jadvalida `file_unique_id` bo'yicha dedup
qiladi. Qayta ishga tushirilsa ham tarix saqlanadi.

## Muammo bartaraf etish

- **"SECRET_CHANNEL ga yuborishda xato"** — siz o'sha kanalda post qila
  olishingizga ishonch hosil qiling (kaworai uchun yaratgan kanal bo'lgani uchun
  odatda admin hisoblanasiz).
- **Userbot FloodWait** — Telegram rate limit. Telethon avtomatik kutadi.
- **Qism raqami noto'g'ri aniqlanadi** — post caption-da `qism 13` yoki `ep 13`
  kabi aniq format kerak. Topilmasa `1` ishlatiladi (keyin kaworai `last_ep+1`
  qo'yadi).
