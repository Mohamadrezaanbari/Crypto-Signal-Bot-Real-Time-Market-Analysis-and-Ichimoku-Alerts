import aiohttp
import pandas as pd
import numpy as np
import asyncio
from telegram import Bot
from telegram.constants import ParseMode

# توکن و آیدی کانال تلگرام
TELEGRAM_TOKEN = '6977718762:AAGadKSZqghHAt_zGnTVB881ns1k2D4xAbw'
CHANNEL_ID = '@best_estrategy'

# تنظیم ربات تلگرام
bot = Bot(token=TELEGRAM_TOKEN)

# محدودیت در تعداد درخواست‌های همزمان
semaphore = asyncio.Semaphore(5)

async def send_message(message):
    async with semaphore:
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode=ParseMode.HTML)
            print(f"پیام ارسال شد: {message}")
        except Exception as e:
            print(f"Failed to send message: {e}")

async def get_top_gainers_spot():
    url = 'https://api.kucoin.com/api/v1/market/allTickers'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as response:
                response.raise_for_status()
                data = await response.json()
                if data and "data" in data and "ticker" in data["data"]:
                    tickers = data["data"]["ticker"]
                    top_gainers = sorted(
                        [ticker for ticker in tickers if 'USDT' in ticker['symbol'] and float(ticker['changeRate']) > 0],
                        key=lambda x: float(x['changeRate']), reverse=True
                    )[:50]  # 15 ارز برتر اسپات
                    return top_gainers
                else:
                    print("داده معتبر دریافت نشد.")
                    return []
    except Exception as e:
        print(f"Request failed: {e}")
        return []

def calculate_ichimoku(data):
    if len(data) < 52:
        return None, None
    high_prices = np.array(data['high'].values)
    low_prices = np.array(data['low'].values)
    senkou_span_b = (high_prices[-26:].max() + low_prices[-26:].min()) / 2
    kijun_sen = (high_prices[-52:].max() + low_prices[-52:].min()) / 2
    return kijun_sen, senkou_span_b

# دیکشنری برای ذخیره وضعیت قبلی کیجنسن و اسپن بی
previous_values = {}

async def process_symbol(session, symbol):
    url = f'https://api.kucoin.com/api/v1/market/candles?symbol={symbol}&type=1min&limit=100'
    try:
        async with session.get(url, timeout=20) as response:
            response.raise_for_status()
            data = await response.json()

            if not data or 'data' not in data:
                print(f"No kline data returned for {symbol}")
                return

            # مدیریت ستون‌های پویا بر اساس داده‌های API
            kline_data = data['data']
            if len(kline_data[0]) == 7:
                columns = ['timestamp', 'open', 'close', 'high', 'low', 'volume', 'close_time']
            elif len(kline_data[0]) == 12:
                columns = ['timestamp', 'open', 'close', 'high', 'low', 'volume', 
                           'close_time', 'quote_asset_volume', 'number_of_trades', 
                           'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore']
            else:
                print(f"Unexpected column structure for {symbol}: {len(kline_data[0])} columns")
                return

            df = pd.DataFrame(kline_data, columns=columns)
            df[['high', 'low', 'close']] = df[['high', 'low', 'close']].astype(float)

            kijun_sen, senkou_span_b = calculate_ichimoku(df)

            if kijun_sen is not None and senkou_span_b is not None:
                # دریافت وضعیت قبلی برای این نماد
                prev_kijun_sen, prev_senkou_span_b = previous_values.get(symbol, (None, None))

                # بررسی لحظه تقاطع: اگر در لحظه قبلی کیجنسن کمتر از اسپن بی بوده و اکنون بالاتر است
                if prev_kijun_sen is not None and prev_senkou_span_b is not None:
                    if prev_kijun_sen <= prev_senkou_span_b and kijun_sen > senkou_span_b:
                        await send_message(f"📈 سیگنال ایچیموکو: <b>کیجون‌سن</b> از <b>سنکو اسپن بی</b> عبور کرد برای {symbol}")

                # ذخیره وضعیت فعلی برای استفاده در بررسی‌های آینده
                previous_values[symbol] = (kijun_sen, senkou_span_b)

    except Exception as e:
        print(f"Error processing symbol {symbol}: {e}")

async def main():
    while True:
        # بارگیری و تحلیل داده‌ها برای ارزهای منتخب
        top_gainers = await get_top_gainers_spot()
        if top_gainers:
            async with aiohttp.ClientSession() as session:
                tasks = [process_symbol(session, ticker["symbol"]) for ticker in top_gainers]
                await asyncio.gather(*tasks)
        else:
            print("هیچ ارزی پیدا نشد.")
        
        # کاهش زمان بررسی مجدد برای تحلیل لحظه‌ای
        await asyncio.sleep(10)  # کاهش زمان به 10 ثانیه برای بررسی لحظه‌ای‌تر

if __name__ == "__main__":
    asyncio.run(main())
