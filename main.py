# main.py

#!/usr/bin/env python3
"""
Market Maker Bot V3 - Last Bid/Ask alapú kereskedés
"""

import os
import sys
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.kraken_client import KrakenClient
from core.market_maker import MarketMaker
from utils.notifier import TelegramNotifier
from utils.logger import setup_logger

def load_config():
    """Betölti a konfigurációkat a config mappából"""
    config_path = project_root / "config" / "settings.yaml"
    env_path = project_root / "config" / ".env"
    
    if not config_path.exists():
        print(f"❌ settings.yaml nem található: {config_path}")
        sys.exit(1)
    
    if not env_path.exists():
        print(f"❌ .env nem található: {env_path}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    load_dotenv(env_path)
    
    # API kulcsok betöltése
    config['api'] = {
        'key': os.getenv('KRAKEN_API_KEY'),
        'secret': os.getenv('KRAKEN_API_SECRET'),
    }
    
    config['telegram'] = {
        'token': os.getenv('TELEGRAM_BOT_TOKEN'),
        'chat_id': os.getenv('TELEGRAM_CHAT_ID'),
    }
    
    return config

def main():
    print("🚀 MARKET MAKER BOT V3 INDÍTÁSA")
    print("📊 Last Bid/Ask alapú kereskedés")
    print("=" * 60)
    
    # Konfiguráció betöltése
    config = load_config()
    
    # Logger beállítása
    logger = setup_logger(config.get('logging', {}))
    
    # Telegram notifier (opcionális)
    notifier = None
    telegram_config = config.get('telegram', {})
    if telegram_config.get('token') and telegram_config.get('chat_id'):
        notifier = TelegramNotifier(
            token=telegram_config['token'],
            chat_id=telegram_config['chat_id']
        )
        notifier.send_message("🤖 MARKET MAKER BOT V3 INDÍTVA\n📊 Last Bid/Ask alapú kereskedés")
    
    # Kraken client
    api = KrakenClient(
        api_key=config['api']['key'],
        api_secret=config['api']['secret'],
        symbol=config['trading']['symbol'],
        sandbox=config.get('sandbox', True)
    )
    
    # Market Maker
    mm = MarketMaker(
        config=config,
        kraken_api=api,
        notifier=notifier
    )
    
    try:
        mm.run()
    except KeyboardInterrupt:
        print("\n🛑 Kilépés kérve...")
        mm.stop()
    except Exception as e:
        print(f"\n❌ Váratlan hiba: {e}")
        if notifier:
            notifier.send_message(f"❌ KRITIKUS HIBA: {e}")
        mm.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()