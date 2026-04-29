# core/position_manager.py

"""
Position Manager - Rebalance és készletkezelés
"""

class PositionManager:
    def __init__(self, config, kraken_api, base_currency, quote_currency):
        self.api = kraken_api
        self.base_currency = base_currency
        self.quote_currency = quote_currency
        
        trading_config = config['trading']
        self.target_ratio_base = trading_config.get('target_ratio_base', 0.5)
        self.target_ratio_quote = trading_config.get('target_ratio_quote', 0.5)
        self.rebalance_threshold_percent = trading_config.get('rebalance_threshold_percent', 0.3)
        self.rebalance_multiplier_max = trading_config.get('rebalance_multiplier_max', 2.0)
        
        self.threshold_low = 1 - self.rebalance_threshold_percent
        self.threshold_high = 1 + self.rebalance_threshold_percent
        
        # Állapot
        self.last_known_balances = {base_currency: 0.0, quote_currency: 0.0}
    
    def update_balances(self, balances):
        """Frissíti az egyenlegeket"""
        self.last_known_balances = {
            self.quote_currency: balances.get(self.quote_currency, 0),
            self.base_currency: balances.get(self.base_currency, 0)
        }
    
    def get_current_balances(self):
        """Visszaadja a jelenlegi egyenlegeket"""
        return {
            self.base_currency: self.last_known_balances.get(self.base_currency, 0),
            self.quote_currency: self.last_known_balances.get(self.quote_currency, 0)
        }
    
    def update_balances_direct(self, base_balance, quote_balance):
        """Közvetlen balance frissítés trade után"""
        self.last_known_balances = {
            self.quote_currency: quote_balance,
            self.base_currency: base_balance
        }

    def check_inventory_limits(self, side, mid_price, base_order_size):
        """Kemény inventory limit (V3)"""
        current_base = self.last_known_balances.get(self.base_currency, 0)
        current_quote = self.last_known_balances.get(self.quote_currency, 0)
        total_value = current_quote + (current_base * mid_price) if mid_price > 0 else 0
        
        if total_value > 0:
            current_ratio = (current_base * mid_price) / total_value
        else:
            current_ratio = 0.5
        
        # 🔥 KEMÉNY LIMITEK
        MAX_BASE_RATIO = 0.70  # maximum 70% PEPE
        MIN_BASE_RATIO = 0.30  # minimum 30% PEPE
        
        if side == 'buy':  # vétel
            if current_ratio > MAX_BASE_RATIO:
                print(f"  🛑 TILTÁS: Túl sok PEPE ({current_ratio*100:.1f}% > 70%), vétel letiltva")
                return False, 0
        else:  # eladás
            if current_ratio < MIN_BASE_RATIO:
                print(f"  🛑 TILTÁS: Túl kevés PEPE ({current_ratio*100:.1f}% < 30%), eladás letiltva")
                return False, 0
        
        # Méret módosítás (ha az arány közelít a limithez)
        adjusted_size = base_order_size
        if side == 'buy' and current_ratio > 0.6:
            multiplier = (MAX_BASE_RATIO - current_ratio) / 0.1
            adjusted_size = base_order_size * max(0.2, min(1.0, multiplier))
        elif side == 'sell' and current_ratio < 0.4:
            multiplier = (current_ratio - MIN_BASE_RATIO) / 0.1
            adjusted_size = base_order_size * max(0.2, min(1.0, multiplier))
        
        return True, adjusted_size

    def has_sufficient_funds(self, side, mid_price, order_size):
        """Elegendő fedezet ellenőrzése"""
        if side == 'buy':
            current_quote = self.last_known_balances.get(self.quote_currency, 0)
            required = order_size * mid_price * 1.05  # 5% safety buffer
            return current_quote >= required
        else:  # sell
            current_base = self.last_known_balances.get(self.base_currency, 0)
            return current_base >= order_size
    
    def get_total_value(self, mid_price):
        """Teljes számla érték kiszámítása"""
        current_base = self.last_known_balances.get(self.base_currency, 0)
        current_quote = self.last_known_balances.get(self.quote_currency, 0)
        return current_quote + (current_base * mid_price) if mid_price > 0 else 0
    
    def get_targets(self, total_value, mid_price):
        """Cél értékek kiszámítása"""
        target_quote = total_value * self.target_ratio_quote
        target_base = (total_value * self.target_ratio_base) / mid_price if mid_price > 0 else 0
        return target_quote, target_base