from django.apps import AppConfig
import threading

class TradingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trading'

    def ready(self):
        """ ✅ Django 서버 시작 시 시장 거래량 추적 스레드 실행 """
        from .views import start_market_volume_tracking  # ✅ 여기에서 import 해야 함
        threading.Thread(target=start_market_volume_tracking, daemon=True).start()
