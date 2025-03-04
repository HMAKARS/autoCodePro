# trading/utils.py
import requests
import jwt
import uuid
from django.conf import settings

def get_account_info():
    """ 업비트 전체 계좌 조회 API 호출 """
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
    """ KRW 마켓에서 상위 5개 코인 조회 """
    markets_url = "https://api.upbit.com/v1/market/all"
    ticker_url = "https://api.upbit.com/v1/ticker"

    markets_response = requests.get(markets_url).json()
    krw_markets = [m["market"] for m in markets_response if m["market"].startswith("KRW-")]

    ticker_response = requests.get(ticker_url, params={"markets": ",".join(krw_markets)}).json()

    coin_info_list = [{
        "market": ticker["market"],
        "trade_price": ticker["trade_price"],
        "signed_change_rate": ticker["signed_change_rate"],
        "acc_trade_price_24h": ticker["acc_trade_price_24h"],
    } for ticker in ticker_response]

    return sorted(coin_info_list, key=lambda x: (x["acc_trade_price_24h"], x["signed_change_rate"]), reverse=True)[:5]

def upbit_order(market, side, volume=None, price=None, ord_type="limit"):
    """ 업비트 주문 API 호출 (매수/매도) """
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY

    payload = {
        "market": market,
        "side": side,
        "ord_type": ord_type,
        "nonce": str(uuid.uuid4())
    }

    if ord_type == "price":
        payload["price"] = price
    elif ord_type == "market":
        payload["volume"] = volume

    jwt_token = jwt.encode(payload, secret_key, algorithm="HS256")
    headers = {"Authorization": f"Bearer {jwt_token}"}
    response = requests.post("https://api.upbit.com/v1/orders", headers=headers, json=payload)

    return response.json()
