# trading/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_account_info , get_market_volume_cur
from .auto_trade import AutoTrader, trade_logs, get_best_trade_coin , getRecntTradeLog , listProfit , update_volume_cache
import threading
import time
import pandas as pd
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .indicators import calculate_rsi, calculate_macd, calculate_stochastic, calculate_ema, calculate_bollinger_bands, calculate_atr

trader = None  # ✅ 자동매매 객체

def main_view(request):
    """ ✅ 메인 페이지 """
    _, top_coins = get_best_trade_coin()  # ✅ UI에 표시할 상위 5개 코인 가져오기

    return render(request, "main.html", {
        "account_info": get_account_info(),
        "top_coins": top_coins
    })

def fetch_account_data(request):
    """ ✅ AJAX 요청을 받아 전체 계좌 정보를 반환 """
    return JsonResponse({"account_info": get_account_info()})

def fetch_coin_data(request):
    """ ✅ AJAX 요청을 받아 상위 5개 코인 정보를 반환 """
    _, top_coins = get_best_trade_coin()

    return JsonResponse({"top_coins": top_coins})

def startVolumeCheck(request) :
    update_volume_cache()
    return JsonResponse({"returnCache" : "true"})

def fetch_trade_logs(request):
    """ ✅ 자동매매 로그 반환 """
    return JsonResponse({"logs": trade_logs})

def start_auto_trading(request):
    """ ✅ 자동매매 시작 API """
    global trader
    budget = int(request.GET.get("budget", 10000))

    if trader is None or not trader.is_active:
        trader = AutoTrader(budget)
        threading.Thread(target=trader.start_trading).start()
        return JsonResponse({"status": "started", "budget": budget})

    return JsonResponse({"status": "already running", "budget": trader.budget})

def stop_auto_trading(request):
    """ ✅ 자동매매 중지 API """
    global trader
    if trader and trader.is_active:
        trader.stop_trading()
        return JsonResponse({"status": "stopped"})

    return JsonResponse({"status": "not running"})

def check_auto_trading(request):
    """ ✅ 자동매매 실행 여부 확인 """
    return JsonResponse({"is_active": trader.is_active if trader else False})

def start_market_volume_tracking():
    """ ✅ 주기적으로 시장 거래량을 기록하는 함수 (24시간마다 실행) """
    from .utils import record_market_volume  # ✅ 함수 내부에서 import
    while True:
        record_market_volume()
        time.sleep(86400)  # 24시간마다 실행 (60초 * 60분 * 24시간)

def get_market_volume(request):
    return JsonResponse({"market_volume_cur": get_market_volume_cur()})

def recentTradeLog(request):  # ✅ 함수 호출해서 데이터를 가져오기
    return JsonResponse({"recentTradeLog": getRecntTradeLog})  # ✅ 리스트에서 첫 번째 요소 가져오기

def recentProfitLog(request) :
    return JsonResponse({"listProfit": listProfit})

UPBIT_TICKER_URL = "https://api.upbit.com/v1/market/all"
UPBIT_TICKER_INFO_URL = "https://api.upbit.com/v1/ticker"
UPBIT_CANDLE_URL = "https://api.upbit.com/v1/candles/minutes/1"

class TradingSignalView(APIView):
    def get_top_volume_tickers(self):
        """거래량 상위 5개 코인 가져오기"""
        response = requests.get(UPBIT_TICKER_INFO_URL, params={"markets": ",".join(self.get_all_tickers())}).json()
        df = pd.DataFrame(response)
        df = df[['market', 'acc_trade_price']]
        df = df.sort_values(by='acc_trade_price', ascending=False)[:5]  # 거래량 상위 5개 선택
        return df['market'].tolist()

    def get_all_tickers(self):
        """업비트에서 모든 종목 리스트 가져오기"""
        response = requests.get(UPBIT_TICKER_URL).json()
        tickers = [item['market'] for item in response if item['market'].startswith('KRW-')]
        return tickers

    def get_candle_data(self, ticker):
        """업비트에서 특정 종목의 1분봉 데이터 가져오기"""
        response = requests.get(f"{UPBIT_CANDLE_URL}?market={ticker}&count=20").json()
        df = pd.DataFrame(response)
        df = df[['trade_price', 'high_price', 'low_price']]
        df.columns = ['close', 'high', 'low']
        return df[::-1]  # 최근 데이터부터 정렬

    def analyze_ticker(self, ticker):
        """종목별 지표 계산 후 매수 여부 판별"""
        df = self.get_candle_data(ticker)
        prices = df['close']
        high_prices = df['high']
        low_prices = df['low']

        # 🎯 지표 계산
        rsi = calculate_rsi(prices)
        macd, macd_signal = calculate_macd(prices)
        stochastic_k, stochastic_d = calculate_stochastic(prices, high_prices, low_prices)
        ema_9 = calculate_ema(prices, 9)
        ema_21 = calculate_ema(prices, 21)
        bollinger_upper, bollinger_lower = calculate_bollinger_bands(prices)
        atr = calculate_atr(high_prices, low_prices, prices)

        # 🎯 매수 조건 판별
        buy_signal = 0
        if (
                rsi < 30 and  # RSI 과매도
                macd > macd_signal and  # MACD 골든크로스
                stochastic_k < 20 and stochastic_d < 20 and stochastic_k > stochastic_d and  # 스토캐스틱 과매도 후 반등
                ema_9 > ema_21 and  # 단기 EMA > 장기 EMA
                prices.iloc[-1] > bollinger_lower and  # 볼린저 밴드 하단에서 반등
                atr > 20  # 변동성이 충분히 높은 경우
        ):
            buy_signal = 1  # 매수 신호 발생

        return {
            "ticker": ticker,
            "buy_signal": buy_signal,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "stochastic_k": stochastic_k,
            "stochastic_d": stochastic_d,
            "ema_9": ema_9,
            "ema_21": ema_21,
            "bollinger_upper": bollinger_upper,
            "bollinger_lower": bollinger_lower,
            "atr": atr
        }

    def get(self, request):
        """거래량 상위 5개 종목을 분석하고 매수할 종목을 반환"""
        top_tickers = self.get_top_volume_tickers()
        buy_candidates = []

        for ticker in top_tickers:
            result = self.analyze_ticker(ticker)
            if result["buy_signal"] == 1:
                buy_candidates.append(result)

        return Response({"buy_candidates": buy_candidates}, status=status.HTTP_200_OK)



