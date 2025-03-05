# trading/auto_trade.py
import time
import threading
from .models import TradeRecord
from django.db import transaction
from .utils import get_krw_market_coin_info, upbit_order, get_orderbook, get_account_info ,check_order_filled

trade_logs = []  # ✅ 자동매매 로그 저장 리스트
recently_sold = {}  # ✅ 최근 매도한 코인 기록
orderbook_cache = {}  # ✅ 호가 데이터 캐싱



def load_active_trade():
    """ ✅ 활성화된 거래 기록을 불러옴 """
    active_trade = TradeRecord.objects.filter(is_active=True).first()
    if active_trade:
        return {
            "market": active_trade.market,
            "buy_price": active_trade.buy_price,
            "highest_price": active_trade.highest_price,
            "uuid": active_trade.uuid
        }
    return None


def get_best_trade_coin():
    """ ✅ 전일 대비 상승한 10개 종목 중에서 호가 정보를 기반으로 상위 5개 선정 """
    coin_data = get_krw_market_coin_info()
    if "error" in coin_data:
        return None, []

    # ✅ 전일 대비 상승률 기준 상위 10개 선정
    positive_coins = [coin for coin in coin_data if coin["signed_change_rate"] > 0]
    top_10_coins = sorted(positive_coins, key=lambda x: x["signed_change_rate"], reverse=True)[:10]

    # ✅ 호가 데이터 한 번에 요청 후 캐싱 (429 방지)
    markets = [coin["market"] for coin in top_10_coins]
    now = time.time()

    fresh_markets = [m for m in markets if m not in orderbook_cache or (now - orderbook_cache[m]["timestamp"] > 5)]
    if fresh_markets:
        new_orderbook_data = get_orderbook(fresh_markets)
        for market, data in new_orderbook_data.items():
            orderbook_cache[market] = {"data": data, "timestamp": now}

    filtered_coins = []
    for coin in top_10_coins:
        orderbook = orderbook_cache.get(coin["market"], {}).get("data")
        if not orderbook:
            continue

        # ✅ 매수세 강도 계산 (매수 총잔량 vs 매도 총잔량 비교)
        bid_size = orderbook.get("total_bid_size", 0)
        ask_size = orderbook.get("total_ask_size", 0)
        spread = (orderbook["orderbook_units"][0]["ask_price"] - orderbook["orderbook_units"][0]["bid_price"]) / orderbook["orderbook_units"][0]["bid_price"]

        if bid_size > ask_size * 1.5 and spread < 0.001:  # ✅ 매수세가 강하고 스프레드가 좁은 종목 선정
            coin["bid_size"] = bid_size
            filtered_coins.append(coin)

    if not filtered_coins:
        return None, []

    top_5_coins = sorted(filtered_coins, key=lambda x: x["acc_trade_price_24h"], reverse=True)[:5]
    best_coin = max(top_5_coins, key=lambda x: x["trade_price"] * x["acc_trade_price_24h"])

    return best_coin, top_5_coins

class AutoTrader:
    def __init__(self, budget):
        """ ✅ 자동매매 트레이더 (거래 정보 DB 연동) """
        self.budget = budget
        self.is_active = False
        self.active_trades = {}  # ✅ 현재 활성화된 거래 목록 (market -> 거래 정보)
        self.failed_markets = set()

        # ✅ DB에서 기존 거래 불러오기 (프로그램 재시작 시 유지)
        active_trades = TradeRecord.objects.filter(is_active=True)
        for trade in active_trades:
            self.active_trades[trade.market] = {
                "buy_price": trade.buy_price,
                "highest_price": trade.highest_price,
                "uuid": trade.uuid
            }
        print(f"🔄 기존 거래 불러오기 완료: {list(self.active_trades.keys())}")

    def log(self, message):
        """ ✅ 로그 저장 """
        print(message)
        trade_logs.append(message)
        if len(trade_logs) > 50:
            trade_logs.pop(0)


    def save_trade(self, market, buy_price, uuid):
        """ ✅ 현재 거래 상태를 DB에 저장 """
        with transaction.atomic():
            trade, _ = TradeRecord.objects.update_or_create(
                market=market,
                defaults={
                    "buy_price": buy_price,
                    "highest_price": buy_price,  # 초기 최고가 = 매수가
                    "uuid": uuid,
                    "is_active": True,
                }
            )
            self.active_trades[market] = {
                "buy_price": buy_price,
                "highest_price": buy_price,
                "uuid": uuid
            }

    def clear_trade(self, market):
        """ ✅ 거래 종료 후 DB에서 삭제 """
        with transaction.atomic():
            TradeRecord.objects.filter(market=market).update(is_active=False)
            if market in self.active_trades:
                del self.active_trades[market]  # ✅ 메모리에서도 제거

    def start_trading(self):
        """ ✅ 자동매매 시작 """
        if self.is_active:
            self.log("⚠️ 이미 자동매매 실행 중")
            return

        self.is_active = True
        self.log("🚀 자동매매 시작됨!")

        while self.is_active:
            self.execute_trade()
            time.sleep(1)

    def stop_trading(self):
        """ ✅ 자동매매 중지 """
        self.is_active = False
        self.log("🛑 자동매매 중지됨!")

    def execute_trade(self):
        """ ✅ 자동매매 실행 (다중 종목 관리) """
        account_info = get_account_info()
        user_holdings = {item["currency"]: item for item in account_info}

        # ✅ 안전한 KRW 잔고 변환 (없으면 0으로 처리)
        krw_balance = float(next((item["balance"] for item in account_info if item["currency"] == "KRW"), 0))

        # ✅ 현재 거래 중인 종목 DB 업데이트
        active_trades = TradeRecord.objects.filter(is_active=True)
        active_markets = set(active_trades.values_list("market", flat=True))
        self.active_trades = {trade.market: {"buy_price": trade.buy_price, "uuid": trade.uuid, "highest_price": trade.highest_price} for trade in active_trades}

        # ✅ 사용자가 직접 매도했는지 확인
        for trade in list(self.active_trades.keys()):
            market = trade
            currency = market.replace("KRW-", "")

            if currency not in user_holdings:
                self.log(f"⚠️ 사용자가 직접 {market}을(를) 매도함. 거래 기록 정리")
                self.clear_trade(market)
                active_markets.remove(market)
                del self.active_trades[market]  # ✅ 내부 관리 목록에서도 삭제

        # ✅ 현재 보유 중인 코인에 대한 처리
        for market, trade_data in list(self.active_trades.items()):
            currency = market.replace("KRW-", "")

            # ✅ 매도 주문 체결 확인
            if "uuid" in trade_data and check_order_filled(trade_data["uuid"]):
                self.log(f"✅ 매도 체결 완료: {market}")
                self.clear_trade(market)
                del self.active_trades[market]  # ✅ 내부 관리 목록에서도 삭제
                continue

            # ✅ 현재 가격 확인
            market_data = get_krw_market_coin_info()
            if not isinstance(market_data, list):
                self.log(f"⚠️ API 데이터 오류: {market_data}")
                continue  # 잘못된 데이터일 경우 처리 중단

            current_price = next((coin["trade_price"] for coin in market_data if coin["market"] == market), None)
            if not current_price:
                continue

            buy_price = trade_data["buy_price"]
            highest_price = max(trade_data["highest_price"], current_price)
            trade_data["highest_price"] = highest_price  # ✅ 최고가 업데이트

            # ✅ 수익률 계산
            fee_rate = 0.0005  # 업비트 수수료
            real_buy_price = buy_price * (1 + fee_rate)
            real_sell_price = current_price * (1 - fee_rate)
            profit_rate = ((real_sell_price - real_buy_price) / real_buy_price) * 100

            self.log(f"📊 거래중인 코인 = {market} 현재 가격: {current_price:.8f}원 "
                     f"(매수가: {buy_price:.8f}원, 최고점: {highest_price:.8f}원, "
                     f"수익률: {profit_rate:.2f}%)")

            # ✅ 2% 목표 수익 도달 시 매도
            if current_price >= buy_price * 1.02:
                self.log(f"✅ 목표 수익률 도달 → 매도 실행: {market}, 가격: {current_price:.8f}원")
                sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue

            # ✅ 트레일링 스탑 (-1%) 매도
            if highest_price * 0.99 >= current_price:
                self.log(f"🚀 트레일링 스탑 매도: {market}, 가격: {current_price:.8f}원")
                sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue

            # ✅ -2% 손절
            if current_price <= buy_price * 0.98:
                self.log(f"🛑 손절 매도 (-2% 하락): {market}, 가격: {current_price:.8f}원")
                sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue

        # ✅ 활성 거래 3개 이상이면 추가 매수 중단
        print(len(active_markets))
        if len(active_markets) >= 3:
            self.log("⏸️ 현재 활성화된 거래가 3개 이상이므로 추가 매수 중단")
            return

        # ✅ 새로운 매수 진행 (기존 보유 종목 제외 후 매수)
        else :
            best_coin, top_coins = get_best_trade_coin()
            if not best_coin or best_coin["market"] in active_markets:
                self.log("❌ 매수할 적절한 종목 없음 (기존 거래 유지 중)")
                return

            market = best_coin["market"]
            buy_amount = min(float(self.budget), krw_balance)  # ✅ 잔고가 부족하면 가능한 만큼 매수
            if buy_amount < 5000:  # ✅ 업비트 최소 주문 금액 체크
                self.log(f"⚠️ 잔고 부족으로 매수 불가 (현재 잔고: {krw_balance:.2f}원)")
                return

            self.log(f"✅ 매수 실행: {market}, 금액: {buy_amount}원")
            buy_order = upbit_order(market, "bid", price=str(buy_amount), ord_type="price")

            if "error" not in buy_order:
                self.save_trade(market, best_coin["trade_price"], buy_order["uuid"])









