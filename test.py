import pandas as pd
from datetime import datetime

df = pd.read_csv('PEPEUSD.csv', header=None)
df.columns = ['timestamp', 'price', 'volume']
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
df = df.sort_values('datetime')

print(f"Összes trade: {len(df)}")
print(f"Időszak: {df['datetime'].min()} - {df['datetime'].max()}")
print(f"\nElső 5 trade:")
print(df.head())
print(f"\nUtolsó 5 trade:")
print(df.tail())

# OHLC készítés
ohlc = df.resample('1min', on='datetime').agg({
    'price': ['first', 'max', 'min', 'last'],
    'volume': 'sum'
})
ohlc.columns = ['open', 'high', 'low', 'close', 'volume']
ohlc = ohlc.dropna()
print(f"\nOHLC gyertyák: {len(ohlc)}")
print(ohlc.head())