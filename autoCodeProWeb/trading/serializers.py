# trading/serializers.py
from rest_framework import serializers

class AccountSerializer(serializers.Serializer):
    currency = serializers.CharField()  # 화폐 종류
    balance = serializers.FloatField()  # 보유 수량
    locked = serializers.FloatField()  # 주문 중 묶인 수량
    avg_buy_price = serializers.FloatField()  # 평균 매수 단가
    unit_currency = serializers.CharField()  # 기준 화폐 (KRW, BTC 등)
