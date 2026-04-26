import asyncio
from web3 import Web3
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import logging
from datetime import datetime
import os
import requests

# ================= KONFIGURASI =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

# ================= ADDRESS =================
FACTORY_ADDRESS = "0x8E9556415124b6C726D5C3610d25c24Be8AC2304"
USDT_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

RPC_URL = "https://bsc-dataseed1.binance.org"
DEX_URL = "https://dex.cryptoreceh.com/bsc"
PAIR_INFO_URL = "https://dex.cryptoreceh.com/info"
CREATE_TOKEN_URL = "https://app.cryptoreceh.com"
BANNER_URL = "https://raw.githubusercontent.com/recehdex/images/refs/heads/main/recehdex-banner-bsc.png"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= ABI =================
FACTORY_ABI = [
    {"inputs": [], "name": "allPairsLength", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "uint256"}], "name": "allPairs", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"}
]

PAIR_ABI = [
    {"inputs": [], "name": "getReserves", "outputs": [{"type": "uint112"}, {"type": "uint112"}, {"type": "uint32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token0", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"}
]

TOKEN_ABI = [
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"}
]

STABLE_ADDRESSES = [USDT_ADDRESS.lower(), WBNB_ADDRESS.lower()]

def get_token_info(token_address):
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except:
        return "Unknown", 18

def is_stable(token_address):
    return token_address.lower() in STABLE_ADDRESSES

def get_stable_type(stable_address):
    if stable_address.lower() == USDT_ADDRESS.lower():
        return "USDT"
    elif stable_address.lower() == WBNB_ADDRESS.lower():
        return "WBNB"
    return "Unknown"

def get_bnb_price_usd():
    """Cari harga BNB dari pair WBNB/USDT di factory"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair.functions.token0().call().lower()
                token1 = pair.functions.token1().call().lower()
                
                # Cari pair WBNB/USDT
                if (WBNB_ADDRESS.lower() in [token0, token1] and 
                    USDT_ADDRESS.lower() in [token0, token1]):
                    
                    reserves = pair.functions.getReserves().call()
                    
                    if token0 == WBNB_ADDRESS.lower():
                        wbnb_reserve = reserves[0] / 1e18
                        usdt_reserve = reserves[1] / 1e18
                    else:
                        wbnb_reserve = reserves[1] / 1e18
                        usdt_reserve = reserves[0] / 1e18
                    
                    if wbnb_reserve > 0:
                        bnb_price = usdt_reserve / wbnb_reserve
                        logger.info(f"BNB Price: ${bnb_price:.2f}")
                        return bnb_price
                        
            except:
                continue
                
        logger.warning("BNB price not found, using $600")
        return 600
        
    except Exception as e:
        logger.error(f"Error getting BNB price: {e}")
        return 600

def get_top_3_pairs():
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pairs: {total_pairs}")
        
        # Dapatkan harga BNB dulu
        bnb_price = get_bnb_price_usd()
        
        valid_pairs = []
        
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair.functions.token0().call().lower()
                token1 = pair.functions.token1().call().lower()
                reserves = pair.functions.getReserves().call()
                reserve0_raw = reserves[0]
                reserve1_raw = reserves[1]
                
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                # Skip jika tidak ada stable token
                if not (is_stable(token0) or is_stable(token1)):
                    continue
                
                # Tentukan mana stable token
                if is_stable(token0):
                    stable_address = token0
                    stable_symbol = token0_symbol
                    stable_decimals = token0_dec
                    stable_reserve_raw = reserve0_raw
                    token_address = token1
                    token_symbol = token1_symbol
                    token_decimals = token1_dec
                    token_reserve_raw = reserve1_raw
                else:
                    stable_address = token1
                    stable_symbol = token1_symbol
                    stable_decimals = token1_dec
                    stable_reserve_raw = reserve1_raw
                    token_address = token0
                    token_symbol = token0_symbol
                    token_decimals = token0_dec
                    token_reserve_raw = reserve0_raw
                
                stable_reserve = stable_reserve_raw / (10 ** stable_decimals)
                token_reserve = token_reserve_raw / (10 ** token_decimals)
                
                if token_reserve == 0:
                    continue
                
                stable_type = get_stable_type(stable_address)
                
                # HITUNG LIQUIDITY DALAM USD YANG BENAR
                if stable_type == "USDT":
                    # Pair TOKEN/USDT - USDT langsung 1:1 USD
                    price_usd = stable_reserve / token_reserve
                    liquidity_usd = stable_reserve * 2  # Total value pool dalam USD
                    
                else:  # WBNB
                    # Pair TOKEN/WBNB - perlu konversi WBNB ke USD
                    price_usd = (stable_reserve / token_reserve) * bnb_price
                    liquidity_usd = (stable_reserve * bnb_price) * 2
                
                if liquidity_usd > 0.01 and price_usd > 0:
                    valid_pairs.append({
                        "pair_name": f"{token_symbol}/{stable_symbol}",
                        "token_address": token_address,
                        "stable_address": stable_address,
                        "stable_type": stable_type,
                        "price": price_usd,
                        "liquidity": liquidity_usd,
                    })
                    
                    logger.info(f"{token_symbol}/{stable_symbol}: price=${price_usd:.8f}, liq=${liquidity_usd:.2f}")
                    
            except Exception as e:
                logger.error(f"Error pair {i}: {e}")
                continue
        
        valid_pairs.sort(key=lambda x: x['liquidity'], reverse=True)
        return valid_pairs[:3]
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return []

async def get_banner():
    try:
        response = requests.get(BANNER_URL, timeout=10)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

async def main():
    logger.info("=" * 50)
    logger.info("RecehDEX Bot - Top 3 Pairs")
    logger.info("=" * 50)
    
    if not w3.is_connected():
        logger.error("Cannot connect to BSC Chain")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    top_pairs = get_top_3_pairs()
    
    if not top_pairs:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No pairs found")
        return
    
    # Build message
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Format price
        price = pair['price']
        if price < 0.000001:
            price_str = f"{price:.12f}"
        elif price < 0.0001:
            price_str = f"{price:.10f}"
        elif price < 0.01:
            price_str = f"{price:.8f}"
        elif price < 1:
            price_str = f"{price:.6f}"
        else:
            price_str = f"{price:.4f}"
        
        # Hilangkan trailing zeros
        price_str = price_str.rstrip('0').rstrip('.')
        
        # Tambah satuan
        if pair['stable_type'] == "USDT":
            price_str = f"${price_str} USD"
        else:
            price_str = f"{price_str} BNB"
        
        # Format liquidity
        liq = pair['liquidity']
        if liq >= 1000:
            liq_str = f"${liq/1000:.2f}K"
        else:
            liq_str = f"${liq:.2f}"
        
        trade_url = f"{DEX_URL}?inputCurrency={pair['token_address']}&outputCurrency={pair['stable_address']}"
        
        message += f"<b>{idx}. {pair['pair_name']}</b>\n\n"
        message += f"   💰 Price: <code>{price_str}</code>\n"
        message += f"   💧 Liquidity: <code>{liq_str}</code>\n"
        message += f"   👉 <a href='{trade_url}'>Trade Now</a>\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    message += "💰 Data from RecehDEX on BSC"
    
    # Tombol
    keyboard = [
        [InlineKeyboardButton("📊 RecehDEX", url=DEX_URL)],
        [InlineKeyboardButton("ℹ️ PairInfo", url=PAIR_INFO_URL)],
        [InlineKeyboardButton("✨ CreateToken", url=CREATE_TOKEN_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Kirim
    banner = await get_banner()
    if banner:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=banner,
            caption=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    logger.info("Done")

if __name__ == "__main__":
    asyncio.run(main())
