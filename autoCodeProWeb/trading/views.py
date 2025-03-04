# trading/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_account_info, get_krw_market_coin_info
from .auto_trade import AutoTrader, trade_logs, get_best_trade_coin
import threading

trader = None  # ✅ 자동매매 객체

def main_view(request):
    """ ✅ 메인 페이지 """
    _, top_coins = get_best_trade_coin()  # ✅ UI에 표시할 상위 5개 코인 가져오기

    return render(request, "main.html", {
        "account_info": get_account_info(),  # ✅ 내 계좌 정보 추가
        "top_coins": top_coins  # ✅ UI에서 사용 가능하도록 추가
    })

def fetch_account_data(request):
    """ ✅ AJAX 요청을 받아 전체 계좌 정보를 반환 (내 자산 조회 API) """
    return JsonResponse({"account_info": get_account_info()})

def fetch_coin_data(request):
    """ ✅ AJAX 요청을 받아 상위 5개 코인 정보를 반환 (실시간 업데이트용 API) """
    _, top_coins = get_best_trade_coin()  # ✅ 최신 데이터 가져오기
    return JsonResponse({"top_coins": top_coins})

def fetch_trade_logs(request):
    """ ✅ 자동매매 로그 반환 API """
    return JsonResponse({"logs": trade_logs})

def start_auto_trading(request):
    """ ✅ 자동매매 시작 API (변동값 반영) """
    global trader
    budget_str = request.GET.get("budget", "10000")  # ✅ 문자열 값으로 가져옴

    try:
        budget = int(budget_str)  # ✅ 정수로 변환
        if budget < 5000:  # ✅ 최소 매수 금액 제한 (1,000원)
            return JsonResponse({"status": "error", "message": "최소 매수 금액은 1,000원 이상이어야 합니다."})
    except ValueError:
        return JsonResponse({"status": "error", "message": "잘못된 매수 금액 입력"})

    if trader is None or not trader.is_active:
        trader = AutoTrader(budget)  # ✅ 변동값 적용
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
    """ ✅ 자동매매 실행 여부 확인 API """
    return JsonResponse({"is_active": trader.is_active if trader else False})
