# trading/auto_trade.py
import time
import threading
from .utils import get_krw_market_coin_info, upbit_order

trade_logs = []  # ✅ 자동매매 로그 저장 리스트

def get_best_trade_coin():
    """ ✅ 전일 대비 상승한 상위 10개 중 거래대금 & 거래량 기준 최적의 종목 선정 """
    coin_data = get_krw_market_coin_info()

    if "error" in coin_data:
        return None, []

    positive_coins = [coin for coin in coin_data if coin["signed_change_rate"] > 0]
    top_10_coins = sorted(positive_coins, key=lambda x: x["signed_change_rate"], reverse=True)[:10]
    top_5_coins = sorted(top_10_coins, key=lambda x: x["acc_trade_price_24h"], reverse=True)[:5]

    best_coin = sorted(top_5_coins, key=lambda x: x["trade_price"] * x["acc_trade_price_24h"], reverse=True)[0]

    return best_coin, top_5_coins

class AutoTrader:
    def __init__(self, budget):
        """ ✅ 자동매매 트레이더 """
        self.budget = budget
        self.is_active = False
        self.current_order = None
        self.highest_price = 0  # ✅ 트레일링 스탑 최고점

    def log(self, message):
        """ ✅ 로그 저장 (최대 50개 유지) """
        print(message)
        trade_logs.append(message)
        if len(trade_logs) > 50:
            trade_logs.pop(0)

    def start_trading(self):
        """ ✅ 자동매매 시작 """
        if self.is_active:
            self.log("⚠️ 이미 자동매매 실행 중")
            return

        self.is_active = True
        self.log("🚀 자동매매 시작됨!")

        while self.is_active:
            self.execute_trade()
            time.sleep(1)  # ✅ 1초마다 실행

    def stop_trading(self):
        """ ✅ 자동매매 중지 """
        self.is_active = False
        self.log("🛑 자동매매 중지됨!")

    def execute_trade(self):
        """ ✅ 자동매매 실행 (트레일링 스탑 손실 방지) """
        if self.current_order is None:
            if not self.is_active:
                return

            best_coin, top_coins = get_best_trade_coin()
            if not best_coin:
                self.log("❌ 매수할 적절한 종목 없음 (전일 대비 상승률 기준)")
                return

            market = best_coin["market"]

            self.log(f"✅ 매수 실행: {market}, 금액: {self.budget}원, 전일 대비: {best_coin['signed_change_rate'] * 100:.2f}%")
            buy_order = upbit_order(market, "buy", price=self.budget, ord_type="price")

            if "error" not in buy_order:
                self.current_order = {
                    "market": market,
                    "buy_price": best_coin["trade_price"],
                }
                self.highest_price = best_coin["trade_price"]
            return

        coin_data = get_krw_market_coin_info()
        for coin in coin_data:
            if coin["market"] == self.current_order["market"]:
                current_price = coin["trade_price"]
                buy_price = self.current_order["buy_price"]

                if current_price > self.highest_price:
                    self.highest_price = current_price

                self.log(f"📊 현재 가격: {current_price}원 (매수가: {buy_price}원, 최고점: {self.highest_price}원)")

                # ✅ 트레일링 스탑 손실 방지 (최고가가 매수가보다 클 때만 적용)
                if self.highest_price > buy_price and self.highest_price * 0.99 >= current_price:
                    self.log(f"🚀 매도 실행 (트레일링 스탑): {self.current_order['market']}, 가격: {current_price}원")
                    upbit_order(self.current_order["market"], "sell", ord_type="market")
                    self.current_order = None
                    self.execute_trade()
                    return

                # ✅ -3% 손절
                if current_price <= buy_price * 0.97:
                    self.log(f"🛑 손절 매도 (-3% 하락): {self.current_order['market']}, 가격: {current_price}원")
                    upbit_order(self.current_order["market"], "sell", ord_type="market")
                    self.current_order = None
                    self.execute_trade()
                    return
