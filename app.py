import os
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
from openai import OpenAI
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = 'your-secret-key'


# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    with sqlite3.connect('fridge.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS fridge_items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            image_path TEXT,
            expiration_date TEXT,
            status TEXT,
            username TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')

from datetime import datetime, timedelta


@app.route('/')
def index():
    with sqlite3.connect('fridge.db') as conn:
        conn.row_factory = sqlite3.Row
        items = conn.execute("SELECT * FROM fridge_items WHERE status='in' AND username=?",
                             (session.get('user'),)).fetchall()

    # Find soon-to-expire items
    today = datetime.today()
    soon_expiring = [item for item in items if
                     datetime.strptime(item['expiration_date'], "%Y-%m-%d") <= today + timedelta(days=2)]

    # List of all food names in fridge
    fridge_names = [item['name'].lower() for item in items]

    number = len(fridge_names)



    return render_template("index.html", items=items, soon_expiring=soon_expiring, number = number)
@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect('fridge.db') as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()

        if user:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid username or password.')
    return render_template('login.html')


@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get("message", "").strip()
    username = session.get('user')

    if not user_msg or not username:
        return {"reply": "Please log in and enter a valid message."}

    # Fetch user's fridge items
    with sqlite3.connect("fridge.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, expiration_date FROM fridge_items WHERE status='in' AND username=?", (username,)).fetchall()
        items_list = [f"{row['name']} (expires: {row['expiration_date']})" for row in rows]
        fridge_summary = ", ".join(items_list) if items_list else "nothing right now"

    # Build prompt
    prompt = f"My fridge currently contains: {fridge_summary}. {user_msg}"

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a smart fridge assistant that suggests recipes or advice based on fridge contents. Please answer within 3-4 sentences. "},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    content = response.choices[0].message.content.strip()
    return {"reply": content}



@app.route('/add', methods=['POST'])
def add():
    print("Called")
    name = request.form['name']
    expiration_date = request.form['expiration']
    image = request.files['image']
    filename = secure_filename(image.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(filepath)

    with sqlite3.connect('fridge.db') as conn:
        conn.execute(
            "INSERT INTO fridge_items (name, image_path, expiration_date, status, username) VALUES (?, ?, ?, 'in', ?)",
            (name, filepath, expiration_date, session.get('user')))

        items = conn.execute("SELECT * FROM fridge_items WHERE status='in'").fetchall()

    if not items:
        return "<div class='empty-state'><p>Your fridge is currently empty.</p></div>"

    html = ""
    for item in items:
        html += f"""
        <div class='col-md-6 mb-3'>
          <div class='card shadow-sm'>
            <img src='{item[2]}' class='card-img-top' style='height:200px; object-fit:cover;'>
            <div class='card-body'>
              <h5 class='card-title'>{item[1]}</h5>
              <p>Expires on: {item[3]}</p>
              <a href='/take_out/{item[0]}' class='btn btn-warning w-100'>Take Out</a>
            </div>
          </div>
        </div>
        """
    return html

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect('fridge.db') as conn:
            try:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                return render_template('register.html', error="Username already exists.")

    return render_template('register.html')

@app.route('/take_out/<int:item_id>')
def take_out(item_id):
    with sqlite3.connect('fridge.db') as conn:
        conn.execute("UPDATE fridge_items SET status='out' WHERE id=?", (item_id,))
    return redirect(url_for('index'))

@app.route('/history')
def history():
    conn = sqlite3.connect('fridge.db')
    logs = conn.execute("SELECT * FROM fridge_items ORDER BY timestamp DESC").fetchall()
    conn.close()
    return render_template('history.html', logs=logs)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
