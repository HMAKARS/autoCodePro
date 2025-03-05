# trading/utils.py

import requests
import jwt
import hashlib
import os
import uuid
from urllib.parse import urlencode, unquote
from django.conf import settings
from .models import FailedMarket

failed_markets = set(FailedMarket.objects.values_list('market', flat=True))

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

def upbit_order(market, side, volume=None, price=None, ord_type="limit", time_in_force=None):
    """ ✅ 업비트 주문 요청 (실패 시 재시도 방지 및 실패 시장 추적) """
    if market in failed_markets:
        print(f"⚠️ {market}은(는) 이전 주문 실패로 인해 제외됨")
        return {"error": "Market excluded due to previous failures"}

    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY
    server_url = "https://api.upbit.com"

    params = {
        'market': market,
        'side': side,
        'ord_type': ord_type,
    }
    if ord_type == "price":
        params['price'] = str(price)
    elif ord_type == "market":
        params['volume'] = str(volume)
    elif ord_type == "limit":
        params['price'] = str(price)
        params['volume'] = str(volume)

    if time_in_force:
        params['time_in_force'] = time_in_force

    query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")
    m = hashlib.sha512()
    m.update(query_string)
    query_hash = m.hexdigest()

    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
        'query_hash': query_hash,
        'query_hash_alg': 'SHA512',
    }

    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    authorization = f'Bearer {jwt_token}'
    headers = {'Authorization': authorization}

    response = requests.post(f"{server_url}/v1/orders", json=params, headers=headers)
    if response.status_code != 201:
        print(f"⚠️ 주문 요청 실패: {response.json()}")
        FailedMarket.objects.get_or_create(market=market)  # DB에 실패 시장 추가
        failed_markets.add(market)  # ✅ 실패한 시장을 추적하여 이후 매수에서 제외
        return {"error": response.json()}

    return response.json()

def get_upbit_token() :
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY
    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
    }
    jwt_token = jwt.encode(payload, secret_key, algorithm="HS256")
    return jwt_token


def check_order_filled(order_uuid):
    """ ✅ 주문이 체결되었는지 확인 """
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY
    server_url = "https://api.upbit.com"

    params = {"uuid": order_uuid}
    query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")

    m = hashlib.sha512()
    m.update(query_string)
    query_hash = m.hexdigest()

    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
        'query_hash': query_hash,
        'query_hash_alg': 'SHA512',
    }

    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    headers = {"Authorization": f"Bearer {jwt_token}"}

    url = f"{server_url}/v1/order"
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"⚠️ 주문 체결 확인 실패: {response.json()}")
        return False

    order_data = response.json()
    return order_data.get("state") == "done"  # ✅ 체결 완료 상태인지 확인



def get_orderbook(markets):
    """ ✅ 여러 코인의 호가 데이터를 한 번에 가져옴 (429 방지) """
    url = "https://api.upbit.com/v1/orderbook"
    params = {"markets": ",".join(markets)}

    try:
        response = requests.get(url, params=params, timeout=2)
        if response.status_code != 200:
            print(f"⚠️ 호가 데이터 요청 실패 (HTTP {response.status_code})")
            return {}

        orderbook_data = response.json()
        return {item["market"]: item for item in orderbook_data}

    except requests.exceptions.RequestException as e:
        print(f"⚠️ 호가 데이터 요청 실패: {str(e)}")
        return {}


def get_open_orders():
    """ ✅ 업비트 API를 사용하여 현재 미체결 주문 목록 조회 """
    access_key = settings.UPBIT_ACCESS_KEY
    secret_key = settings.UPBIT_SECRET_KEY

    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
    }

    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    headers = {"Authorization": f"Bearer {jwt_token}"}

    url = "https://api.upbit.com/v1/orders?state=open"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()  # ✅ 미체결 주문 리스트 반환
    else:
        print(f"⚠️ 미체결 주문 조회 실패: {response.status_code}, {response.json()}")
        return []


