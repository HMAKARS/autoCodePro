# trading/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_account_info, get_krw_market_coin_info, upbit_order
from .auto_trade import AutoTrader, trade_logs
import threading

auto_trading = False

def main_view(request):
    """ 메인 페이지 """
    return render(request, "main.html", {
        "account_info": get_account_info(),
        "coin_info_list": get_krw_market_coin_info()
    })

def fetch_account_data(request):
    """ AJAX 요청을 받아 전체 계좌 정보를 반환 """
    return JsonResponse({"account_info": get_account_info()})

def fetch_coin_data(request):
    """ AJAX 요청을 받아 상위 5개 코인 정보를 반환 """
    return JsonResponse({"coin_info_list": get_krw_market_coin_info()})

def fetch_trade_logs(request):
    """ ✅ AJAX 요청을 받아 자동매매 로그 반환 """
    return JsonResponse({"logs": trade_logs})

def start_auto_trading(request):
    """ 자동매매 시작 """
    global trader
    budget = int(request.GET.get("budget", 10000))

    if trader is None or not trader.active:
        trader = AutoTrader(budget)
        threading.Thread(target=trader.start_trading).start()
        return JsonResponse({"status": "started"})

    return JsonResponse({"status": "already running"})

def stop_auto_trading(request):
    """ 자동매매 중지 """
    global trader
    if trader and trader.active:
        trader.stop_trading()
        return JsonResponse({"status": "stopped"})

    return JsonResponse({"status": "not running"})