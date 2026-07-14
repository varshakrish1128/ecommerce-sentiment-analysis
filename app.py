# app.py
import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'psp_app.db')
DATASET_PATH = os.path.join(BASE_DIR, 'dataset', 'ecommerce_reviews.csv')

app = Flask(__name__)
app.secret_key = 'replace_this_with_a_random_secret_for_production'  # change for production

analyzer = SentimentIntensityAnalyzer()

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def classify_sentiment(text):
    if not isinstance(text, str) or not text.strip():
        return 'neutral'
    vs = analyzer.polarity_scores(text)
    c = vs['compound']
    if c >= 0.05:
        return 'positive'
    elif c <= -0.05:
        return 'negative'
    else:
        return 'neutral'

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Signup
@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        if not username or not password:
            flash('Provide username and password', 'error')
            return redirect(url_for('signup'))
        pw_hash = generate_password_hash(password)
        conn = get_db_conn()
        try:
            conn.execute("INSERT INTO users (username,password) VALUES (?, ?)", (username, pw_hash))
            conn.commit()
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
            return redirect(url_for('signup'))
        finally:
            conn.close()
        flash('Account created — please login', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

# Login
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        conn = get_db_conn()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session.get('username'))

# Serve dataset file (optional)
@app.route('/dataset/<path:filename>')
def serve_dataset(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'dataset'), filename)

# API: get reviews filtered by product query
@app.route('/api/get_reviews', methods=['GET'])
def api_get_reviews():
    if 'user_id' not in session:
        return jsonify({'error':'unauthenticated'}), 401

    # query param: q (product name substring)
    q = request.args.get('q','').strip().lower()
    try:
        df = pd.read_csv(DATASET_PATH)
    except Exception as e:
        return jsonify({'error':'failed reading dataset', 'details': str(e)}), 500

    # ensure expected columns
    expected = {'product_name','platform','review','rating'}
    if not expected.issubset(set(df.columns)):
        return jsonify({'error':'dataset missing columns','expected':list(expected)}), 400

    # filter by product substring if provided
    if q:
        df = df[df['product_name'].astype(str).str.lower().str.contains(q)]

    # compute sentiment for each review (cache into a new column)
    df['review'] = df['review'].fillna('')
    df['sentiment'] = df['review'].apply(classify_sentiment)
    # ensure rating numeric
    df['rating'] = pd.to_numeric(df['rating'], errors='coerce')

    # build response: per-platform aggregated + flat reviews
    platforms = {}
    for plat, group in df.groupby('platform'):
        total = len(group)
        pos = int((group['sentiment']=='positive').sum())
        neu = int((group['sentiment']=='neutral').sum())
        neg = int((group['sentiment']=='negative').sum())
        avg_rating = None
        if group['rating'].notna().any():
            avg_rating = round(float(group['rating'].dropna().mean()), 2)
        platforms[plat] = {
            'total': total,
            'positive': pos,
            'neutral': neu,
            'negative': neg,
            'avg_rating': avg_rating
        }

    # flat reviews list (limit to 500)
    reviews = []
    for _, row in df.iterrows():
        reviews.append({
            'product_name': row['product_name'],
            'platform': row['platform'],
            'review': row['review'],
            'rating': None if pd.isna(row['rating']) else int(row['rating']),
            'sentiment': row['sentiment']
        })

    return jsonify({'ok': True, 'platforms': platforms, 'reviews': reviews})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
