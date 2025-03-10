import pandas as pd
import requests
import numpy as np
import time
from datetime import datetime, timedelta
from itertools import product
import os

def mainAI():
    """ ✅ 다중 종목에 대해 AI 기반 최적 매매 전략 탐색 """
    coins = get_top_trade_coins()  # ✅ 상위 거래량 10개 코인 가져오기
    best_results = []

    for coin in coins:
        market = coin["market"]
        print(f"🔍 {market} 백테스트 시작...")
        df = get_historical_data(market)
        df = apply_technical_indicators(df)

        # ✅ 개별 종목 최적 매매 전략 찾기
        best_config, best_profit = optimize_strategy(df)
        print(f"🔥 {market} 최적 전략: {best_config} | 예상 수익률: {best_profit:.2f}%")
        best_results.append((market, best_config, best_profit))

    # ✅ 수익률이 가장 높은 코인 찾기
    best_results.sort(key=lambda x: x[2], reverse=True)  # 수익률 기준 정렬
    best_coin = best_results[0]
    print(f"🏆 최적의 매매 대상: {best_coin[0]} | 전략: {best_coin[1]} | 예상 수익률: {best_coin[2]:.2f}%")

    return best_results  # ✅ 최적의 종목 및 전략 반환

def get_top_trade_coins():
    """ ✅ 업비트 API에서 거래량 상위 10개 코인 가져오기 """
    server_url = "https://api.upbit.com"

    params = {
        "markets": "KRW-BTC,KRW-ETH"
    }

    res = requests.get(server_url + "/v1/ticker", params=params)

    try:
        rres = requests.get(server_url + "/v1/ticker", params=params)
        data = rres.json()

        # ✅ 디버깅: 응답 데이터 확인
        print("📊 API 응답 데이터:", data)

        # ✅ 응답이 리스트인지 확인
        if not isinstance(data, list):
            raise ValueError(f"❌ API 응답 형식 오류: {type(data)} -> {data}")

        # ✅ 거래량 기준 상위 10개 코인 선정
        top_coins = sorted(data, key=lambda x: x.get("acc_trade_price_24h", 0), reverse=True)[:10]

        return [{"market": coin["market"], "trade_price": coin["trade_price"]} for coin in top_coins]

    except requests.exceptions.RequestException as e:
        print(f"❌ API 요청 실패: {e}")
        return []
    except ValueError as e:
        print(f"❌ 데이터 파싱 오류: {e}")
        return []

def optimize_strategy(df):
    """ ✅ 여러 RSI, MACD 조합을 테스트하고 최적의 조합을 찾는 함수 """
    best_config = None
    best_profit = -9999

    rsi_ranges = [(25, 70), (28, 72), (30, 75)]
    macd_ranges = [(12, 26, 9), (10, 24, 8), (14, 30, 10)]
    stop_loss_levels = [0.98, 0.97]
    take_profit_levels = [1.02, 1.03]

    for rsi_range, macd_setting, stop_loss, take_profit in product(rsi_ranges, macd_ranges, stop_loss_levels, take_profit_levels):
        df = apply_technical_indicators(df, macd_setting, rsi_range)
        profit = backtest_strategy(df, rsi_range, macd_setting, stop_loss, take_profit)

        if profit > best_profit:
            best_profit = profit
            best_config = (rsi_range, macd_setting, stop_loss, take_profit)

    return best_config, best_profit

def backtest_strategy(df, rsi_range, macd_setting, stop_loss, take_profit):
    """ ✅ RSI + MACD + 손절/익절 기반 백테스트 실행 """
    initial_balance = 1000000  # 100만원
    balance = initial_balance
    position = 0
    buy_price = 0

    for i in range(len(df)):
        if df["rsi"].iloc[i] < rsi_range[0] and df["macd"].iloc[i] > df["macd_signal"].iloc[i]:
            if position == 0:
                buy_price = df["trade_price"].iloc[i]
                position = balance / buy_price
                balance = 0

        elif df["rsi"].iloc[i] > rsi_range[1] and df["macd"].iloc[i] < df["macd_signal"].iloc[i]:
            if position > 0:
                sell_price = df["trade_price"].iloc[i]
                balance = position * sell_price
                position = 0

        if position > 0 and df["trade_price"].iloc[i] < buy_price * stop_loss:
            sell_price = df["trade_price"].iloc[i]
            balance = position * sell_price
            position = 0

        if position > 0 and df["trade_price"].iloc[i] > buy_price * take_profit:
            sell_price = df["trade_price"].iloc[i]
            balance = position * sell_price
            position = 0

    final_balance = balance if position == 0 else position * df["trade_price"].iloc[-1]
    return (final_balance / initial_balance - 1) * 100  # 최종 수익률

def apply_technical_indicators(df, macd_setting=(12, 26, 9), rsi_range=(30, 70)):
    """ ✅ 기술적 지표 추가 """
    df = calculate_rsi(df, rsi_range)
    df = calculate_macd(df, macd_setting)
    return df

def calculate_rsi(df, rsi_range, period=14):
    """ ✅ RSI 계산 """
    delta = df["trade_price"].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period, min_periods=1).mean()
    avg_loss = pd.Series(loss).rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df

def calculate_macd(df, macd_setting):
    """ ✅ MACD 계산 """
    short, long, signal = macd_setting
    df["ema_short"] = df["trade_price"].ewm(span=short, adjust=False).mean()
    df["ema_long"] = df["trade_price"].ewm(span=long, adjust=False).mean()
    df["macd"] = df["ema_short"] - df["ema_long"]
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    return df

"""
def get_historical_data(market, interval="15", count=200, max_requests=10):
    #✅ 중복 없는 캔들 데이터 가져오기 (최대 max_requests번 요청) 
    url = f"https://api.upbit.com/v1/candles/minutes/{interval}"
    all_data = []
    to = None  # 마지막 캔들 시간을 저장할 변수

    for _ in range(max_requests):
        params = {'market': market, 'count': count}
        if to:
            params['to'] = to  # ✅ 이전 요청의 마지막 시간 사용
        response = requests.get(url, params=params)
        data = response.json()

        if not isinstance(data, list) or "error" in data:
            print(f"❌ API 에러 발생: {data}")
            break

        # ✅ 중복 방지: 마지막 데이터 이전 데이터만 요청하기 위해 `to` 값 업데이트
        to = data[-1]["candle_date_time_utc"]

        # ✅ 기존 데이터와 중복되는지 체크 후 추가
        new_data = [d for d in data if d["candle_date_time_utc"] not in [d["candle_date_time_utc"] for d in all_data]]
        all_data.extend(new_data)

        time.sleep(0.5)  # 요청 간격 조절

    # ✅ DataFrame 변환 및 정리
    df = pd.DataFrame(all_data)
    df["time"] = pd.to_datetime(df["candle_date_time_kst"])  # KST 시간 변환
    df = df[["time", "opening_price", "high_price", "low_price", "trade_price", "candle_acc_trade_volume"]]

    return df
"""
def get_historical_data(market, interval="15", count=200, to=None):
    """ 업비트에서 특정 마켓의 과거 데이터를 가져오는 함수 """
    url = f"https://api.upbit.com/v1/candles/minutes/{interval}"
    headers = {"Accept": "application/json"}

    params = {"market": market, "count": count}
    if to:
        params["to"] = to.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    for _ in range(3):  # ✅ 최대 3번까지 재시도
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"⚠️ API 요청 실패, 재시도 중... (응답 코드: {response.status_code})")
        time.sleep(2)  # 2초 대기 후 재시도

    return []  # 3번 시도 후에도 실패하면 빈 리스트 반환

def fetch_all_data(market, save_path="data/"):
    """ 15분봉 데이터를 가능한 한 오래 수집하여 CSV로 저장 """
    all_data = []
    to_time = datetime.utcnow()  # 최신 데이터부터 시작
    max_no_data_count = 5  # ✅ 연속 5번 데이터가 없으면 종료
    no_data_count = 0
    data_count = 0

    while data_count < 1000:

        data = get_historical_data(market, to=to_time)
        data_count += 1

        if not data:
            no_data_count += 1
            print(f"⚠️ {market} 데이터 없음 ({no_data_count}/{max_no_data_count})")
            if no_data_count >= max_no_data_count:
                print(f"🛑 {market} 데이터 수집 중단 (연속 {max_no_data_count}회 데이터 없음)")
                break
            time.sleep(1)
            continue

        no_data_count = 0  # 데이터가 들어오면 카운트 초기화

        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["candle_date_time_kst"])  # KST 기준 시간 변환
        df = df[["time", "opening_price", "high_price", "low_price", "trade_price", "candle_acc_trade_volume"]]

        all_data.append(df)

        try:
            to_time = datetime.strptime(data[-1]["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S") - timedelta(minutes=15)
        except Exception as e:
            print(f"❌ to_time 업데이트 오류: {e}")
            break  # 오류 발생 시 루프 종료

        print(f"📊 {market} - {len(all_data) * 200}개 데이터 수집 중...")

        time.sleep(0.3)  # ✅ API 요청 제한 준수

    # 데이터 합치기 및 저장
    # 저장할 폴더 경로
    save_path = "/Users/hongbookpro/Downloads/"

    # 디렉토리 없으면 생성
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    final_df = pd.concat(all_data, ignore_index=True)
    final_df.to_csv(f"{save_path}{market}_15m_data.csv", index=False)

    print(f"✅ {market} 데이터 저장 완료! ({len(final_df)}개 캔들)")

if __name__ == "__main__":
    fetch_all_data("KRW-BTC")



