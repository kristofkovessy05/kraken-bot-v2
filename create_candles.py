# create_candles.py
import pandas as pd
from datetime import datetime

print("Adatok betöltése a PEPEUSD.csv fájlból...")
df = pd.read_csv('PEPEUSD.csv', header=None)
df.columns = ['timestamp', 'price', 'volume']
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.sort_values('datetime')

print(f"Trade-ek száma: {len(df)}")
print(f"Időszak: {df['datetime'].min()} - {df['datetime'].max()}")

print("\nOHLC gyertyák készítése...")
ohlc = df.resample('1min', on='datetime').agg({
    'price': ['first', 'max', 'min', 'last'],
    'volume': 'sum'
})
ohlc.columns = ['open', 'high', 'low', 'close', 'volume']
ohlc = ohlc.dropna()
ohlc = ohlc.reset_index()

print(f"Gyertyák száma: {len(ohlc)}")
print(f"Időszak: {ohlc['datetime'].min()} - {ohlc['datetime'].max()}")

# CSV mentése
ohlc.to_csv('pepe_1m_ohlc.csv', index=False)
print("\n✅ Mentve: pepe_1m_ohlc.csv")
