import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc, precision_recall_curve
import shutil


def dayTradingView():
    # ✅ 데이터 불러오기
    tf.config.optimizer.set_jit(True)  # XLA (Accelerated Linear Algebra) 활성화
    save_path = "/Users/hongbookpro/Downloads/KRW-BTC_15m_data.csv"
    df = pd.read_csv(save_path)

    # ✅ 결측값 제거
    df = df.dropna()

    # ✅ 이상치 제거 (고가가 저가보다 낮은 경우)
    df = df[(df["high_price"] >= df["low_price"]) & (df["trade_price"] > 0)]

    # ✅ 기술적 지표 추가 (RSI, MACD 적용)
    df = calculate_rsi(df)
    df = calculate_macd(df)

    # ✅ 데이터 정규화 (Min-Max Scaling)
    scaler = MinMaxScaler(feature_range=(0,1))
    scaled_features = ["opening_price", "high_price", "low_price", "trade_price", "candle_acc_trade_volume", "rsi", "macd", "macd_signal"]
    df[scaled_features] = scaler.fit_transform(df[scaled_features])

    # ✅ 타겟 변수 생성 (다음 캔들 가격 상승 여부)
    df["target"] = (df["trade_price"].shift(-1) > df["trade_price"]).astype(int)
    df = df.dropna()

    # ✅ 데이터셋 준비 (LSTM 입력 형식 변환)
    X, y = prepare_lstm_data(df, scaled_features, time_steps=60)

    # ✅ 학습/테스트 데이터 분할
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # ✅ LSTM 모델 학습
    model = train_lstm_model(X_train, y_train, X_test, y_test)

    # ✅ 모델 평가 (ROC Curve & AUC)
    RocAndAuc(model, X_test, y_test)

    model.save("lstm_model.h5")
    shutil.make_archive("lstm_model", 'zip', ".", "/Users/hongbookpro/Downloads/lstm_model.h5")

def prepare_lstm_data(df, features, time_steps=60):
    """ LSTM 모델 입력 데이터 생성 """
    X, y = [], []
    for i in range(len(df) - time_steps):
        X.append(df[features].iloc[i:i+time_steps].values)  # 60개 데이터 입력
        y.append(df["target"].iloc[i+time_steps])           # 1개 데이터 예측값

    return np.array(X), np.array(y)

def train_lstm_model(X_train, y_train, X_test, y_test):
    """ LSTM 모델 학습 """
    model = keras.Sequential([
        LSTM(32, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(25),
        Dense(1, activation="sigmoid")  # 0~1 확률 예측
    ])

    model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])

    # ✅ 모델 학습
    model.fit(X_train, y_train, epochs=10, chch_size=128, vervose=1,validation_data=(X_test, y_test))

    # ✅ 정확도 평가
    loss, accuracy = model.evaluate(X_test, y_test)
    print(f"🎯 LSTM 모델 정확도: {accuracy:.2f}")

    return model

def RocAndAuc(model, X_test, y_test):
    """ 📌 ROC Curve & Precision-Recall Curve 분석 """
    y_probs = model.predict(X_test)

    # ROC Curve 계산
    fpr, tpr, _ = roc_curve(y_test, y_probs)
    roc_auc = auc(fpr, tpr)

    # Precision-Recall Curve 계산
    precision, recall, _ = precision_recall_curve(y_test, y_probs)

    # 그래프 출력
    plt.figure(figsize=(12, 5))

    # ROC Curve
    plt.subplot(1, 2, 1)
    plt.plot(fpr, tpr, color="blue", label=f"AUC = {roc_auc:.2f}")
    plt.plot([0, 1], [0, 1], "r--")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve")
    plt.legend()

    # Precision-Recall Curve
    plt.subplot(1, 2, 2)
    plt.plot(recall, precision, color="green")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Precision-Recall Curve")

    plt.show()

def calculate_rsi(df, period=14):
    """ 📌 RSI 계산 함수 """
    delta = df["trade_price"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df

def calculate_macd(df, short=12, long=26, signal=9):
    """ 📌 MACD 계산 함수 """
    df["ema_short"] = df["trade_price"].ewm(span=short, adjust=False).mean()
    df["ema_long"] = df["trade_price"].ewm(span=long, adjust=False).mean()
    df["macd"] = df["ema_short"] - df["ema_long"]
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    return df

if __name__ == "__main__":
    dayTradingView()
