"""Tanbex (so'kish) xabarlari pooli — javob bermagan paytda yuboriladi.

Foydalanuvchining iltimosiga ko'ra qattiqroq, og'riqliroq, jonli ohanglar.
"""

from __future__ import annotations

import random

# Asosiy qattiq tanbex xabarlari pooli.
# Eslatma vaqti o'tib, foydalanuvchi javob bermagan paytda yuboriladi.
SCOLD_POOL: list[str] = [
    "Hoyt!! Yana yo'qolib qoldingmi?! Telefonga yopishib o'tirma, TUR mashqni qil! Hoziroq!",
    "Sen jiddiymisan o'zi?! Mashq vaqti keldi, sen esa shunchaki qarab turibsanmi? Uyalmaysanmi?",
    "Bo'ldi, dangasalik! Bo'ldi bahonalar! HOZIR tur, telefonni qo'y, mashqni boshla! Bahonangni eshitishni xohlamayman.",
    "Sen o'zingni aldayapsan, men emas. Mashq qilmasang, natijang ham yo'q. Ko'p o'ylama — TUR!",
    "Yana ertagagami? Ertangi 'ertaga' hech qachon kelmaydi. Vaqt sendan qochyapti, sen esa xurrak otyapsan!",
    "Bot eslatdi, sen e'tibor bermading. Demak so'zing puch, irodang nol. Tur, isbotla — yoki yana uxla, yana shu ahvolda qol!",
    "O'zingdan uyalmadingmi? Rejani sen yozgan, sen tasdiqlagan, sen unutyapsan. TUR! Mashq seni kutib turibdi!",
    "Yana bahonami?! Charchadim, vaqt yo'q, kayfiyat yo'q — barchasi yolg'on. ORTIQ BAHONA YO'Q. Hoziroq mashqni qil!",
    "Sen aytgansan: 'Men o'zgaraman.' Hozir sen bu so'zni yana puchga chiqaryapsan. TUR! Yo'qsa hech qachon o'zgarmaysan!",
    "Telefonni tashla. Skrollni to'xtat. TUR! Mashq qil! Boshqa hech narsa muhim emas hozir!",
    "Sen yana shunday qilsang, ertaga ham aynan shunday qilasan. Dangasalik — odat. Odatni hozir uzasan, bo'lmasa hech qachon!",
    "Sen rejangni o'zing yozgan ekansan, sen uni o'zing buzyapsan. Bu sening dushmaning sen o'zing degani. Tur va kuchroq bo'l!",
    "Yana 5 daqiqa? 5 daqiqa o'tdi, sen hali ham shu yerda. Yolg'on aytma o'zingga. TUR HOZIROQ!",
    "Hoyt!!! Bu mashq seni kuchli qiladi, sen esa uni qil deyman, sen esa yo'q deysan. Sening kelajaging hozir tepada turibdi — sen uni tepib yuboryapsan!",
    "Bot zerikkanini bilasanmi?! Har kuni eslataman, har kuni sen yo'qolasan. Bo'ldi! Bugun farq bo'lsin — TUR!",
    "Vaqt o'tyapti, yoshing oshyapti, mushaklaring kichraydi. Sen esa o'tirib o'ylab o'tiribsanmi? TUR! Hozirgina! KECH EMAS!",
    "Sen mashqdan qochsang, sog'liq sendan qochadi. Sen yoshlikdan qochsang, qarilik tezroq keladi. TUR!",
    "O'zingga rahm qilma. Rahm qilsang, hech narsa o'zgarmaydi. Qattiqqo'l bo'l O'ZINGGA! Tur, qil, shikoyat qilma!",
    "Sen bu yo'lni o'zing tanlagan. Endi yo borasan, yo to'xtaysan. Tanla — lekin yana ertaga deyma. HOZIR — yoki HECH QACHON!",
    "Mashqni qilmasang, sen ertaga oynadan kim ko'rasan? O'zingni? Yo'q — sen tushkun, dangasa, va'dasini buzgan odamni ko'rasan. Buni xohlaysanmi?! TUR!",
    "VAQTING TUGADI. Sen yana yutqazding — o'zingdan. Mashq endi 2-marta o'tdi, sen 0-marta tursang. Bu sening hayoting?!",
    "Hoyt, BO'LDI! Sen meni kar deb o'ylayapsanmi?! Tur, mashqni qil, BAHONA TUGAGAN!",
    "Sen o'zingga 'yarim soat dam' deding — yarim soat soatga aylandi. Soat kunga aylandi. KUN OYIGA. Sen butun umr 'yarim soat'da yashayapsanmi?!",
    "Endi men so'kishni to'xtatmayman. Toki sen turmaguningcha. Tushunyapsanmi?! TUR!",
    "Mashqni qil yoki ertaga oynaga qarama. Ikkalasini bir vaqtda qila olmaysan!",
]


def random_scold() -> str:
    return random.choice(SCOLD_POOL)
