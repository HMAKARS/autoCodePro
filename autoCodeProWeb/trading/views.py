# trading/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_account_info , get_market_volume_cur
from .auto_trade import AutoTrader, trade_logs, get_best_trade_coin , getRecntTradeLog , listProfit
import threading
import time

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
