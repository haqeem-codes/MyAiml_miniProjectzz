import matplotlib
matplotlib.use("Agg")

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, make_response
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import base64
import sqlite3
from io import BytesIO, StringIO
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
import os
import csv

app = Flask(__name__)
app.secret_key = 'secret_key'

# --- SQLite DB Setup ---
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        state TEXT,
        year INTEGER,
        predicted_total INTEGER,
        dangerous_time TEXT,
        accidents_in_time INTEGER
    )
''')
conn.commit()

# --- Load Dataset ---
try:
    df = pd.read_csv('only_road_accidents_data3.csv')
    df['YEAR'] = df['YEAR'].astype(int)
    df = df.sort_values(by="YEAR")
except Exception as e:
    print(f"❌ Error loading dataset: {e}")

required_columns = ['STATE/UT', 'YEAR', 'Total']
if not all(col in df.columns for col in required_columns):
    raise ValueError("❌ Missing required columns in dataset!")

time_periods = ['0-3 hrs. (Night)', '3-6 hrs. (Night)', '6-9 hrs (Day)', '9-12 hrs (Day)', 
                '12-15 hrs (Day)', '15-18 hrs (Day)', '18-21 hrs (Night)', '21-24 hrs (Night)']

def get_base64_image():
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches="tight")
    plt.close()
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode()

def generate_graph(state_data, selected_state, selected_year, y_pred_total, predicted_time_accidents):
    graphs = {}

    plt.figure(figsize=(10, 5))
    plt.bar(state_data['YEAR'], state_data['Total'], color='skyblue', label="Past Data")
    plt.bar(selected_year, int(y_pred_total), color='red', label="Predicted", alpha=0.8)
    plt.xlabel("Year"); plt.ylabel("Total Accidents")
    plt.title(f"Accident Trends in {selected_state}")
    plt.legend(); plt.grid(axis='y', linestyle='--', alpha=0.6)
    graphs["graph_total"] = get_base64_image()

    plt.figure(figsize=(12, 6))
    for period in time_periods:
        if period in state_data.columns:
            plt.plot(state_data['YEAR'], state_data[period], marker='o', label=period)
    plt.xlabel("Year"); plt.ylabel("Accidents")
    plt.title(f"Trends by Time Period in {selected_state}")
    plt.legend(); plt.grid(True)
    graphs["graph_time"] = get_base64_image()

    plt.figure(figsize=(12, 6))
    plt.bar(time_periods, predicted_time_accidents.values(), color='orange', alpha=0.8)
    plt.xlabel("Time Period"); plt.ylabel("Predicted Accidents")
    plt.title(f"Predicted Accidents in {selected_state} ({selected_year})")
    plt.xticks(rotation=30); plt.grid(True)
    graphs["graph_predicted_time"] = get_base64_image()

    return graphs

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        if user:
            session["username"] = username
            return redirect(url_for("predict"))
        else:
            return render_template("login.html", message="❌ Invalid credentials.")
    return render_template("login.html", message="")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("signup.html", message="⚠️ Username already exists.")
    return render_template("signup.html")

@app.route("/predict", methods=["GET", "POST"])
def predict():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        selected_state = request.form["state"]
        selected_year = int(request.form["year"])
        state_data = df[df['STATE/UT'] == selected_state]

        if state_data.shape[0] < 5:
            return jsonify({"error": "⚠️ Not enough data for training."})

        X = state_data[['YEAR']].values
        y_total = state_data[['Total']].values

        scaler_x = StandardScaler()
        scaler_y = StandardScaler()
        X_scaled = scaler_x.fit_transform(X)
        y_total_scaled = scaler_y.fit_transform(y_total)

        model_total = LinearRegression()
        model_total.fit(X_scaled, y_total_scaled)

        year_test_scaled = scaler_x.transform(np.array([[selected_year]]))
        y_pred_total_scaled = model_total.predict(year_test_scaled)
        y_pred_total = int(scaler_y.inverse_transform(y_pred_total_scaled.reshape(-1, 1))[0][0])

        predicted_time_accidents = {}
        for period in time_periods:
            if period in state_data.columns:
                y_time = state_data[[period]].values
                scaler_y_time = StandardScaler()
                y_time_scaled = scaler_y_time.fit_transform(y_time)

                model_time = LinearRegression()
                model_time.fit(X_scaled, y_time_scaled)

                y_pred_time_scaled = model_time.predict(year_test_scaled)
                y_pred_time = scaler_y_time.inverse_transform(y_pred_time_scaled.reshape(-1, 1))
                predicted_time_accidents[period] = int(y_pred_time[0][0])

        most_dangerous_time = max(predicted_time_accidents, key=predicted_time_accidents.get)
        most_accidents = predicted_time_accidents[most_dangerous_time]

        c.execute('''INSERT INTO history (username, state, year, predicted_total, dangerous_time, accidents_in_time)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (session["username"], selected_state, selected_year, y_pred_total, most_dangerous_time, most_accidents))
        conn.commit()

        graphs = generate_graph(state_data, selected_state, selected_year, y_pred_total, predicted_time_accidents)

        return jsonify({
            "predicted_total_accidents": y_pred_total,
            "most_dangerous_time": most_dangerous_time,
            "most_accidents": most_accidents,
            "graph_total": graphs["graph_total"],
            "graph_time": graphs["graph_time"],
            "graph_predicted_time": graphs["graph_predicted_time"]
        })

    return render_template("index.html")

@app.route("/history")
def history():
    if "username" not in session:
        return redirect(url_for("login"))

    c.execute("SELECT state, year, predicted_total, dangerous_time, accidents_in_time FROM history WHERE username=?", (session["username"],))
    rows = c.fetchall()
    return render_template("history.html", data=rows)

@app.route("/download_history")
def download_history():
    if "username" not in session:
        return redirect(url_for("login"))

    c.execute("SELECT state, year, predicted_total, dangerous_time, accidents_in_time FROM history WHERE username=?", (session["username"],))
    rows = c.fetchall()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["State", "Year", "Predicted Total Accidents", "Most Dangerous Time", "Accidents in that Time"])
    writer.writerows(rows)

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=accident_prediction_history.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
