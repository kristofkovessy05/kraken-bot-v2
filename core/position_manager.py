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
    
    def check_inventory_limits(self, side, mid_price, base_order_size):
        """
        Ellenőrzi a készlet limitet és visszaadja a módosított order méretet.
        🔥 NINCS TILTÁS! Csak méret módosítás és figyelmeztetés.
        Returns: (can_trade, adjusted_size)
        """
        current_base = self.last_known_balances.get(self.base_currency, 0)
        current_quote = self.last_known_balances.get(self.quote_currency, 0)
        total_value = current_quote + (current_base * mid_price) if mid_price > 0 else 0
        
        target_quote = total_value * self.target_ratio_quote
        target_base = (total_value * self.target_ratio_base) / mid_price if mid_price > 0 else 0
        
        adjusted_size = base_order_size
        # 🔥 MINDIG ENGEDÉLYEZZÜK!
        can_trade = True
        
        if side == 'sell':  # ASK - eladás
            if current_base < target_base * self.threshold_low:
                # Csak figyelmeztetés, NEM TILTÁS!
                print(f"  ⚠️ REBALANCE: Kevés {self.base_currency} ({current_base:.6f} < {target_base * self.threshold_low:.6f})")
            elif current_base > target_base * self.threshold_high:
                multiplier = min(self.rebalance_multiplier_max, current_base / target_base)
                adjusted_size = base_order_size * multiplier
                print(f"  🔄 REBALANCE: ASK méret x{multiplier:.1f}")
        
        elif side == 'buy':  # BID - vétel
            if current_quote < target_quote * self.threshold_low:
                # Csak figyelmeztetés, NEM TILTÁS!
                print(f"  ⚠️ REBALANCE: Kevés {self.quote_currency} (${current_quote:.2f} < ${target_quote * self.threshold_low:.2f})")
            elif current_quote > target_quote * self.threshold_high:
                multiplier = min(self.rebalance_multiplier_max, current_quote / target_quote)
                adjusted_size = base_order_size * multiplier
                print(f"  🔄 REBALANCE: BID méret x{multiplier:.1f}")
        
        return can_trade, adjusted_size
    
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