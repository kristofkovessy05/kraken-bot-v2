# core/market_maker.py

"""
Market Maker V3
"""

import time
import math

class MarketMaker:
    def __init__(self, config, kraken_api, notifier=None):
        self.config = config
        self.api = kraken_api
        self.notifier = notifier
        
        trading_config = config['trading']
        self.symbol = trading_config['symbol']
        
        # 🔥 SPREAD BEÁLLÍTÁSOK
        self.base_half_spread = trading_config.get('base_half_spread', 0.0035)
        self.min_half_spread = trading_config.get('min_half_spread', 0.00275)
        self.max_half_spread = trading_config.get('max_half_spread', 0.01)
        
        # 🔥 MOMENTUM VÉDELEM
        momentum_config = trading_config.get('momentum', {})
        self.cooldown_seconds = momentum_config.get('cooldown_seconds', 5)
        self.ask_multiplier = momentum_config.get('ask_multiplier', 2.5)
        self.bid_multiplier = momentum_config.get('bid_multiplier', 2.5)
        
        # 🔥 REBALANCE
        self.target_ratio_base = trading_config.get('target_ratio_base', 0.5)
        self.target_ratio_quote = trading_config.get('target_ratio_quote', 0.5)
        self.max_skew = trading_config.get('max_skew', 0.001)
        
        self.order_size_percent = trading_config.get('order_size_percent', 0.10)
        self.interval = trading_config.get('interval_seconds', 5)
        
        # Pénznemek
        self.base_currency = self.symbol.split('/')[0]
        self.quote_currency = self.symbol.split('/')[1]
        
        # DÍJAK
        self.maker_fee = trading_config.get('maker_fee', 0.0025)
        
        # VOLATILITÁS (opcionális)
        vol_config = trading_config.get('volatility', {})
        self.atr_period = vol_config.get('atr_period', 14)
        self.atr_extra_multiplier = vol_config.get('atr_extra_multiplier', 0)
        
        # ÁLLAPOT VÁLTOZÓK
        self.is_running = False
        self.current_bid_order = None
        self.current_ask_order = None
        
        # Hibakezelés
        self.error_count = 0
        self.max_errors = 10
        
        # Árak nyomon követése
        self.price_history = []
        self.last_filled_price = None
        self.last_filled_side = None
        self.last_filled_time = 0
        
        # Napi veszteség
        self.daily_loss_percent = trading_config.get('daily_loss_percent', 3.0)  # 3% alapból
        self.daily_start_portfolio_value = 0.0
        self.daily_start_time = time.time()

        # Napi veszteség utáni szünet
        self.is_paused = False
        self.pause_until = 0
        
        # Tick size
        self.tick_size = self._get_tick_size()
        self.decimals = self._calculate_decimals()
        
        # Order size cache
        self.order_size = 0.0001
        self.min_order_size = self._get_min_order_size()
        
        # Cache
        self.last_open_orders_check = 0
        self.cached_bid_order = None
        self.cached_ask_order = None
        
        # MODULOK
        from core.position_manager import PositionManager
        from core.pnl_calculator import PnLCalculator
        
        self.position_manager = PositionManager(config, kraken_api, self.base_currency, self.quote_currency)
        self.pnl_calculator = PnLCalculator(self.base_currency, self.quote_currency)
        
        # Kezdeti szinkronizáció
        self._sync_balances()
        self._init_inventory()
        
        self.stats = {
            'start_time': time.time(),
            'errors': 0,
        }
        
        self._print_init_info()

    def _get_tick_size(self):
        tick_sizes = {
            'BTC/USD': 0.1,
            'ETH/USD': 0.01,
            'SOL/USD': 0.01,
            'JUP/USD': 0.000001,
            'ADA/USD': 0.000001,
            'DOT/USD': 0.0001,
            'LINK/USD': 0.00001,
            'PEPE/USD': 0.000000001,
            'TAO/USD': 0.0001, 
        }
        return tick_sizes.get(self.symbol, 0.01)
    
    def _calculate_decimals(self):
        if self.tick_size >= 0.1:
            return 2
        elif self.tick_size >= 0.01:
            return 3
        elif self.tick_size >= 0.001:
            return 4
        elif self.tick_size >= 0.00001:
            return 6
        else:
            return 9
    
    def get_current_portfolio_value(self, mid_price):
        """Aktuális portfólió érték kiszámítása"""
        balances = self.position_manager.get_current_balances()
        current_base = balances.get(self.base_currency, 0)
        current_quote = balances.get(self.quote_currency, 0)
        return current_quote + (current_base * mid_price)

    def _get_min_order_size(self):
        try:
            markets = self.api.exchange.load_markets()
            if self.symbol in markets:
                return markets[self.symbol]['limits']['amount']['min']
            return 0.0001
        except Exception:
            return 0.0001
    
    def _sync_balances(self):
        """Egyenlegek szinkronizálása"""
        quote_balance = self.api.get_balance(self.quote_currency)
        base_balance = self.api.get_balance(self.base_currency)
        
        if quote_balance and base_balance:
            balances = {
                self.quote_currency: quote_balance['free'],
                self.base_currency: base_balance['free']
            }
            self.position_manager.update_balances(balances)
            return True
        return False
    
    def _init_inventory(self):
        """Kezdeti inventory beállítása"""
        current_price = self.api.get_mid_price(self.symbol)
        if current_price:
            balances = self.position_manager.get_current_balances()
            initial_base = balances.get(self.base_currency, 0)
            self.pnl_calculator.init_inventory(initial_base, current_price)
    
    def _print_init_info(self):
        print(f"📏 Tick size: {self.tick_size} (decimals: {self.decimals})")
        print(f"💰 Pár: {self.symbol}")
        print(f"🎯 Alap spread: {self.base_half_spread*2*100:.2f}% (fél: {self.base_half_spread*100:.2f}%)")
        print(f"🛡️ Momentum védelem: {self.cooldown_seconds}s, ASK x{self.ask_multiplier}, BID x{self.bid_multiplier}")
        print(f"⚖️ Rebalance max skew: {self.max_skew*100:.2f}%")
        print(f"💰 Maker díj: {self.maker_fee*100:.2f}%")
        
    # ========== 🔥 BID/ASK SZÁMÍTÁS (MID PRICE ALAPJÁN) ==========
    
    def calculate_bid_ask(self):
        best_bid = self.api.get_best_bid(self.symbol)
        best_ask = self.api.get_best_ask(self.symbol)
        
        if best_bid is None or best_ask is None:
            return None, None, None
        
        mid_price = (best_bid + best_ask) / 2
        
        # ========== 1. BASE SPREAD ==========
        final_bid_half = self.base_half_spread
        final_ask_half = self.base_half_spread
        
        # ========== 2. 🔥 MOMENTUM VÉDELEM (ideiglenes, cooldown alatt) ==========
        momentum_bid_mult = 1.0
        momentum_ask_mult = 1.0
        
        if self.last_filled_time:
            time_since_fill = time.time() - self.last_filled_time
            if time_since_fill < self.cooldown_seconds:
                # Lineáris csökkenés: a cooldown végére 1x-es lesz
                progress = 1 - (time_since_fill / self.cooldown_seconds)
                
                if self.last_filled_side == 'sell':  # ASK teljesült
                    # ASK spread NÖVEXIK (ne adjunk el még egyet)
                    momentum_ask_mult = 1 + (self.ask_multiplier - 1) * progress
                    # BID spread CSÖKKEN kicsit (hogy vonzóbb legyen a vétel - de ez opcionális)
                    momentum_bid_mult = 1 - (self.bid_multiplier - 1) * progress * 0.3
                    momentum_bid_mult = max(0.7, momentum_bid_mult)
                else:  # BID teljesült
                    # BID spread NÖVEXIK (ne vegyünk még egyet)
                    momentum_bid_mult = 1 + (self.bid_multiplier - 1) * progress
                    # ASK spread CSÖKKEN kicsit
                    momentum_ask_mult = 1 - (self.ask_multiplier - 1) * progress * 0.3
                    momentum_ask_mult = max(0.7, momentum_ask_mult)
                
                final_bid_half *= momentum_bid_mult
                final_ask_half *= momentum_ask_mult
        
        # ========== 3. ⚖️ REBALANCING (inventory skew, folyamatos) ==========
        balances = self.position_manager.get_current_balances()
        current_base = balances.get(self.base_currency, 0)
        current_quote = balances.get(self.quote_currency, 0)
        total_value = current_quote + (current_base * mid_price)
        
        if total_value > 0:
            base_ratio = (current_base * mid_price) / total_value
            deviation = base_ratio - self.target_ratio_base  # cél: 0.5
        else:
            deviation = 0
        
        # 🔥 HASZNÁLD A CONFIG-BÓL A MAX_SKEW-T!
        max_skew = self.max_skew  # alapból 0.001 a config-ban, de érdemes nagyobbra venni
        # JAVASLAT: max_skew = 0.005  # 0.5%
        
        # Skew erőssége - a deviáció arányában (max 50% eltérésnél éri el a max_skew-t)
        skew_strength = max_skew * min(1.0, abs(deviation) / 0.5)
        
        # Skew alkalmazása (additív módon, mivel ez a half spread-re megy)
        if deviation > 0:  # Túl sok PEPE -> eladás felé kell tolni
            final_bid_half += skew_strength   # BID spread NÖVEXIK (olcsóbban veszünk)
            final_ask_half -= skew_strength   # ASK spread CSÖKKEN (olcsóbban adunk el)
        else:  # Túl kevés PEPE -> vétel felé kell tolni
            final_bid_half -= skew_strength   # BID spread CSÖKKEN (drágábban veszünk)
            final_ask_half += skew_strength   # ASK spread NÖVEXIK (drágábban adunk el)
        
        # ========== 4. MINIMUM SPREAD ==========
        min_required = self.maker_fee * 1.1  # 0.275%
        final_bid_half = max(min_required, min(self.max_half_spread, final_bid_half))
        final_ask_half = max(min_required, min(self.max_half_spread, final_ask_half))
        
        # ========== 5. ÁRAK ==========
        raw_bid = best_bid * (1 - final_bid_half)
        raw_ask = best_ask * (1 + final_ask_half)
        
        # Tick size kerekítés
        bid_price = round(math.floor(raw_bid / self.tick_size) * self.tick_size, self.decimals)
        ask_price = round(math.ceil(raw_ask / self.tick_size) * self.tick_size, self.decimals)
        
        if bid_price >= ask_price:
            bid_price = round(bid_price - self.tick_size, self.decimals)
            ask_price = round(ask_price + self.tick_size, self.decimals)
        
        current_spread = (ask_price - bid_price) / mid_price if mid_price > 0 else 0
        
        return bid_price, ask_price, current_spread

    def _calculate_volatility_extra(self, mid_price):
        """ATR alapú extra spread (opcionális, később bekapcsolható)"""
        if self.atr_extra_multiplier <= 0:
            return 0
        
        self.price_history.append(mid_price)
        if len(self.price_history) > self.atr_period + 5:
            self.price_history.pop(0)
        
        if len(self.price_history) < self.atr_period + 1:
            return 0
        
        # 🔥 JAVÍTOTT VERZIÓ - csak mid price alapján
        tr_values = []
        for i in range(1, len(self.price_history)):
            current = self.price_history[i]
            previous = self.price_history[i-1]
            
            # Mivel nincs high/low adatunk, a true range = |current - previous|
            true_range = abs(current - previous)
            tr_values.append(true_range)
        
        if len(tr_values) < self.atr_period:
            return 0
        
        atr = sum(tr_values[-self.atr_period:]) / self.atr_period
        volatility_pct = atr / mid_price if mid_price > 0 else 0
        
        extra = volatility_pct * self.atr_extra_multiplier
        return min(extra, 0.005)  # Maximum 0.5% extra
    
    # ========== ORDER MANAGEMENT ==========
    
    def get_dynamic_order_size(self, mid_price):
        """Dinamikus order méret számítás"""
        total_value = self.position_manager.get_total_value(mid_price)
        dynamic_size = (total_value * self.order_size_percent) / mid_price if mid_price > 0 else self.order_size
        
        if dynamic_size < self.min_order_size:
            dynamic_size = self.min_order_size
        
        return round(dynamic_size, 8)
    
    def get_open_orders_from_api(self):
        """Nyitott order-ek lekérése cache-el"""
        try:
            if time.time() - self.last_open_orders_check > 5:
                orders = self.api.get_open_orders(self.symbol)
                self.last_open_orders_check = time.time()
                
                bid_order = None
                ask_order = None
                for order in orders:
                    price = order.get('price')
                    if price is None or price == 0:
                        if 'info' in order and 'price' in order['info']:
                            price = float(order['info']['price'])
                            order['price'] = price
                    
                    if order['side'] == 'buy':
                        bid_order = order
                    elif order['side'] == 'sell':
                        ask_order = order
                
                self.cached_bid_order = bid_order
                self.cached_ask_order = ask_order
            
            return self.cached_bid_order, self.cached_ask_order
        except Exception as e:
            print(f"⚠️ Open orders lekérési hiba: {e}")
            return None, None
    
    def check_filled_orders(self):
        """Teljesülések ellenőrzése"""
        try:
            if 'last_trade_time' not in self.stats:
                all_trades = self.api.get_my_trades(self.symbol, since=None)
                if all_trades:
                    last_trade = max(all_trades, key=lambda x: x['timestamp'])
                    self.stats['last_trade_time'] = int(last_trade['timestamp'] / 1000) + 1
                else:
                    self.stats['last_trade_time'] = int(time.time()) - 60
            
            new_trades = self.api.get_my_trades(self.symbol, since=self.stats['last_trade_time'])
            if not new_trades:
                return True
            
            latest_time = max(t['timestamp'] for t in new_trades)
            self.stats['last_trade_time'] = int(latest_time / 1000) + 1
            
            # Order ID alapú összevonás
            order_map = {}
            for trade in new_trades:
                order_id = trade.get('order')
                if order_id not in order_map:
                    order_map[order_id] = {
                        'side': trade.get('side'),
                        'amount': 0,
                        'cost': 0,
                        'fee': 0,
                        'price': trade.get('price'),
                        'trade_ids': []
                    }
                order_map[order_id]['amount'] += trade.get('amount')
                order_map[order_id]['cost'] += trade.get('cost', 0)
                order_map[order_id]['fee'] += trade.get('fee', {}).get('cost', 0)
                order_map[order_id]['trade_ids'].append(trade.get('id'))
            
            # Trade-ek feldolgozása
            for order_id, trade_data in order_map.items():
                side = trade_data['side']
                amount = trade_data['amount']
                price = trade_data['price']
                fee = trade_data['fee']
                trade_ids = trade_data['trade_ids']
                
                # 🔥 CSERE: Az eredeti V1 kód helyett:
                self.last_filled_price = price
                self.last_filled_side = side  # 'buy' vagy 'sell'
                self.last_filled_time = time.time()
                
                if side == 'sell':
                    result = self.pnl_calculator.add_sell(amount, price, fee, trade_ids)
                    self._print_sell_result(result)
                    self.pnl_calculator.log_trade('SELL', amount, price, fee, trade_ids, result['profit'])
                    
                    if self.notifier:
                        self.notifier.send_message(
                            f"✅ ASK TELJESÜLT\n─────────────────\n"
                            f"💰 Eladás: {amount:.6f} {self.base_currency}\n"
                            f"💵 Ár: ${price:,.{self.decimals}f}\n"
                            f"📈 Profit: ${result['profit']:.4f}\n"
                            f"💰 Összes: ${result['total_profit']:.4f}"
                        )
                else:
                    result = self.pnl_calculator.add_buy(amount, price, fee, trade_ids)
                    self._print_buy_result(result)
                    self.pnl_calculator.log_trade('BUY', amount, price, fee, trade_ids)
                    
                    if self.notifier:
                        self.notifier.send_message(
                            f"✅ BID TELJESÜLT\n─────────────────\n"
                            f"💰 Vétel: {amount:.6f} {self.base_currency}\n"
                            f"💵 Ár: ${price:,.{self.decimals}f}\n"
                            f"💸 Díj: ${fee:.4f}"
                        )
            
            # Order szinkronizáció
            if self.current_bid_order or self.current_ask_order:
                existing_bid, existing_ask = self.get_open_orders_from_api()
                if self.current_bid_order and not existing_bid:
                    self.current_bid_order = None
                if self.current_ask_order and not existing_ask:
                    self.current_ask_order = None
            
            # Egyenleg frissítés
            self._sync_balances()
            
            return True
        except Exception as e:
            print(f"⚠️ Teljesülés ellenőrzési hiba: {e}")
            return False
    
    def _print_sell_result(self, result):
        print(f"\n✅ ASK TELJESÜLT! {result['amount']:.6f} @ ${result['price']:.{self.decimals}f} (díj: ${result['fee']:.4f})")
        print(f"   📊 Körönkénti profit: ${result['profit']:.4f}")
        print(f"   📊 Összesített profit: ${result['total_profit']:.4f}")
    
    def _print_buy_result(self, result):
        print(f"\n✅ BID TELJESÜLT! {result['amount']:.6f} @ ${result['price']:.{self.decimals}f} (díj: ${result['fee']:.4f})")
    
    def ensure_orders(self, mid_price):
        """Biztosítja, hogy mindkét order kint van"""
        try:            
            # 🔥 TELJESÜLÉSEK ELLENŐRZÉSE (minden ciklusban)
            self.check_filled_orders()

            # Várakozás teljesülés után
            if self.last_filled_time and (time.time() - self.last_filled_time) < self.cooldown_seconds:
                return

            bid_price, ask_price, current_spread = self.calculate_bid_ask()
            if bid_price is None or ask_price is None:
                return
            
            # Dinamikus order méret
            self.order_size = self.get_dynamic_order_size(mid_price)
            
            # Meglévő order-ek lekérése
            existing_bid, existing_ask = self.get_open_orders_from_api()
            
            # Dinamikus refresh threshold az ATR alapján
            if self.atr_extra_multiplier > 0 and len(self.price_history) > self.atr_period:
                atr = self._calculate_volatility_extra(mid_price)
                refresh_threshold = max(0.0015, min(0.003, atr * 2))
            else:
                refresh_threshold = 0.002  # 0.2% alapból
            
            needs_bid = False
            needs_ask = False
            final_bid_size = self.order_size
            final_ask_size = self.order_size
            
            # --- BID oldal ellenőrzése ---
            if not existing_bid:
                can_buy, adjusted_size = self.position_manager.check_inventory_limits('buy', mid_price, self.order_size)
                if can_buy and self.position_manager.has_sufficient_funds('buy', mid_price, adjusted_size):
                    needs_bid = True
                    final_bid_size = adjusted_size
            else:
                # Ár elmozdulás ellenőrzés
                price_diff_pct = (bid_price - existing_bid['price']) / existing_bid['price']
                if price_diff_pct > refresh_threshold:
                    print(f"  🔄 BID frissítés (ár változás: {price_diff_pct*100:.2f}%)...")
                    if self.cancel_order_and_clear_cache(existing_bid['id'], self.symbol):
                        can_buy, adjusted_size = self.position_manager.check_inventory_limits('buy', mid_price, self.order_size)
                        if can_buy:
                            needs_bid = True
                            final_bid_size = adjusted_size
            
            # --- ASK oldal ellenőrzése ---
            if not existing_ask:
                can_sell, adjusted_size = self.position_manager.check_inventory_limits('sell', mid_price, self.order_size)
                if can_sell and self.position_manager.has_sufficient_funds('sell', mid_price, adjusted_size):
                    needs_ask = True
                    final_ask_size = adjusted_size
            else:
                price_diff_pct = (existing_ask['price'] - ask_price) / existing_ask['price']
                if price_diff_pct > refresh_threshold:
                    print(f"  🔄 ASK frissítés (ár változás: {price_diff_pct*100:.2f}%)...")
                    if self.cancel_order_and_clear_cache(existing_ask['id'], self.symbol):
                        can_sell, adjusted_size = self.position_manager.check_inventory_limits('sell', mid_price, self.order_size)
                        if can_sell:
                            needs_ask = True
                            final_ask_size = adjusted_size
            
            # --- Új order-ek kihelyezése ---
            if needs_bid:
                self.current_bid_order = self.api.place_limit_order(self.symbol, 'buy', bid_price, final_bid_size)
                if self.current_bid_order and self.notifier:
                    total_value = self.position_manager.get_total_value(mid_price)
                    target_quote, _ = self.position_manager.get_targets(total_value, mid_price)
                    current_quote = self.position_manager.get_current_balances()[self.quote_currency]
                    self.notifier.send_message(
                        f"🟢 Új BID order\n─────────────────\n"
                        f"💰 Vétel: {final_bid_size:.6f} {self.base_currency}\n"
                        f"💵 Ár: ${bid_price:,.{self.decimals}f}\n"
                        f"🎯 Cél USD: ${target_quote:.0f} (most: ${current_quote:.0f})"
                    )
            
            if needs_ask:
                self.current_ask_order = self.api.place_limit_order(self.symbol, 'sell', ask_price, final_ask_size)
                if self.current_ask_order and self.notifier:
                    total_value = self.position_manager.get_total_value(mid_price)
                    _, target_base = self.position_manager.get_targets(total_value, mid_price)
                    current_base = self.position_manager.get_current_balances()[self.base_currency]
                    self.notifier.send_message(
                        f"🔴 Új ASK order\n─────────────────\n"
                        f"💰 Eladás: {final_ask_size:.6f} {self.base_currency}\n"
                        f"💵 Ár: ${ask_price:,.{self.decimals}f}\n"
                        f"🎯 Cél {self.base_currency}: {target_base:.6f} (most: {current_base:.6f})"
                    )
            
            # ========== NAPI DRAWDOWN ELLENŐRZÉS ==========
            current_time = time.time()

            # Új nap? (24 óra eltelt)
            if current_time - self.daily_start_time > 86400:
                self.daily_start_time = current_time
                self.daily_start_portfolio_value = self.get_current_portfolio_value(mid_price)
                print(f"\n📅 Új nap - induló portfólió érték: ${self.daily_start_portfolio_value:.2f}")
                # 🔥 HA SZÜNETELT, FOLYTASSUK
                if self.is_paused:
                    print(f"🟢 Bot újraindulva a napi limit után!")
                    self.is_paused = False
                    if self.notifier:
                        self.notifier.send_message(f"🟢 Bot újraindult a napi limit letelte után.\n💰 Portfólió: ${self.daily_start_portfolio_value:.2f}")

            # Ha szünetel, ne csináljunk semmit
            if self.is_paused:
                return

            # Százalékos drawdown számítás
            if self.daily_start_portfolio_value > 0:
                current_value = self.get_current_portfolio_value(mid_price)
                daily_return_pct = ((current_value - self.daily_start_portfolio_value) / self.daily_start_portfolio_value) * 100
                
                if daily_return_pct <= -self.daily_loss_percent:
                    print(f"\n🔴 NAPI DRAWDOWN HATÁR ELÉRVE! {daily_return_pct:.2f}% (limit: -{self.daily_loss_percent}%)")
                    self.is_paused = True
                    self.pause_until = time.time() + 86400  # 24 óra múlva
                    if self.notifier:
                        self.notifier.send_message(
                            f"🔴 NAPI DRAWDOWN HATÁR!\n"
                            f"📉 Hozam: {daily_return_pct:.2f}%\n"
                            f"💰 Portfólió: ${self.daily_start_portfolio_value:.2f} → ${current_value:.2f}\n"
                            f"⏸️ Bot szünetel 24 óráig.\n🟢 Holnap automatikusan újraindul."
                        )
                    # Szünetelés a nap hátralévő részében
                    while self.is_paused and time.time() < self.pause_until:
                        time.sleep(60)  # Ellenőrizzük percenként
                        # Ellenőrizzük, hogy eljött-e az új nap
                        if time.time() >= self.pause_until:
                            print(f"\n📅 Új nap - bot újraindul...")
                            self.daily_start_time = time.time()
                            self.daily_start_portfolio_value = self.get_current_portfolio_value(mid_price)
                            self.is_paused = False
                            if self.notifier:
                                self.notifier.send_message(f"🟢 Bot újraindult.\n💰 Portfólió: ${self.daily_start_portfolio_value:.2f}")
                            break
            
        except Exception as e:
            print(f"⚠️ Hiba az ensure_orders-ben: {e}")
            self.error_count += 1
            if self.error_count >= self.max_errors:
                self.stop()
    
    def print_status(self, mid_price, bid_price, ask_price, current_spread):
        """Aktuális állapot kiírása"""
        existing_bid, existing_ask = self.get_open_orders_from_api()
        bid_status = "✅" if existing_bid else "❌"
        ask_status = "✅" if existing_ask else "❌"
        
        balances = self.position_manager.get_current_balances()
        current_base = balances.get(self.base_currency, 0)
        current_quote = balances.get(self.quote_currency, 0)
        
        total_value = self.position_manager.get_total_value(mid_price)
        
        runtime = int(time.time() - self.stats['start_time'])
        hours = runtime // 3600
        minutes = (runtime % 3600) // 60
        seconds = runtime % 60
        
        # 🔥 A TÉNYLEGESEN KINT LÉVŐ ORDER-ek half spread-je
        bid_half = 0
        ask_half = 0
        if existing_bid and mid_price > 0:
            bid_half = (mid_price - existing_bid['price']) / mid_price * 100
        if existing_ask and mid_price > 0:
            ask_half = (existing_ask['price'] - mid_price) / mid_price * 100
        
        print(f"\r"
            f"📊 ${mid_price:,.{self.decimals}f} | "
            f"{bid_status}B:${existing_bid['price'] if existing_bid else 0:,.{self.decimals}f}({bid_half:.2f}%) | "
            f"{ask_status}A:${existing_ask['price'] if existing_ask else 0:,.{self.decimals}f}({ask_half:.2f}%) | "
            f"Spread:{current_spread*100:.2f}% | "
            f"PnL:${self.pnl_calculator.total_profit:.4f} | "
            f"💰 {self.quote_currency}:${current_quote:.0f}/{self.base_currency}:{current_base:.6f} | "
            f"📈 {hours:02d}:{minutes:02d}:{seconds:02d}",
            end="", flush=True)
    
    def cancel_order_and_clear_cache(self, order_id, symbol):
        """Order törlése cache törléssel együtt"""
        if self.api.cancel_order(order_id, symbol):
            # Cache törlése
            self.cached_bid_order = None
            self.cached_ask_order = None
            if self.current_bid_order and self.current_bid_order['id'] == order_id:
                self.current_bid_order = None
            if self.current_ask_order and self.current_ask_order['id'] == order_id:
                self.current_ask_order = None
            return True
        return False

    def cancel_all_orders(self):
        """Összes order törlése"""
        self.api.cancel_all_orders(self.symbol)
        self.current_bid_order = None
        self.current_ask_order = None
    
    def run(self):
        """Bot indítása (polling mód)"""
        self.is_running = True
        
        print("\n" + "="*60)
        print("🚀 KRAKEN MARKET MAKER BOT INDÍTVA")
        print(f"📊 Üzemmód: Mid price alapú, aszimmetrikus momentum védelemmel")
        print(f"🎯 Alap spread: {self.base_half_spread*2*100:.2f}%")
        print(f"🛡️ Momentum védelem: {self.cooldown_seconds}s, ASK x{self.ask_multiplier}, BID x{self.bid_multiplier}")
        print("="*60 + "\n")
        
        self._sync_balances()
        balances = self.position_manager.get_current_balances()
        print(f"💰 Kezdeti egyenleg - {self.quote_currency}: ${balances.get(self.quote_currency, 0):.2f}, {self.base_currency}: {balances.get(self.base_currency, 0):.6f}")
        print("="*60)
        
        while self.is_running:
            try:
                # Mid price lekérése (csak status-hoz és order size számításhoz)
                mid_price = self.api.get_mid_price(self.symbol)
                
                if mid_price is None:
                    print("⚠️ Várakozás árfolyamra...", end="\r")
                    time.sleep(1)
                    continue
                
                # Order-ek biztosítása
                self.ensure_orders(mid_price)
                
                # Árak lekérése a megjelenítéshez
                bid_price, ask_price, current_spread = self.calculate_bid_ask()
                if bid_price and ask_price:
                    self.print_status(mid_price, bid_price, ask_price, current_spread)
                
                time.sleep(self.interval)
                
            except KeyboardInterrupt:
                print("\n🛑 Kilépés kérve...")
                break
            except Exception as e:
                print(f"\n❌ Váratlan hiba: {e}")
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    print(f"🔴 Túl sok hiba ({self.error_count}), leállás...")
                    break
                time.sleep(5)
        
        self.stop()
    
    def stop(self):
        """Bot leállítása"""
        print("\n🛑 Bot leállítása...")
        self.is_running = False
        self.cancel_all_orders()
        
        print("\n" + "="*60)
        print("📊 ZÁRÓ STATISZTIKA:")
        stats = self.pnl_calculator.get_stats()
        print(f"   🔥 FIFO alapú profit: ${stats['total_profit']:.4f}")
        print(f"   BID teljesülések (vétel): {stats['bid_filled']}")
        print(f"   ASK teljesülések (eladás): {stats['ask_filled']}")
        
        # Nem realizált PnL
        current_price = self.api.get_mid_price(self.symbol)
        if current_price:
            unrealized = self.pnl_calculator.get_unrealized_pnl(current_price)
            print(f"   Nem realizált PnL: ${unrealized:.4f}")
        
        runtime = int(time.time() - self.stats['start_time'])
        print(f"   Futási idő: {runtime // 3600}h {(runtime % 3600) // 60}m {runtime % 60}s")
        print("="*60)
        
        if self.notifier:
            if stats['ask_filled'] > 0:
                message = (
                    f"🛑 BOT LEÁLLÍTVA V3\n─────────────────\n"
                    f"💰 FIFO profit: ${stats['total_profit']:.4f}\n"
                    f"📊 ASK teljesülések: {stats['ask_filled']}\n"
                    f"📈 BID teljesülések: {stats['bid_filled']}\n"
                    f"⏱️ Futási idő: {runtime // 3600}h {(runtime % 3600) // 60}m {runtime % 60}s"
                )
            else:
                message = f"🛑 BOT LEÁLLÍTVA V3\n─────────────────\n⚠️ Nincs ASK teljesülés"
            self.notifier.send_message(message)
        
        print("✅ Bot leállítva")