# trading/auto_trade.py
import time
import threading
from .utils import get_krw_market_coin_info, upbit_order, get_account_info
import requests

trade_logs = []  # ✅ 자동매매 로그 저장 리스트

class AutoTrader:
    def __init__(self, budget):
        """자동매매 트레이더"""
        self.budget = budget
        self.active = False
        self.current_order = None
        self.highest_price = 0  # 트레일링 스탑 최고점

    def log(self, message):
        """ ✅ 로그 저장 및 최대 50개까지만 유지 """
        print(message)
        trade_logs.append(message)
        if len(trade_logs) > 50:
            trade_logs.pop(0)

    def get_available_krw(self):
        """ ✅ 현재 사용 가능한 원화(KRW) 잔고 조회 """
        accounts = get_account_info()
        for account in accounts:
            if account["currency"] == "KRW":
                return float(account["balance"])  # 현재 사용 가능한 원화 잔고 반환
        return 0  # KRW 잔고가 없으면 0 반환

    def start_trading(self):
        """자동매매 시작"""
        self.active = True
        self.log("🚀 자동매매 시작됨!")

        while self.active:
            self.execute_trade()
            time.sleep(1)  # ✅ 1초마다 실행

    def stop_trading(self):
        """자동매매 중지"""
        self.active = False
        self.log("🛑 자동매매 중지됨!")

    def execute_trade(self):
        """자동매매 실행"""
        if self.current_order is None:
            # ✅ 1. 현재 원화 잔고 확인 (잔고 부족 방지)
            available_krw = self.get_available_krw()
            if available_krw < self.budget:
                self.log(f"❌ 잔고 부족: {available_krw}원 (필요: {self.budget}원)")
                return

            # ✅ 2. RSI 30 이하 종목 찾기
            best_coin = None
            for coin in get_krw_market_coin_info():
                rsi = self.get_rsi(coin["market"])
                if rsi <= 30:
                    best_coin = coin
                    break

            if best_coin is None:
                self.log("❌ 매수할 적절한 코인이 없음 (RSI 30 이하 조건 미충족)")
                return

            market = best_coin["market"]

            # ✅ 3. 시장가 매수 실행
            self.log(f"✅ 매수 실행: {market}, 금액: {self.budget}원, RSI: {rsi}")
            buy_order = upbit_order(market, "buy", price=self.budget, ord_type="price")

            if "error" not in buy_order:
                self.current_order = {
                    "market": market,
                    "buy_price": best_coin["trade_price"],
                }
                self.highest_price = best_coin["trade_price"]
            return

        # ✅ 4. 매도 조건 체크 (트레일링 스탑)
        coin_data = get_krw_market_coin_info()
        for coin in coin_data:
            if coin["market"] == self.current_order["market"]:
                current_price = coin["trade_price"]
                buy_price = self.current_order["buy_price"]

                # 최고점 갱신
                if current_price > self.highest_price:
                    self.highest_price = current_price

                self.log(f"📊 현재 가격: {current_price}원 (매수가: {buy_price}원, 최고점: {self.highest_price}원)")

                # ✅ 트레일링 스탑: 최고점 대비 -1% 하락 시 매도
                if self.highest_price * 0.99 >= current_price:
                    self.log(f"🚀 매도 실행 (트레일링 스탑): {self.current_order['market']}, 가격: {current_price}원")
                    upbit_order(self.current_order["market"], "sell", ord_type="market")
                    self.current_order = None
                    time.sleep(1)
                    return

                # ✅ -3% 손절
                if current_price <= buy_price * 0.97:
                    self.log(f"🛑 손절 매도 (-3% 하락): {self.current_order['market']}, 가격: {current_price}원")
                    upbit_order(self.current_order["market"], "sell", ord_type="market")
                    self.current_order = None
                    time.sleep(1)
                    return
