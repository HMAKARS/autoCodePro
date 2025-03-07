# trading/urls.py
from django.urls import path
from .views import (main_view, start_auto_trading,
                    stop_auto_trading, fetch_account_data, fetch_coin_data, check_auto_trading,
                    fetch_trade_logs , get_market_volume , recentTradeLog ,recentProfitLog)

urlpatterns = [
    path('', main_view, name='main-page'),
    path('auto_trade/start/', start_auto_trading, name='start-auto-trade'),
    path('auto_trade/stop/', stop_auto_trading, name='stop-auto-trade'),
    path('api/fetch_account_data/', fetch_account_data, name='fetch-account-data'),
    path('api/fetch_coin_data/', fetch_coin_data, name='fetch-coin-data'),
    path('api/trade_logs/', fetch_trade_logs, name='fetch-trade-logs'),
    path('api/check_auto_trading/', check_auto_trading, name='check_auto_trading'),
    path('api/get_market_volume/', get_market_volume, name='get_market_volume'),
    path('api/getRecntTradeLog/', recentTradeLog, name='recentTradeLog'),
    path('api/recentProfitLog/', recentProfitLog, name='recentProfitLog'),
    ]