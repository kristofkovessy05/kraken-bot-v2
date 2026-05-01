# core/kraken_client.py

"""
Kraken API Client V3 
"""

import ccxt
import time

class KrakenClient:
    def __init__(self, api_key, api_secret, symbol, sandbox=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol
        
        self.exchange = ccxt.kraken({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        
        if sandbox:
            print("⚠️ Sandbox mód - valódi kereskedés NINCS")
    
    def _safe(self, func, *args, **kwargs):
        time.sleep(0.05)  # 50ms -> 20 req/sec
        return func(*args, **kwargs)
    
    def get_order_book(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        try:
            return self._safe(self.exchange.fetch_order_book, symbol)
        except Exception as e:
            print(f"❌ Order book hiba: {e}")
            return None
    
    def get_best_bid(self, symbol=None):
        orderbook = self.get_order_book(symbol)
        if orderbook and orderbook.get('bids') and len(orderbook['bids']) > 0:
            return orderbook['bids'][0][0]
        return None
    
    def get_best_ask(self, symbol=None):
        orderbook = self.get_order_book(symbol)
        if orderbook and orderbook.get('asks') and len(orderbook['asks']) > 0:
            return orderbook['asks'][0][0]
        return None
    
    def get_mid_price(self, symbol=None):
        bid = self.get_best_bid(symbol)
        ask = self.get_best_ask(symbol)
        if bid and ask and bid > 0 and ask > 0:
            return (bid + ask) / 2
        return None
    
    def place_limit_order(self, symbol, side, price, amount):
        try:
            order = self._safe(self.exchange.create_limit_order,
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                params={'postOnly': True}
            )
            if not order or 'id' not in order:
                print(f"❌ Order hiba: érvénytelen válasz")
                return None
            print(f"✅ Order kihelyezve: {side.upper()} {amount} {symbol} @ ${price:.8f}")
            return order
        except Exception as e:
            print(f"❌ Order hiba: {e}")
            return None
    
    def cancel_order(self, order_id, symbol):
        try:
            for attempt in range(3):
                self._safe(self.exchange.cancel_order, order_id, symbol)
                time.sleep(0.5)
                
                orders = self._safe(self.exchange.fetch_open_orders, symbol)
                still_open = [o for o in orders if o['id'] == order_id]
                
                if not still_open:
                    print(f"🗑️ Order törölve: {order_id}")
                    return True
                
                print(f"⚠️ Order még mindig kint, újra próbálkozom ({attempt + 1}/3)...")
            
            print(f"❌ Cancel sikertelen 3 próbálkozás után: {order_id}")
            return False
        except Exception as e:
            print(f"❌ Cancel hiba: {e}")
            return False
    
    def cancel_all_orders(self, symbol=None):
        try:
            orders = self._safe(self.exchange.fetch_open_orders)
            if symbol:
                orders = [o for o in orders if o['symbol'] == symbol]
            
            for o in orders:
                self._safe(self.exchange.cancel_order, o['id'])
            
            print(f"🗑️ {len(orders)} order törölve")
            return True
        except Exception as e:
            print(f"❌ Cancel all hiba: {e}")
            return False
    
    def get_open_orders(self, symbol=None):
        try:
            if symbol:
                orders = self._safe(self.exchange.fetch_open_orders, symbol)
            else:
                orders = self._safe(self.exchange.fetch_open_orders)
            
            if not orders:
                return []
            
            for order in orders:
                if order.get('price') is None or order['price'] == 0:
                    if 'info' in order and 'price' in order['info']:
                        order['price'] = float(order['info']['price'])
            
            return orders
        except Exception as e:
            print(f"❌ Open orders hiba: {e}")
            return []
    
    def get_balance(self, currency):
        try:
            balance = self._safe(self.exchange.fetch_balance)
            if currency not in balance:
                return {'free': 0, 'used': 0, 'total': 0}
            return {
                'free': balance[currency]['free'],
                'used': balance[currency]['used'],
                'total': balance[currency]['total']
            }
        except Exception as e:
            print(f"❌ Balance hiba: {e}")
            return None
    
    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            print(f"❌ Ticker hiba: {e}")
            return None
    
    def get_my_trades(self, symbol=None, since=None):
        try:
            if symbol is None:
                symbol = self.symbol
            
            if since is not None:
                since_ms = int(since * 1000)
            else:
                since_ms = None
            
            trades = self._safe(self.exchange.fetch_my_trades, symbol, since_ms)
            return trades if trades else []
        except Exception as e:
            print(f"❌ Trades lekérési hiba: {e}")
            return []