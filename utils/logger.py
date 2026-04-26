# utils/logger.py

"""
Logger setup
"""

import logging
from pathlib import Path

def setup_logger(config=None):
    """Logger beállítása"""
    if config is None:
        config = {}
    
    log_level = config.get('level', 'INFO')
    log_file = config.get('file', 'logs/bot.log')
    
    # Log mappa létrehozása
    Path("logs").mkdir(exist_ok=True)
    
    # Logger konfiguráció
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)