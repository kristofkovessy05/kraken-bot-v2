# backtest.py - Gyors verzió (CSV-ből tölt)

import pandas as pd
import math
from datetime import datetime

class MarketMakerBacktest:
    def __init__(self, start_date, end_date, initial_balance=100):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.ohlcv = []
        
        # Bot paraméterek
        self.base_half_spread = 0.0035  # 0.35%
        self.min_half_spread = 0.00275
        self.maker_fee = 0.0025
        self.cooldown_seconds = 5
        self.target_ratio_base = 0.5
        self.max_skew = 0.001
        self.order_size_percent = 0.10

        # 🔥 MOMENTUM VÉDELEM (új)
        self.cooldown_seconds = 5
        self.ask_multiplier = 2.5
        self.bid_multiplier = 2.5
        self.min_distance_percent = 0.002
        
        self.last_filled_time = 0
        self.last_filled_side = None
        
        # Állapot
        self.usd_balance = initial_balance
        self.pepe_balance = 0
        self.total_profit = 0.0
        self.inventory = []
        self.bid_filled = 0
        self.ask_filled = 0
        self.trades = []

    def load_candles(self):
        """Betölti az előre legenerált OHLC CSV fájlt"""
        print(f"Adatok betöltése: pepe_1m_ohlc.csv")
        df = pd.read_csv('pepe_1m_ohlc.csv')
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # Szűrés a kívánt időszakra
        mask = (df['datetime'] >= self.start_date) & (df['datetime'] <= self.end_date)
        self.ohlcv = df[mask].reset_index(drop=True)
        
        print(f"✅ Kész: {len(self.ohlcv)} gyertya ({self.start_date.date()} - {self.end_date.date()})")
        return len(self.ohlcv) > 0

    def calculate_bid_ask(self, mid_price, current_pepe_ratio):
        """
        Mid price alapú árazás V3 (javított momentum védelemmel)
        """
        # ========== 1. MOMENTUM VÉDELEM ==========
        bid_multiplier = 1.0
        ask_multiplier = 1.0
        
        if self.last_filled_time:
            time_since_fill = (self.current_time - self.last_filled_time).total_seconds()
            
            if time_since_fill < self.cooldown_seconds:
                progress = time_since_fill / self.cooldown_seconds
                
                if self.last_filled_side == 'sell':  # ASK teljesült (eladás)
                    # BID közelebb (visszavétel), ASK távolabb
                    bid_multiplier = 0.5 + (0.5 * progress)   # 0.5 → 1.0
                    ask_multiplier = 1.5 + (0.5 * progress)   # 1.5 → 2.0
                    
                elif self.last_filled_side == 'buy':  # BID teljesült (vétel)
                    # ASK közelebb (eladás), BID távolabb
                    ask_multiplier = 0.5 + (0.5 * progress)   # 0.5 → 1.0
                    bid_multiplier = 1.5 + (0.5 * progress)   # 1.5 → 2.0
        
        # ========== 2. BASE SPREAD ==========
        final_bid_half = self.base_half_spread * bid_multiplier
        final_ask_half = self.base_half_spread * ask_multiplier
        
        # ========== 3. SKEW ==========
        deviation = current_pepe_ratio - self.target_ratio_base
        
        if abs(deviation) >= 0.5:
            skew_strength = self.max_skew
        else:
            skew_strength = self.max_skew * (abs(deviation) / 0.5)
        
        if deviation > 0:  # Több PEPE → ELADÁS
            final_bid_half = final_bid_half + skew_strength
            final_ask_half = final_ask_half - skew_strength
        else:  # Kevés PEPE → VÉTEL
            final_bid_half = final_bid_half - skew_strength
            final_ask_half = final_ask_half + skew_strength
        
        # ========== 4. MINIMUM SPREAD ==========
        min_required = self.maker_fee * 1.1
        final_bid_half = max(min_required, min(0.01, final_bid_half))
        final_ask_half = max(min_required, min(0.01, final_ask_half))
        
        # ========== 5. ÁRAK (MID PRICE ALAPJÁN) ==========
        raw_bid = mid_price * (1 - final_bid_half)
        raw_ask = mid_price * (1 + final_ask_half)
        
        # Tick size kerekítés
        tick_size = 0.000000001
        bid_price = round(math.floor(raw_bid / tick_size) * tick_size, 9)
        ask_price = round(math.ceil(raw_ask / tick_size) * tick_size, 9)
        
        if bid_price >= ask_price:
            bid_price = round(bid_price - tick_size, 9)
            ask_price = round(ask_price + tick_size, 9)
        
        return bid_price, ask_price

    def check_inventory_limits(self, side, current_pepe_ratio):
        """Kemény inventory limit"""
        MAX_BASE_RATIO = 0.70
        MIN_BASE_RATIO = 0.30
        
        if side == 'buy':
            if current_pepe_ratio > MAX_BASE_RATIO:
                return False
        else:
            if current_pepe_ratio < MIN_BASE_RATIO:
                return False
        return True
        
    def execute_order(self, side, price, amount, timestamp):
        """Order végrehajtása (FIFO profit számítással)"""
        cost = amount * price
        fee = cost * self.maker_fee
        
        if side == 'buy':
            self.usd_balance -= (cost + fee)
            self.pepe_balance += amount
            self.inventory.append({
                'amount': amount,
                'price': price,
                'fee': fee,
                'cost': cost + fee
            })
            self.bid_filled += 1
            print(f"  BID teljesült: {amount:.0f} @ {price:.9f} | USD: {self.usd_balance:.2f}, PEPE: {self.pepe_balance:.0f}")
            
        else:
            self.usd_balance += (cost - fee)
            self.pepe_balance -= amount
            
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
            self.ask_filled += 1
            print(f"  ASK teljesült: {amount:.0f} @ {price:.9f} | Profit: {trade_profit:.4f} | Total: {self.total_profit:.4f}")

        # 🔥 Frissítsd a momentum állapotokat
        self.last_filled_side = side
        self.last_filled_time = timestamp

        self.trades.append({
            'timestamp': timestamp,
            'side': side,
            'price': price,
            'amount': amount,
            'fee': fee,
            'usd_balance': self.usd_balance,
            'pepe_balance': self.pepe_balance,
            'total_profit': self.total_profit
        })
        
    def get_order_size(self, mid_price):
        """Dinamikus order méret"""
        total_value = self.usd_balance + (self.pepe_balance * mid_price)
        order_size = (total_value * self.order_size_percent) / mid_price if mid_price > 0 else 0
        return max(0, order_size)
        
    def run(self):
        """Futtatja a backtest-et"""
        print(f"\nBacktest indítása...")
        print(f"Kezdeti egyenleg: ${self.initial_balance:.2f} USD")
        print(f"Időszak: {self.start_date} - {self.end_date}")
        print(f"Adatpontok: {len(self.ohlcv)} gyertya")
        print("="*60)
        
        current_bid_order = None
        current_ask_order = None
        last_trade_time = 0
        
        for idx, row in self.ohlcv.iterrows():
            timestamp = row['datetime']
            mid_price = row['close']
            
            # 🔥 Átadjuk a current_time-t a momentum számításhoz
            self.current_time = timestamp
            
            total_value = self.usd_balance + (self.pepe_balance * mid_price)
            current_pepe_ratio = (self.pepe_balance * mid_price) / total_value if total_value > 0 else 0.5
            
            # Cooldown ellenőrzés
            if last_trade_time:
                time_diff = (timestamp - last_trade_time).total_seconds()
                if time_diff < self.cooldown_seconds:
                    continue
            
            # 🔥 Már nem kell best_bid/best_ask, csak mid_price
            bid_price, ask_price = self.calculate_bid_ask(mid_price, current_pepe_ratio)
            if bid_price is None or ask_price is None:
                continue
            
            order_size = self.get_order_size(mid_price)
            
            # Teljesülés ellenőrzés
            if current_bid_order and mid_price <= current_bid_order['price']:
                self.execute_order('buy', current_bid_order['price'], current_bid_order['amount'], timestamp)
                current_bid_order = None
                last_trade_time = timestamp
                continue
                
            if current_ask_order and mid_price >= current_ask_order['price']:
                self.execute_order('sell', current_ask_order['price'], current_ask_order['amount'], timestamp)
                current_ask_order = None
                last_trade_time = timestamp
                continue
            
            # Új order kihelyezés
            if current_bid_order is None:
                if self.check_inventory_limits('buy', current_pepe_ratio):
                    current_bid_order = {'price': bid_price, 'amount': order_size}
                    
            if current_ask_order is None:
                if self.check_inventory_limits('sell', current_pepe_ratio):
                    current_ask_order = {'price': ask_price, 'amount': order_size}
        
        print("\n" + "="*60)
        print("📊 BACKTEST EREDMÉNYEK")
        print("="*60)
        print(f"Kezdeti egyenleg: ${self.initial_balance:.2f}")
        print(f"Végső USD: ${self.usd_balance:.2f}")
        print(f"Végső PEPE: {self.pepe_balance:.0f}")
        if len(self.ohlcv) > 0:
            final_price = self.ohlcv.iloc[-1]['close']
            print(f"Portfólió értéke: ${self.usd_balance + (self.pepe_balance * final_price):.2f}")
        print(f"Realizált profit: ${self.total_profit:.4f}")
        print(f"BID teljesülések: {self.bid_filled}")
        print(f"ASK teljesülések: {self.ask_filled}")
        print(f"Összes trade: {len(self.trades)}")
        
        return self.total_profit

if __name__ == "__main__":
    # Teszteljünk 1 hetet 2024 októberéből
    start = datetime(2025, 10, 1)
    end = datetime(2025, 11, 1)
    
    bt = MarketMakerBacktest(start, end, initial_balance=100)
    
    if bt.load_candles():
        profit = bt.run()
        print(f"\n💰 Végeredmény: ${profit:.4f} profit")
    else:
        print("Backtest sikertelen: nincs adat")