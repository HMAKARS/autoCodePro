# trading/auto_trade.py
import time
from django.utils import timezone
import threading
from .models import TradeRecord
from django.db import transaction
from .utils import get_krw_market_coin_info, upbit_order, get_orderbook, get_account_info, check_order_filled , get_combined_market_trend

trade_logs = []  # ✅ 자동매매 로그 저장 리스트
recently_sold = {}  # ✅ 최근 매도한 코인 기록
orderbook_cache = {}  # ✅ 호가 데이터 캐싱
getRecntTradeLog = []
listProfit = []


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
        spread = (orderbook["orderbook_units"][0]["ask_price"] - orderbook["orderbook_units"][0]["bid_price"]) / \
                 orderbook["orderbook_units"][0]["bid_price"]

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
        self.failedTrade = 0

        # ✅ DB에서 기존 거래 불러오기 (프로그램 재시작 시 유지)
        active_trades = TradeRecord.objects.filter(is_active=True)
        for trade in active_trades:
            self.active_trades[trade.market] = {
                "buy_price": trade.buy_price,
                "highest_price": trade.highest_price,
                "uuid": trade.uuid,
                "created_at": trade.created_at  # ✅ created_at 추가!
            }
        print(f"🔄 기존 거래 불러오기 완료: {list(self.active_trades.keys())}")

    def log(self, message):
        """ ✅ 로그 저장 """
        print(message)
        trade_logs.append(message)
        if len(trade_logs) > 50:
            trade_logs.pop(0)

    def save_trade(self, market, buy_price, uuid , budget):
        """ ✅ 현재 거래 상태를 DB에 저장 (매수 시 `created_at` 갱신) """
        with transaction.atomic():
            trade, created = TradeRecord.objects.update_or_create(
                market=market,
                defaults={
                    "buy_price": buy_price,
                    "highest_price": buy_price,  # 초기 최고가 = 매수가
                    "uuid": uuid,
                    "is_active": True,
                    "created_at": timezone.now(),  # ✅ 매수 시점 갱신
                    "buy_krw_price" : budget
                }
            )
            self.active_trades[market] = {
                "buy_price": buy_price,
                "highest_price": buy_price,
                "uuid": uuid,
                "created_at": trade.created_at,  # ✅ 내부 저장소에도 저장
            }

    def clear_trade(self, market):
        """ ✅ 거래 종료 후 DB에서 삭제 """
        with transaction.atomic():
            TradeRecord.objects.filter(market=market).update(is_active=False)
            if market in self.active_trades:
                del self.active_trades[market]  # ✅ 메모리에서도 제거

    def change_trade(self, market):
        """ ✅ 거래 종료 후 DB에서 삭제 """
        with transaction.atomic():
            TradeRecord.objects.filter(market=market).update(is_active=False)
            if market in self.active_trades:
                del self.active_trades[market]  # ✅ 메모리에서도 제거

    def _run_trading(self):
        """ ✅ 쓰레드에서 실행할 자동매매 루프 """
        try:
            while self.is_active:
                self.execute_trade()
                time.sleep(1)  # ✅ 1초 간격으로 거래 실행
        except Exception as e:
            self.log(f"⚠️ 거래 중 오류 발생: {e}")
            self.failedTrade += 1
            while self.is_active and self.failedTrade < 3:
                self.execute_trade()
                time.sleep(1)

    def start_trading(self):
        """ ✅ 자동매매 시작 (쓰레드 실행) """
        if self.is_active:
            self.log("⚠️ 이미 자동매매 실행 중")
            return

        self.is_active = True
        self.failedTrade = 0
        self.log("🚀 자동매매 시작됨!")

        # ✅ 새로운 쓰레드를 생성하여 _run_trading 실행
        self.trade_thread = threading.Thread(target=self._run_trading, daemon=True)
        self.trade_thread.start()

    def stop_trading(self):
        """ ✅ 자동매매 중지 """
        if not self.is_active:
            self.log("⚠️ 자동매매가 이미 중지됨")
            return

        self.is_active = False
        self.log("🛑 자동매매 중지됨!")

        if self.trade_thread and self.trade_thread.is_alive():
            self.trade_thread.join()  # ✅ 쓰레드가 안전하게 종료될 때까지 기다림

    def execute_trade(self):
        """ ✅ 자동매매 실행 (변동성 리스크 관리 추가) """

        account_info = get_account_info()
        market_trend = get_combined_market_trend()
        user_holdings = {item["currency"]: item for item in account_info}

        # ✅ 안전한 KRW 잔고 변환 (없으면 0으로 처리)
        krw_balance = float(next((item["balance"] for item in account_info if item["currency"] == "KRW"), 0))

        # ✅ 현재 거래 중인 종목 DB 업데이트
        active_trades = TradeRecord.objects.filter(is_active=True)
        active_markets = set(active_trades.values_list("market", flat=True))
        self.active_trades = {
            trade.market: {"buy_price": trade.buy_price, "uuid": trade.uuid, "highest_price": trade.highest_price , "created_at" : trade.created_at} for trade
            in active_trades}

        # ✅ 사용자가 직접 매도했는지 확인
        for market in list(self.active_trades.keys()):
            currency = market.replace("KRW-", "")
            if currency not in user_holdings:
                self.log(f"⚠️ 사용자가 직접 {market}을(를) 매도함. 거래 기록 정리")
                self.clear_trade(market)
                active_markets.discard(market)  # ✅ 집합(set)에서 안전하게 제거
                self.active_trades.pop(market, None)  # ✅ 안전하게 삭제

        # ✅ 변동성 필터링을 위한 데이터 가져오기
        market_data = get_krw_market_coin_info()
        if not isinstance(market_data, list):
            self.log(f"⚠️ API 데이터 오류: {market_data}")
            return

        # ✅ 변동성이 너무 큰 종목 필터링 (최근 5분 변동률 확인)
        volatility_data = {coin["market"]: abs(coin["signed_change_rate"]) for coin in market_data}
        high_volatility_markets = {market for market, vol in volatility_data.items() if vol > 0.05}  # ✅ 5% 이상 변동한 종목 제외

        # ✅ 현재 보유 중인 코인에 대한 처리
        for market, trade_data in list(self.active_trades.items()):
            currency = market.replace("KRW-", "")
            # ✅ 매도 주문 체결 확인
            if "uuid" in trade_data and check_order_filled(trade_data["uuid"]):
                self.log(f"✅ 매도 체결 완료: {market}")
                self.clear_trade(market)
                self.active_trades.pop(market, None)  # ✅ 안전하게 삭제
                continue
            # ✅ 현재 가격 확인
            current_price = next((coin["trade_price"] for coin in market_data if coin["market"] == market), None)
            if not current_price:
                continue

            buy_price = trade_data["buy_price"]

            if trade_data["highest_price"] is None:
                trade_data["highest_price"] = buy_price  # ✅ 매수가를 초기 최고점으로 설정
                TradeRecord.objects.filter(market=market).update(highest_price=buy_price)

            if current_price > trade_data["highest_price"]:
                trade_data["highest_price"] = current_price  # ✅ 가격 상승 시만 최고점 갱신
                TradeRecord.objects.filter(market=market).update(highest_price=current_price)  # ✅ DB 업데이트
                self.log(f"📊 최고점 갱신: {market}, 최고점 = {trade_data['highest_price']:.8f}원")

            # ✅ 수익률 계산
            fee_rate = 0.0005  # 업비트 수수료
            real_buy_price = buy_price * (1 + fee_rate)
            real_sell_price = current_price * (1 - fee_rate)
            profit_rate = ((real_sell_price - real_buy_price) / real_buy_price) * 100

            if "created_at" in trade_data and trade_data["created_at"]:
                holding_time = (timezone.now() - trade_data["created_at"]).total_seconds()
            else:
                holding_time = 0  # ✅ created_at이 없을 경우 기본값 0

            self.log(f"📊 거래중인 코인 = {market} 현재 가격: {current_price:.8f}원 "
                     f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                     f"수익률: {profit_rate:.2f}%)")
            """
            dictProfit = {"market" : "","profit_rate" : ""}
            if len(listProfit) > 0 :
                for item in listProfit :
                    if item.get("market") == market :
                        item["profit_rate"] = profit_rate
                    else :
                        dictProfit["market"] = market
                        dictProfit["profit_rate"] = profit_rate
                        listProfit.append(dictProfit)
            else :
                dictProfit["market"] = market
                dictProfit["profit_rate"] = profit_rate
                listProfit.append(dictProfit)
            """

            # ✅ 10분 보유 후 1% 수익 도달 시 매도 (보합장/하락장)
            if market_trend in ["neutral", "bearish"] and holding_time > 600:
                if current_price >= buy_price * 1.01:
                    self.log(f"✅ 보합/하락장 감지 → 10분 보유 후 1% 수익 도달! 즉시 매도: {market}, 가격: {current_price:.8f}원")
                    getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                            f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                            f"수익률: {profit_rate:.2f}%)")
                    sell_order = upbit_order(market, "ask", ord_type="market",
                                             volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                    if "error" not in sell_order:
                        trade_data["uuid"] = sell_order["uuid"]
                    continue
                else:
                    self.log(f"🚨 {market} : 10분 경과 BUT 1% 수익률 미달, 현재 수익률 {profit_rate:.2f}%")
            # ✅ 5분 보유 후 1% 수익 도달 시 매도 (상승장)
            elif market_trend == "bullish" and holding_time > 360:
                if current_price >= buy_price * 1.01:
                    self.log(f"✅ 상승장 감지 → 5분 보유 후 1% 수익 도달! 즉시 매도: {market}, 가격: {current_price:.8f}원")
                    getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                                f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                                f"수익률: {profit_rate:.2f}%)")
                    sell_order = upbit_order(market, "ask", ord_type="market",
                                                 volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                    if "error" not in sell_order:
                        trade_data["uuid"] = sell_order["uuid"]
                    continue
                else:
                    self.log(f"🚨 {market} : 5분 경과 BUT 1% 수익률 미달, 현재 수익률 {profit_rate:.2f}%")

            # ✅ 변동성 기반 손절 설정
            volatility_factor = 0.96 if market in high_volatility_markets else 0.98
            if current_price <= buy_price * volatility_factor:
                self.log(f"🛑 변동성 리스크 반영 손절 ({100 - volatility_factor * 100:.1f}% 하락): {market}, 가격: {current_price:.8f}원")
                getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                        f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                        f"수익률: {profit_rate:.2f}%)")
                sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue

            # ✅ 추가적인 -2% 손절 로직 (변동성 손절과 별도로 적용)
            if current_price <= buy_price * 0.98:
                self.log(f"🛑 -2% 손절 기준 도달 → 즉시 매도: {market}, 가격: {current_price:.8f}원")
                getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                        f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                        f"수익률: {profit_rate:.2f}%)")
                sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue

            # ✅ 2% 목표 수익 도달 시 매도 (상승장일 경우 트레일링 스탑 유지)
            if current_price >= buy_price * 1.02:
                if market_trend == "bullish":
                    self.log(f"🚀 상승장 감지! 트레일링 스탑 유지: {market}, 최고가 = {trade_data['highest_price']:.8f}원")
                else:
                    self.log(f"✅ {market_trend.upper()} 시장 감지 → 목표 수익률 도달 (2% 상승) → 즉시 매도: {market}, 가격: {current_price:.8f}원")
                    getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                            f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                            f"수익률: {profit_rate:.2f}%)")
                    sell_order = upbit_order(market, "ask", ord_type="market",
                                             volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                    if "error" not in sell_order:
                        trade_data["uuid"] = sell_order["uuid"]
                    continue  # ✅ 즉시 매도되었으므로 트레일링 스탑을 실행할 필요 없음.

            # ✅ 트레일링 스탑 발동 조건: 최소 +2% 수익 이상에서만 작동
            if current_price >= buy_price * 1.02:  # 🔹 수익이 +2%를 초과한 경우
                trade_data["highest_price"] = max(trade_data["highest_price"], current_price)
                self.log(f"🚀 최고점 갱신: {market}, 최고점 = {trade_data['highest_price']:.8f}원")

            # ✅ 트레일링 스탑 (-1%) 적용: 최소 2% 수익 이후부터 작동
            if trade_data["highest_price"] >= buy_price * 1.02 and current_price <= trade_data["highest_price"] * 0.99:
                self.log(f"🚀 트레일링 스탑 매도: {market}, 가격: {current_price:.8f}원")
                getRecntTradeLog.append(f"📊 매도체결된 코인 = {market} 현재 가격: {current_price:.8f}원 ,"
                                        f"(매수가: {buy_price:.8f}원, 최고점: {trade_data['highest_price']:.8f}원, "
                                        f"수익률: {profit_rate:.2f}%)")
                sell_order = upbit_order(market, "ask", ord_type="market",
                                         volume=str(user_holdings.get(currency, {}).get("balance", 0)))
                if "error" not in sell_order:
                    trade_data["uuid"] = sell_order["uuid"]
                continue


    # ✅ 매도 후 종목이 하나도 없을 경우 새로운 매수 진행
        if len(self.active_trades) == 0 and self.is_active:
            self.log("🔄 모든 종목이 매도 완료됨, 새로운 종목 매수 진행")

            # ✅ 활성 거래 3개 이상이면 추가 매수 중단
        if len(active_markets) >= 3:
            self.log("⏸️ 현재 활성화된 거래가 3개 이상이므로 추가 매수 중단")
            return

        # ✅ 새로운 매수 진행 (변동성 높은 종목 제외)
        if self.is_active:
            best_coin, top_coins = get_best_trade_coin()
            if not best_coin or best_coin["market"] in active_markets or best_coin["market"] in high_volatility_markets:
                self.log("❌ 매수할 적절한 종목 없음 (변동성 초과 종목 제외)")
                return

            market = best_coin["market"]
            buy_amount = min(float(self.budget), krw_balance)
            if buy_amount < 5000:
                self.log(f"⚠️ 잔고 부족으로 매수 불가 (현재 잔고: {krw_balance:.2f}원)")
                return

            self.log(f"✅ 매수 실행: {market}, 금액: {buy_amount}원")
            buy_order = upbit_order(market, "bid", price=str(buy_amount), ord_type="price")

            if "error" not in buy_order:
                self.save_trade(market, best_coin["trade_price"], buy_order["uuid"],self.budget)
