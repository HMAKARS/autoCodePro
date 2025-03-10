import numpy as np
import pandas as pd

# 🎯 RSI 계산 함수
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]  # 최신 RSI 값 반환

# 🎯 MACD 계산 함수
def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    short_ema = prices.ewm(span=short_period, adjust=False).mean()
    long_ema = prices.ewm(span=long_period, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]  # 최신 MACD 값 반환

# 🎯 스토캐스틱 오실레이터 계산 함수
def calculate_stochastic(prices, high_prices, low_prices, period=14):
    lowest_low = low_prices.rolling(window=period).min()
    highest_high = high_prices.rolling(window=period).max()
    k = 100 * ((prices - lowest_low) / (highest_high - lowest_low))
    d = k.rolling(window=3).mean()
    return k.iloc[-1], d.iloc[-1]  # 최신 스토캐스틱 K, D 값 반환

# 🎯 이동평균선 (EMA) 계산
def calculate_ema(prices, period):
    return prices.ewm(span=period, adjust=False).mean().iloc[-1]

# 🎯 볼린저 밴드 계산
def calculate_bollinger_bands(prices, period=20):
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper_band = sma + (std * 2)
    lower_band = sma - (std * 2)
    return upper_band.iloc[-1], lower_band.iloc[-1]  # 최신 볼린저 밴드 값 반환

# 🎯 ATR (Average True Range) 계산
def calculate_atr(high_prices, low_prices, close_prices, period=14):
    tr1 = high_prices - low_prices
    tr2 = abs(high_prices - close_prices.shift())
    tr3 = abs(low_prices - close_prices.shift())
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr.iloc[-1]  # 최신 ATR 값 반환
