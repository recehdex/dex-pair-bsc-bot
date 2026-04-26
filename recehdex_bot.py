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
USD_ADDRESS = "0x55d398326f99059fF775485246999027B3197955"  # BSC USDT
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
BUSD_ADDRESS = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"  # BUSD untuk alternatif

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

# ================= HELPER FUNCTIONS =================
STABLE_ADDRESSES = [USD_ADDRESS.lower(), WBNB_ADDRESS.lower(), BUSD_ADDRESS.lower()]

def get_token_info(token_address):
    """Get token symbol and decimals"""
    try:
        token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=TOKEN_ABI)
        return token.functions.symbol().call(), token.functions.decimals().call()
    except Exception as e:
        logger.error(f"Error getting token info for {token_address}: {e}")
        return "Unknown", 18

def is_stable(token_address):
    """Check if token is a stablecoin or WBNB"""
    return token_address.lower() in STABLE_ADDRESSES

def get_stable_type(stable_address):
    """Get type of stable token"""
    if stable_address.lower() == USD_ADDRESS.lower():
        return "USDT"
    elif stable_address.lower() == BUSD_ADDRESS.lower():
        return "BUSD"
    elif stable_address.lower() == WBNB_ADDRESS.lower():
        return "WBNB"
    return "Unknown"

def get_bnb_price_from_factory():
    """Get BNB price in USD from WBNB/USDT or WBNB/BUSD pair"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        
        bnb_price = None
        
        for i in range(total_pairs):
            try:
                pair_address = factory.functions.allPairs(i).call()
                pair = w3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                
                token0 = pair.functions.token0().call().lower()
                token1 = pair.functions.token1().call().lower()
                
                # Check for WBNB/USDT or WBNB/BUSD pair
                if (WBNB_ADDRESS.lower() in [token0, token1]):
                    if USD_ADDRESS.lower() in [token0, token1] or BUSD_ADDRESS.lower() in [token0, token1]:
                        reserves = pair.functions.getReserves().call()
                        
                        # Get decimals
                        wbnb_decimals = 18
                        stable_decimals = 18  # USDT and BUSD both have 18 decimals on BSC
                        
                        # Determine which is WBNB and which is stable
                        if token0 == WBNB_ADDRESS.lower():
                            wbnb_reserve_raw = reserves[0]
                            stable_reserve_raw = reserves[1]
                        else:
                            wbnb_reserve_raw = reserves[1]
                            stable_reserve_raw = reserves[0]
                        
                        wbnb_reserve = wbnb_reserve_raw / (10 ** wbnb_decimals)
                        stable_reserve = stable_reserve_raw / (10 ** stable_decimals)
                        
                        if wbnb_reserve > 0:
                            bnb_price = stable_reserve / wbnb_reserve
                            logger.info(f"BNB Price found: ${bnb_price:.2f}")
                            return bnb_price
                            
            except Exception as e:
                logger.error(f"Error checking pair {i} for BNB price: {e}")
                continue
        
        logger.warning("BNB price not found, using fallback price $600")
        return 600  # fallback price
        
    except Exception as e:
        logger.error(f"Error getting BNB price: {e}")
        return 600

def get_top_3_pairs_with_stable():
    """Get top 3 pairs by liquidity in USD"""
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(FACTORY_ADDRESS), abi=FACTORY_ABI)
        total_pairs = factory.functions.allPairsLength().call()
        logger.info(f"Total pairs in factory: {total_pairs}")
        
        # Get BNB price first
        bnb_price_usd = get_bnb_price_from_factory()
        logger.info(f"Using BNB price: ${bnb_price_usd:.2f}")
        
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
                
                # Get token info
                token0_symbol, token0_dec = get_token_info(token0)
                token1_symbol, token1_dec = get_token_info(token1)
                
                # Skip if no stable token in pair
                if not (is_stable(token0) or is_stable(token1)):
                    continue
                
                # Determine which token is stable
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
                
                # Convert reserves to human readable
                stable_reserve = stable_reserve_raw / (10 ** stable_decimals)
                token_reserve = token_reserve_raw / (10 ** token_decimals)
                
                if token_reserve == 0:
                    continue
                
                stable_type = get_stable_type(stable_address)
                
                # Calculate price in USD
                if stable_type == "USDT" or stable_type == "BUSD":
                    # Stablecoin harganya 1 USD
                    price_in_usd = stable_reserve / token_reserve
                    # Liquidity in USD = (stable_reserve * 2) because stable = 1 USD
                    liquidity_usd = stable_reserve * 2
                    
                elif stable_type == "WBNB":
                    # Need to convert WBNB to USD
                    price_in_usd = (stable_reserve / token_reserve) * bnb_price_usd
                    # Liquidity in USD = (WBNB reserve in USD) * 2
                    liquidity_usd = (stable_reserve * bnb_price_usd) * 2
                    
                else:
                    # Unknown stable type, skip
                    logger.warning(f"Unknown stable type: {stable_type} for {stable_address}")
                    continue
                
                # Only include pairs with positive liquidity and price
                if liquidity_usd > 0.01 and price_in_usd > 0:
                    valid_pairs.append({
                        "pair_name": f"{token_symbol}/{stable_symbol}",
                        "token_symbol": token_symbol,
                        "token_address": token_address,
                        "stable_symbol": stable_symbol,
                        "stable_address": stable_address,
                        "stable_type": stable_type,
                        "price": price_in_usd,
                        "liquidity": liquidity_usd,
                        "token_reserve": token_reserve,
                        "stable_reserve": stable_reserve,
                    })
                    
                    logger.info(f"{token_symbol}/{stable_symbol}: price=${price_in_usd:.8f}, liq=${liquidity_usd:.2f}")
                    
            except Exception as e:
                logger.error(f"Error processing pair {i}: {e}")
                continue
        
        # Sort by liquidity (highest first) and take top 3
        valid_pairs.sort(key=lambda x: x['liquidity'], reverse=True)
        logger.info(f"Found {len(valid_pairs)} valid pairs, showing top 3")
        
        return valid_pairs[:3]
        
    except Exception as e:
        logger.error(f"Error in get_top_3_pairs_with_stable: {e}")
        return []

async def get_banner():
    """Download banner image from GitHub"""
    try:
        response = requests.get(BANNER_URL, timeout=10)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.error(f"Error downloading banner: {e}")
    return None

def format_price(price, stable_type):
    """Format price with appropriate decimal places"""
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
    
    # Remove trailing zeros
    price_str = price_str.rstrip('0').rstrip('.')
    
    # Add unit
    if stable_type == "USDT" or stable_type == "BUSD":
        return f"${price_str} USD"
    else:
        return f"{price_str} BNB"

def format_liquidity(liquidity):
    """Format liquidity with appropriate prefix"""
    if liquidity >= 1_000_000:
        return f"${liquidity/1_000_000:.2f}M"
    elif liquidity >= 1_000:
        return f"${liquidity/1_000:.2f}K"
    elif liquidity >= 1:
        return f"${liquidity:.2f}"
    else:
        return f"${liquidity:.4f}"

async def main():
    logger.info("=" * 50)
    logger.info("RecehDEX Bot - Top 3 Pairs (Fixed Version)")
    logger.info("=" * 50)
    
    # Check connection
    if not w3.is_connected():
        logger.error("Cannot connect to BSC Chain")
        return
    
    # Initialize bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Get top pairs
    top_pairs = get_top_3_pairs_with_stable()
    
    if not top_pairs:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text="⚠️ No pairs found or error fetching data"
        )
        return
    
    # Build message
    message = "🏆 <b>RECEHDEX - TOP 3 PAIRS</b>\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, pair in enumerate(top_pairs, 1):
        # Format price and liquidity
        price_str = format_price(pair['price'], pair['stable_type'])
        liq_str = format_liquidity(pair['liquidity'])
        
        # Build trade URL
        trade_url = f"{DEX_URL}?inputCurrency={pair['token_address']}&outputCurrency={pair['stable_address']}"
        
        # Add to message
        message += f"<b>{idx}. {pair['pair_name']}</b>\n\n"
        message += f"   💰 Price: <code>{price_str}</code>\n"
        message += f"   💧 Liquidity: <code>{liq_str}</code>\n"
        message += f"   👉 <a href='{trade_url}'>Trade Now</a>\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    message += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
    message += "💰 Data from RecehDEX on BSC\n"
    message += "📊 Liquidity calculated in USD"
    
    # Create inline keyboard
    keyboard = [
        [InlineKeyboardButton("📊 RecehDEX", url=DEX_URL)],
        [InlineKeyboardButton("ℹ️ Pair Info", url=PAIR_INFO_URL)],
        [InlineKeyboardButton("✨ Create Token", url=CREATE_TOKEN_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with banner
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
    
    logger.info("Message sent successfully")

if __name__ == "__main__":
    asyncio.run(main())
