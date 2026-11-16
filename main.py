import os
import re
import asyncio
import aiohttp
import html
import phonenumbers
from phonenumbers import geocoder, carrier, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан в Secrets")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


async def check_url(session, url, timeout=8):
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as r:
            text = await r.text()
            return r.status, text[:5000]
    except Exception:
        return 0, ""


async def ddg_search(session, query):
    url = "https://html.duckduckgo.com/html/"
    try:
        async with session.post(
            url,
            data={"q": query},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            html_text = await r.text()
    except Exception:
        return []

    links = re.findall(
        r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html_text,
    )
    out = []
    for href, title in links[:10]:
        clean_title = re.sub(r"<[^>]+>", "", title).strip()
        safe_title = html.escape(clean_title)
        out.append((safe_title, href))
    return out


async def check_messengers(session, num_e164):
    digits = num_e164.lstrip("+")
    results = {}

    st, txt = await check_url(session, f"https://t.me/+{digits}")
    results["telegram"] = (
        "есть" if st == 200 and "tgme_page_title" in txt else "нет/скрыт"
    )

    st, txt = await check_url(session, f"https://wa.me/{digits}")
    results["whatsapp"] = (
        "есть" if st == 200 and "whatsapp" in txt.lower() else "нет"
    )

    st, txt = await check_url(session, f"https://viber.click/{digits}")
    results["viber"] = "есть" if st == 200 else "нет/неизвестно"

    return results


async def osint_report(raw):
    try:
        n = phonenumbers.parse(raw, None)
    except Exception:
        return "не понял номер, напиши +7XXXXXXXXXX"

    e164 = phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)

    lines = [
        f"<b>Номер:</b> <code>{e164}</code>",
        f"<b>Валиден:</b> {phonenumbers.is_valid_number(n)}",
        f"<b>Регион:</b> {geocoder.description_for_number(n, 'ru') or '—'}",
        f"<b>Оператор:</b> {carrier.name_for_number(n, 'ru') or '—'}",
        f"<b>Таймзона:</b> {', '.join(timezone.time_zones_for_number(n)) or '—'}",
        "",
    ]

    async with aiohttp.ClientSession(headers=HEADERS) as s:
        msgr = await check_messengers(s, e164)
        lines.append("<b>Мессенджеры:</b>")
        for k, v in msgr.items():
            lines.append(f"  • {k}: {v}")
        lines.append("")

        lines.append("<b>Упоминания в вебе:</b>")
        found = False
        for q in [f'"{e164}"', f'"{e164.lstrip("+")}"', f'"{raw}"']:
            res = await ddg_search(s, q)
            for title, href in res[:3]:
                lines.append(f"  • <a href='{href}'>{title[:60]}</a>")
                found = True
            if found:
                break
        if not found:
            lines.append("  • ничего не нашлось")

    return "\n".join(lines)


@dp.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "кинь номер: <code>+79991234567</code>\n"
        "ищу только в открытых источниках"
    )


@dp.message(F.text)
async def handle(m: Message):
    if m.text.startswith("/"):
        return
    await m.answer("⏳ ищу по открытым источникам...")
    report = await osint_report(m.text.strip())
    await m.answer(report, disable_web_page_preview=True)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())