from django.db import models

class TradeRecord(models.Model):
    market = models.CharField(max_length=20, unique=True)  # 거래 종목 (KRW-BTC)
    buy_price = models.FloatField()  # 매수가격
    highest_price = models.FloatField(default=0)  # 최고점
    uuid = models.CharField(max_length=100, unique=True, null=True, blank=True)  # 주문 UUID
    created_at = models.DateTimeField(auto_now_add=True)  # 주문 시간
    is_active = models.BooleanField(default=True)  # 거래 활성 상태

    def __str__(self):
        return f"{self.market} (매수가: {self.buy_price})"


class FailedMarket(models.Model):
    market = models.CharField(max_length=20, unique=True)  # 중복 저장 방지
    failed_at = models.DateTimeField(auto_now_add=True)  # 실패 시간 기록

    def __str__(self):
        return self.market

