from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import yfinance as yf
import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.offline as pyo
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from sklearn.preprocessing import MinMaxScaler
import feedparser
import bcrypt
import os
import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Clear session on every server restart
@app.before_request
def clear_session_on_restart():
    if not os.path.exists("server_restart.lock"):
        session.clear()
        open("server_restart.lock", "w").close()

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password BLOB NOT NULL
        )
    """)
    
    # Update history table to include last_traded_price and predicted_price
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            crypto_symbol TEXT NOT NULL,
            last_traded_price REAL NOT NULL,
            predicted_price REAL NOT NULL,
            graph_html TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


init_db()  # Ensure database is initialized

# Fetch cryptocurrency data from Yahoo Finance
def get_crypto_data(symbol):
    crypto = yf.Ticker(symbol)
    data = crypto.history(period="2y")
    info = crypto.info
    return data, info

# Modify predict_crypto to return last traded price
def predict_crypto(symbol):
    data, info = get_crypto_data(symbol)
    if data.empty:
        return None, None, None, None  # Added last_traded_price

    df = data[['Close']].copy()
    scaler = MinMaxScaler(feature_range=(0,1))
    df_scaled = scaler.fit_transform(df)

    X, y = [], []
    for i in range(60, len(df_scaled)):
        X.append(df_scaled[i-60:i, 0])
        y.append(df_scaled[i, 0])

    X, y = np.array(X), np.array(y)
    X = np.reshape(X, (X.shape[0], X.shape[1], 1))

    model = Sequential([
        LSTM(50, return_sequences=True, input_shape=(X.shape[1], 1)),
        LSTM(50, return_sequences=False),
        Dense(25),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mean_squared_error')
    model.fit(X, y, epochs=10, batch_size=16, verbose=0)

    # Predict next 60 days
    future_prices = []
    last_60_days = df_scaled[-60:]

    for _ in range(60):
        X_test = np.reshape(last_60_days, (1, last_60_days.shape[0], 1))
        pred_price = model.predict(X_test)
        future_prices.append(pred_price[0][0])
        last_60_days = np.append(last_60_days[1:], pred_price, axis=0)

    future_prices = scaler.inverse_transform(np.array(future_prices).reshape(-1,1))

    last_traded_price = round(df.iloc[-1, 0], 2)  # Get last closing price

    return data, info, future_prices.flatten().tolist(), last_traded_price  # ✅ Ensure list format

   

# Generate interactive cryptocurrency price graph
def plot_crypto(data, future_prices):
    past_trace = go.Scatter(
        x=data.index,
        y=data['Close'],
        mode='lines',
        name='Past Prices',
        line=dict(color='#FF4500', width=2)
    )

    future_dates = pd.date_range(start=data.index[-1], periods=60, freq='D')
    future_trace = go.Scatter(
        x=future_dates,
        y=future_prices,
        mode='lines',
        name='Predicted Prices (Next 60 Days)',
        line=dict(color='#FFD700', width=2, dash='dot')
    )

    layout = go.Layout(
        xaxis=dict(title="Date"),
        yaxis=dict(title="Price (USD)"),
        plot_bgcolor='black',
        paper_bgcolor='black',
        font=dict(color='white'),
    )

    fig = go.Figure(data=[past_trace, future_trace], layout=layout)
    return pyo.plot(fig, output_type='div')

def save_history(username, symbol, last_traded_price, predicted_price, plot_html):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ✅ Ensure `predicted_price` is a float before storing
    predicted_price = float(predicted_price)  

    cursor.execute("""
        INSERT INTO history (username, crypto_symbol, last_traded_price, predicted_price, graph_html, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, symbol, last_traded_price, predicted_price, plot_html, timestamp))
    
    conn.commit()
    conn.close()



# Fetch cryptocurrency news
def get_crypto_news(symbol):
    url = f"https://news.google.com/rss/search?q={symbol}+cryptocurrency"
    feed = feedparser.parse(url)

    news_data = []
    for entry in feed.entries[:5]:  # Get top 5 news articles
        news_data.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.published,
            "summary": entry.get("summary", "Click the link to read more.")
        })

    return news_data

@app.route("/news/<symbol>")
def news(symbol):
    if "user" not in session:
        return redirect(url_for("auth"))
    
    news_data = get_crypto_news(symbol)  # Fetch news for the entered crypto
    
    return render_template("news.html", symbol=symbol, news_data=news_data)


@app.route("/")
def home():
    """Always redirect to login unless user is authenticated"""
    if "user" in session:
        return redirect(url_for("index"))  # If logged in, go to index page
    return redirect(url_for("auth"))  # Else, go to login page

@app.route("/index", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect(url_for("auth"))

    if request.method == "POST":
        symbol = request.form["symbol"].upper()
        data, info, future_prices, last_traded_price = predict_crypto(symbol)

        if data is None:
            return render_template("index.html", error="Invalid cryptocurrency symbol!")
        
        predicted_price = round(float(future_prices[-1]), 2)  # ✅ Extract last price correctly

        plot = plot_crypto(data, future_prices)
        
         # ✅ Ensure float before saving
        save_history(session["user"], symbol, last_traded_price, predicted_price, plot)


        return render_template("index.html", symbol=symbol, 
                               predicted_price=predicted_price,
                               last_traded_price=last_traded_price, 
                               plot=plot, info=info, news=get_crypto_news(symbol))

    return render_template("index.html")
@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("auth"))

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # ✅ Fetch last traded price & predicted price
    cursor.execute("""
        SELECT crypto_symbol, last_traded_price, predicted_price, graph_html, timestamp 
        FROM history 
        WHERE username=?
    """, (session["user"],))
    
    history_data = cursor.fetchall()
    conn.close()

    # Convert fetched data into a list of dictionaries
    history_list = []
    for row in history_data:
        try:
            predicted_price = round(float(row[2]), 2) if row[2] else "N/A"  # ✅ Convert & round to 2 decimal places  # ✅ Convert bytes to float
        except (ValueError, TypeError):
            predicted_price = "N/A"  # If conversion fails, show "N/A"

        history_list.append({
            'symbol': row[0],
            'last_traded_price': row[1],  
            'predicted_price': predicted_price,  # ✅ Fix binary issue
            'plot': row[3],  
            'date': row[4]
        })

    return render_template("history.html", history=history_list)



@app.route("/auth", methods=["GET", "POST"])
def auth():
    """Handles user login and signup"""
    if "user" in session:
        return redirect(url_for("index"))  # If already logged in, redirect to index

    if request.method == "POST":
        action = request.form["action"]
        username = request.form["username"]
        password = request.form["password"].encode("utf-8")
        
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        
        if action == "login":
            cursor.execute("SELECT password FROM users WHERE username=?", (username,))
            user = cursor.fetchone()
            conn.close()
            if user:
                hashed_password = user[0]  # Fetch hashed password (stored as BLOB)
                if bcrypt.checkpw(password, hashed_password):
                    session["user"] = username
                    return redirect(url_for("index"))
            return render_template("login.html", error="Invalid username or password!")

        elif action == "signup":
            hashed_password = bcrypt.hashpw(password, bcrypt.gensalt())
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
                conn.commit()
                conn.close()
                return redirect(url_for("auth"))  # Redirect back to login after signup
            except:
                return render_template("login.html", error="Username already exists!")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))

if __name__ == "__main__":
    # Remove lock file when server stops
    if os.path.exists("server_restart.lock"):
        os.remove("server_restart.lock")
    app.run(debug=True)
    