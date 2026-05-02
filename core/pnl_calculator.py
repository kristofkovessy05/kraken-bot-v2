# core/pnl_calculator.py

"""
PnL Calculator - FIFO alapú profit számítás
"""

from datetime import datetime

class PnLCalculator:
    def __init__(self, base_currency, quote_currency):
        self.base_currency = base_currency
        self.quote_currency = quote_currency
        self.inventory = []
        self.total_profit = 0.0
        self.bid_filled = 0
        self.ask_filled = 0
    
    def _log_initial_inventory(self, amount, price):
        """Kezdeti inventory naplózása CSV-be"""
        try:
            import csv
            from pathlib import Path
            from datetime import datetime
            
            project_root = Path(__file__).parent.parent
            log_dir = project_root / "logs"
            log_dir.mkdir(exist_ok=True)
            
            csv_file = log_dir / "trades.csv"
            file_exists = csv_file.exists()
            
            trade_data = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'side': 'INITIAL_INVENTORY',
                'amount': amount,
                'price': price,
                'fee': 0,
                'fee_currency': self.quote_currency,
                'trade_ids': 'INITIAL',
                'realized_profit': '',  # Üres, mert nem realizált
                'total_profit': self.total_profit
            }
            
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=trade_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade_data)
            
            print(f"  📝 Kezdeti inventory naplózva: {amount} {self.base_currency} @ ${price}")
            
        except Exception as e:
            print(f"  ⚠️ Inventory naplózási hiba: {e}")

    def init_inventory(self, initial_base, current_price):
        """Kezdeti inventory beállítása (meglévő pozíció)"""
        if initial_base > 0 and current_price > 0:
            initial_cost = initial_base * current_price
            self.inventory = [{
                'amount': initial_base,
                'price': current_price,
                'fee': 0,
                'cost': initial_cost
            }]
            print(f"  🔍 Kezdeti inventory: {initial_base} {self.base_currency} @ ${current_price:.9f}")

            self._log_initial_inventory(initial_base, current_price)
    
    def add_buy(self, amount, price, fee, trade_ids):
        """BID teljesülés - hozzáadás a FIFO készlethez"""
        self.bid_filled += 1
        cost = amount * price + fee
        self.inventory.append({
            'amount': amount,
            'price': price,
            'fee': fee,
            'cost': cost
        })
        
        return {
            'side': 'BUY',
            'amount': amount,
            'price': price,
            'fee': fee,
            'trade_ids': trade_ids
        }
    
    def add_sell(self, amount, price, fee, trade_ids):
        """ASK teljesülés - FIFO profit számítás"""
        self.ask_filled += 1
        
        remaining = amount
        trade_profit = 0.0
        
        while remaining > 0 and self.inventory:
            oldest = self.inventory[0]
            sell_amount = min(remaining, oldest['amount'])
            
            buy_cost = oldest['cost'] * (sell_amount / oldest['amount'])
            sell_revenue = (sell_amount * price) - (fee * (sell_amount / amount))
            trade_profit += sell_revenue - buy_cost
            
            oldest['amount'] -= sell_amount
            oldest['cost'] -= buy_cost
            
            if oldest['amount'] <= 0:
                self.inventory.pop(0)
            
            remaining -= sell_amount
        
        self.total_profit += trade_profit
        
        return {
            'side': 'SELL',
            'amount': amount,
            'price': price,
            'fee': fee,
            'profit': trade_profit,
            'total_profit': self.total_profit,
            'trade_ids': trade_ids
        }
    
    def get_stats(self):
        """Visszaadja a PnL statisztikákat"""
        return {
            'total_profit': self.total_profit,
            'bid_filled': self.bid_filled,
            'ask_filled': self.ask_filled,
            'inventory_size': len(self.inventory),
            'inventory_value': sum(item['cost'] for item in self.inventory)
        }
    
    def get_unrealized_pnl(self, current_price):
        """Nem realizált PnL számítása a nyitott pozícióra"""
        if not self.inventory:
            return 0.0
        
        total_cost = sum(item['cost'] for item in self.inventory)
        total_amount = sum(item['amount'] for item in self.inventory)
        current_value = total_amount * current_price
        
        return current_value - total_cost
    
    def log_trade(self, side, amount, price, fee, trade_ids, profit=None):
        """Trade logolása CSV-be (adóbevalláshoz)"""
        try:
            import csv
            from pathlib import Path
            
            project_root = Path(__file__).parent.parent
            log_dir = project_root / "logs"
            log_dir.mkdir(exist_ok=True)
            
            csv_file = log_dir / "trades.csv"
            file_exists = csv_file.exists()
            
            trade_data = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'side': side,
                'amount': amount,
                'price': price,
                'fee': fee,
                'fee_currency': self.quote_currency,
                'trade_ids': ','.join(str(tid) for tid in trade_ids)
            }
            
            if side == 'SELL' and profit is not None:
                trade_data['realized_profit'] = profit
                trade_data['total_profit'] = self.total_profit
            
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=trade_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade_data)
            
        except Exception as e:
            print(f"  ⚠️ Logolási hiba: {e}")