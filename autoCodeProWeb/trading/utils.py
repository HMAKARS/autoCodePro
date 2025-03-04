# trading/utils.py
import requests
import jwt
import uuid
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
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY

    payload = {"market": market, "side": side, "ord_type": ord_type, "nonce": str(uuid.uuid4())}
    if ord_type == "price": payload["price"] = str(price)
    elif ord_type == "market": payload["volume"] = str(volume)

    jwt_token = jwt.encode(payload, secret_key, algorithm="HS256")
    headers = {"Authorization": f"Bearer {jwt_token}"}
    response = requests.post("https://api.upbit.com/v1/orders", headers=headers, json=payload)

    return response.json() if response.status_code == 201 else {"error": response.json()}
