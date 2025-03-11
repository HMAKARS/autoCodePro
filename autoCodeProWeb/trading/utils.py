# trading/utils.py
from django.utils import timezone

import requests
import jwt
import hashlib
import uuid
from urllib.parse import urlencode, unquote
from django.conf import settings
from .models import FailedMarket,MarketVolumeRecord,AskRecrod
import pandas as pd


market_volume_cur = None # 현재 장상황
getRecntTradeLogCur = None #최근 거래내역
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
    arrJson = response.json()

    return arrJson if response.status_code == 200 else {"error": arrJson}

UPBIT_CANDLE_URL = "https://api.upbit.com/v1/candles/seconds"

def get_candle_data(market, count=30):
    """
    ✅ 업비트 API에서 특정 종목의 1분봉 데이터를 가져오는 함수
    :param market: 조회할 코인의 종목 코드 (예: "KRW-BTC")
    :param count: 가져올 캔들 개수 (기본값: 30)
    :return: DataFrame (고가, 저가, 종가 데이터 포함)
    """
    try:
        response = requests.get(UPBIT_CANDLE_URL, params={"market": market, "count": count})
        response.raise_for_status()  # 요청 오류가 있으면 예외 발생
        data = response.json()  # JSON 응답을 파이썬 리스트로 변환

        # DataFrame 변환 및 필요한 컬럼 추출
        df = pd.DataFrame(data)
        df = df[["trade_price", "high_price", "low_price"]]  # 종가, 고가, 저가 추출
        df.columns = ["close", "high", "low"]  # 컬럼명 변경 (지표 계산 함수와 일치시키기)
        df = df.iloc[::-1]  # 최신 데이터가 위쪽에 있으므로 역순 정렬

        return df

    except requests.exceptions.RequestException as e:
        print(f"❌ {market} 캔들 데이터 요청 실패: {e}")
        return None

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
            "high_price" : ticker["high_price"],
            "low_price" : ticker["low_price"],
            "trade_volume" : ticker["trade_volume"],
            "signed_change_rate": ticker["signed_change_rate"],
            "acc_trade_price_24h": ticker["acc_trade_price_24h"],
            "acc_trade_volume_24h": ticker["acc_trade_volume_24h"],
        } for ticker in ticker_response.json()
    ], key=lambda x: x["acc_trade_price_24h"], reverse=True)

def upbit_order(market, side, volume=None, price=None, ord_type="limit", time_in_force=None):
    """ ✅ 업비트 주문 요청 (실패 시 재시도 방지 및 실패 시장 추적) """

    if market in failed_markets:
        print(f"⚠️ {market}은(는) 이전 주문 실패로 인해 제외됨")
        return {"error": "Market excluded due to previous failures"}

    latest_market = AskRecrod.objects.order_by('-id').values_list('market', flat=True).first()
    latest_market_time = AskRecrod.objects.order_by('-id').values_list('recorded_at', flat=True).first()
    if latest_market_time != None and market == latest_market and side == "bid":
        elapsed_time = (timezone.now() - latest_market_time).total_seconds()
        print(f"최근 매도된 코인 {latest_market} 최근 매도 시각: {latest_market_time}, 경과 시간: {elapsed_time:.2f}초")

        if elapsed_time < 1200:
            print("🚫 10분이 지나지 않았습니다. 거래를 중단합니다.")
            return
        else :
            print("✅ 10분이 지났습니다. 거래를 계속 진행합니다.")



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
    elif response.status_code != 200:
        if side == "ask" :
            AskRecrod.objects.update_or_create(
                market=market,
                defaults={
                    "recorded_at": timezone.now()  # ✅ 매도 시점 갱신
                }
            )


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
        response = requests.get(url, params=params, timeout=5)
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

def get_market_trend():
    """ ✅ BTC & ETH 변동성을 기반으로 시장 강도를 분석 """
    coin_data = get_krw_market_coin_info()

    btc = next((coin for coin in coin_data if coin["market"] == "KRW-BTC"), None)
    eth = next((coin for coin in coin_data if coin["market"] == "KRW-ETH"), None)

    if not btc or not eth:
        return "neutral"  # 데이터 없으면 보합장으로 처리

    btc_change = btc["signed_change_rate"]  # BTC 변동률
    eth_change = eth["signed_change_rate"]  # ETH 변동률
    avg_change = (btc_change + eth_change) / 2  # 두 종목 평균 변동률

    if avg_change > 0.02:  # +2% 이상이면 상승장
        return "bullish"
    elif avg_change < -0.02:  # -2% 이하이면 하락장
        return "bearish"
    else:
        return "neutral"  # 그 외에는 보합장

def get_market_trend_by_volume():
    """ ✅ 전체 시장 거래량 변화를 기반으로 시장 강도를 분석 """
    coin_data = get_krw_market_coin_info()
    total_volume = sum(coin["acc_trade_price_24h"] for coin in coin_data)  # 현재 거래량
    previous_volume = get_previous_market_volume()  # 🔹 과거 거래량 (DB에서 가져옴)

    if previous_volume == 0:
        return "neutral"  # 데이터가 없으면 보합장으로 처리

    volume_change = (total_volume - previous_volume) / previous_volume  # 거래량 변동률

    if volume_change > 0.2:
        return "bullish"  # 20% 이상 증가 -> 강세장
    elif volume_change < -0.2:
        return "bearish"  # 20% 이상 감소 -> 약세장
    else:
        return "neutral"  # 변동성이 낮으면 보합장


def get_market_trend_by_ratio():
    """ ✅ 상승/하락 코인 비율을 활용한 시장 강도 분석 """
    coin_data = get_krw_market_coin_info()

    rising_coins = sum(1 for coin in coin_data if coin["signed_change_rate"] > 0)
    falling_coins = sum(1 for coin in coin_data if coin["signed_change_rate"] < 0)

    total_coins = len(coin_data)
    rising_ratio = rising_coins / total_coins  # 상승 비율
    falling_ratio = falling_coins / total_coins  # 하락 비율

    if rising_ratio > 0.6:  # 60% 이상이 상승 중이면 강세장
        return "bullish"
    elif falling_ratio > 0.6:  # 60% 이상이 하락 중이면 약세장
        return "bearish"
    else:
        return "neutral"  # 상승/하락 균형이면 보합장

def get_combined_market_trend():
    """ ✅ 여러 지표를 결합하여 시장 강도 분석 """
    global market_volume_cur
    trend_by_btc_eth = get_market_trend()  # BTC/ETH 변동률 기준
    trend_by_volume = get_market_trend_by_volume()  # 전체 거래량 변화 기준
    trend_by_ratio = get_market_trend_by_ratio()  # 상승/하락 비율 기준

    trends = [trend_by_btc_eth, trend_by_volume, trend_by_ratio]

    if trends.count("bullish") >= 2:  # 3개 중 2개 이상이 강세장이면 상승장
        market_volume_cur = "상승장"
        return "bullish"
    elif trends.count("bearish") >= 2:  # 3개 중 2개 이상이 약세장이면 하락장
        market_volume_cur = "하락장"
        return "bearish"
    else:
        market_volume_cur = "보합장"
        return "neutral"  # 나머지는 보합장

def get_previous_market_volume():
    """ ✅ DB에서 가장 최근의 시장 거래량 기록을 가져옴 """
    last_record = MarketVolumeRecord.objects.order_by("-recorded_at").first()
    return last_record.total_market_volume if last_record else 0  # 데이터가 없으면 0 반환

def record_market_volume():
    """ ✅ 현재 시장의 전체 거래량을 DB에 저장 """
    coin_data = get_krw_market_coin_info()
    total_volume = sum(coin["acc_trade_price_24h"] for coin in coin_data)  # 전체 거래량 계산

    # ✅ 새 거래량 데이터 저장
    MarketVolumeRecord.objects.create(total_market_volume=total_volume)
    print(f"📊 시장 거래량 기록됨: {total_volume}")

def get_market_volume_cur():
    try:
        return market_volume_cur
    except Exception as e :
        return {"error" : str(e)}



