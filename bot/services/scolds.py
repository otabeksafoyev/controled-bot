"""Tanbex (so'kish) xabarlari pooli — javob bermagan paytda yuboriladi."""

from __future__ import annotations

import random

SCOLD_POOL: list[str] = [
    "Jinni bo'ldingmi?! Tur o'rningdan, mashqni qil!",
    "Dangasalik bas! Hozir tur va mashqni boshla, o'zingni achin!",
    "Ko'zing nimaga ko'r? Bot yozgan ekan — qil! Bahona kerak emas!",
    "Eh nodon, vaqtni shunchaki sovurding. Hozir tur va mashqni qil!",
    "Sen aytganingni o'zing buzasanmi?! Mashq seni kutyapti, harakatlan!",
    "Sport — irodaning ko'zgusi. Sen aks etmaganingdan keyin, demak iroda yo'q. Tur!",
    "O'zingdan uyalmadingmi? Mashq qilmasdan dam olganing — natijang ham xuddi shunday bo'ladi.",
    "Bo'sh gaplar bas. Telefonni qo'y, tur, mashqni boshla — hozir!",
    "Yana bahonami? Yana ertagami? Ertangi 'ertaga' kelmaydi. Hozir qil!",
    "Sen mashqdan qochsang, mashq sendan qochmaydi — natija qochadi. Tur, qiyofangni saqla!",
]


def random_scold() -> str:
    return random.choice(SCOLD_POOL)
