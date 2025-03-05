# trading/utils.py

import requests
import jwt
import uuid
import numpy as np
import time
from django.conf import settings

def get_account_info():
    """ ✅ 업비트 전체 계좌 조회 API 호출 """
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY

    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
    }

    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    headers = {"Authorization": f"Bearer {jwt_token}"}

    url = "https://api.upbit.com/v1/accounts"
    response = requests.get(url, headers=headers)

    return response.json() if response.status_code == 200 else {"error": response.json()}

def get_krw_market_coin_info():
    """ ✅ 원화(KRW) 시장의 모든 코인 정보 조회 """
    markets_url = "https://api.upbit.com/v1/market/all"
    ticker_url = "https://api.upbit.com/v1/ticker"

    markets_response = requests.get(markets_url)
    if markets_response.status_code != 200:
        return {"error": markets_response.json()}

    krw_markets = [m["market"] for m in markets_response.json() if m["market"].startswith("KRW-")]
    ticker_response = requests.get(ticker_url, params={"markets": ",".join(krw_markets)})

    if ticker_response.status_code != 200:
        return {"error": ticker_response.json()}

    return sorted([
        {
            "market": ticker["market"],
            "trade_price": ticker["trade_price"],
            "signed_change_rate": ticker["signed_change_rate"],
            "acc_trade_price_24h": ticker["acc_trade_price_24h"],
        } for ticker in ticker_response.json()
    ], key=lambda x: x["acc_trade_price_24h"], reverse=True)

def upbit_order(market, side, volume=None, price=None, ord_type="limit"):
    """ ✅ 업비트 주문 실행 함수 """
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY

    payload = {"market": market, "side": side, "ord_type": ord_type, "nonce": str(uuid.uuid4())}
    if ord_type == "price":
        payload["price"] = str(price)
    elif ord_type == "market":
        payload["volume"] = str(volume)

    jwt_token = jwt.encode(payload, secret_key, algorithm="HS256")
    headers = {"Authorization": f"Bearer {jwt_token}"}
    response = requests.post("https://api.upbit.com/v1/orders", headers=headers, json=payload)

    return response.json() if response.status_code == 201 else {"error": response.json()}

def get_rsi(market, period=14, max_retries=3):
    """ ✅ RSI(상대강도지수) 계산 (API 요청 제한 고려) """
    url = f"https://api.upbit.com/v1/candles/minutes/1?market={market}&count={period+1}"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                raise ValueError(f"API 응답 실패 (HTTP {response.status_code})")

            response_json = response.json()
            if not isinstance(response_json, list) or len(response_json) < period + 1:
                raise ValueError("API 응답 데이터 부족")

            prices = [candle.get("trade_price", 0) for candle in response_json if isinstance(candle, dict)]
            if len(prices) < period + 1:
                raise ValueError("RSI 계산에 필요한 데이터 부족")

            gains = [max(0, prices[i] - prices[i-1]) for i in range(1, len(prices))]
            losses = [max(0, prices[i-1] - prices[i]) for i in range(1, len(prices))]

            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)

            if avg_loss == 0:
                return 100  # ✅ 손실이 없으면 RSI는 100

            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"⚠️ {market} RSI 요청 실패: {str(e)} (재시도 {attempt+1}/{max_retries})")
            time.sleep(1)

    return None  # ✅ 최종 실패 시 `None` 반환

def get_volatility(market):
    """ ✅ 최근 1시간 변동성 체크 (API 요청 최적화) """
    url = f"https://api.upbit.com/v1/candles/minutes/60?market={market}&count=1"

    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            print(f"⚠️ {market} 변동성 요청 실패 (HTTP {response.status_code})")
            return None  # ✅ 요청 실패 시 None 반환

        response_json = response.json()
        if not isinstance(response_json, list) or len(response_json) == 0:
            print(f"⚠️ {market} 변동성 데이터 없음")
            return None  # ✅ 데이터 없음 처리

        high = response_json[0].get("high_price")
        low = response_json[0].get("low_price")

        if high is None or low is None:
            return None  # ✅ 데이터가 없을 경우 None 반환

        avg = (high + low) / 2
        return ((high - low) / avg) * 100  # 변동률 %

    except requests.exceptions.RequestException as e:
        print(f"⚠️ {market} 변동성 요청 실패: {str(e)}")
        return None  # ✅ 네트워크 오류 발생 시 None 반환
