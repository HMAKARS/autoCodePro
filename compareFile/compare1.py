def execute_trade(self):
    """ ✅ 자동매매 실행 (변동성 리스크 관리 추가) """
    account_info = get_account_info()
    user_holdings = {item["currency"]: item for item in account_info}

    # ✅ 안전한 KRW 잔고 변환 (없으면 0으로 처리)
    krw_balance = float(next((item["balance"] for item in account_info if item["currency"] == "KRW"), 0))

    # ✅ 현재 거래 중인 종목 DB 업데이트
    active_trades = TradeRecord.objects.filter(is_active=True)
    active_markets = set(active_trades.values_list("market", flat=True))
    self.active_trades = {trade.market: {"buy_price": trade.buy_price, "uuid": trade.uuid, "highest_price": trade.highest_price} for trade in active_trades}

    # ✅ 변동성 필터링을 위한 데이터 가져오기
    market_data = get_krw_market_coin_info()
    if not isinstance(market_data, list):
        self.log(f"⚠️ API 데이터 오류: {market_data}")
        return

    # ✅ 변동성이 너무 큰 종목 필터링 (최근 5분 변동률 확인)
    volatility_data = {coin["market"]: abs(coin["signed_change_rate"]) for coin in market_data}
    high_volatility_markets = {market for market, vol in volatility_data.items() if vol > 0.03}  # ✅ 3% 이상 변동한 종목 제외

    # ✅ 사용자가 직접 매도했는지 확인
    for market in list(self.active_trades.keys()):
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

        # ✅ 급락 감지 (-5% 이상 급락 시 즉시 손절)
        if current_price <= highest_price * 0.95:
            self.log(f"⚠️ 급락 감지 (-5% 이상) → 긴급 손절: {market}, 가격: {current_price:.8f}원")
            sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
            if "error" not in sell_order:
                trade_data["uuid"] = sell_order["uuid"]
            continue

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

        # ✅ 변동성이 클 경우 손절폭 완화 (-3% 손절)
        loss_cut = 0.97 if market in high_volatility_markets else 0.98
        if current_price <= buy_price * loss_cut:
            self.log(f"🛑 손절 매도 ({100 - loss_cut * 100}% 하락): {market}, 가격: {current_price:.8f}원")
            sell_order = upbit_order(market, "ask", ord_type="market", volume=str(user_holdings.get(currency, {}).get("balance", 0)))
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
            self.save_trade(market, best_coin["trade_price"], buy_order["uuid"])
