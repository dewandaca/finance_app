from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
DATABASE = 'database.db'

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash FROM users WHERE id = ?', (user_id,))
        user_data = cursor.fetchone()
        if user_data:
            return User(id=user_data[0], username=user_data[1], password_hash=user_data[2])
        return None

# Initialize database
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()

# Format mata uang
def format_currency(amount):
    if amount is None:
        return "Rp.0"
    return f"Rp.{amount:,.0f}".replace(",", ".")

# Routes
@app.route('/')
@login_required
def index():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Ambil semua transaksi pengguna yang sedang login
        cursor.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC', (current_user.id,))
        transactions = cursor.fetchall()

        # Hitung total pemasukan dan pengeluaran
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "income"', (current_user.id,))
        total_income = cursor.fetchone()[0] or 0

        cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "expense"', (current_user.id,))
        total_expense = cursor.fetchone()[0] or 0

        # Hitung total pemasukan dan pengeluaran per bulan
        cursor.execute('''
            SELECT strftime('%Y-%m', date) AS month, 
                   SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS total_income,
                   SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS total_expense
            FROM transactions
            WHERE user_id = ?
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month DESC
        ''', (current_user.id,))
        monthly_totals = cursor.fetchall()

        # Format data untuk Chart.js
        months = [row[0] for row in monthly_totals]
        income_data = [row[1] for row in monthly_totals]
        expense_data = [row[2] for row in monthly_totals]

    return render_template('index.html', 
                           transactions=transactions, 
                           total_income=total_income, 
                           total_expense=total_expense, 
                           monthly_totals=monthly_totals,
                           months=months,
                           income_data=income_data,
                           expense_data=expense_data,
                           format_currency=format_currency)
@app.route('/add', methods=['POST'])
@login_required
def add_transaction():
    description = request.form['description']
    amount = float(request.form['amount'])
    transaction_type = request.form['type']
    date = request.form['date']

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, description, amount, type, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (current_user.id, description, amount, transaction_type, date))
        conn.commit()

    flash('Transaction added successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_transaction(id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM transactions WHERE id = ? AND user_id = ?', (id, current_user.id))
        conn.commit()

    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        transaction_type = request.form['type']
        date = request.form['date']

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE transactions
                SET description = ?, amount = ?, type = ?, date = ?
                WHERE id = ? AND user_id = ?
            ''', (description, amount, transaction_type, date, id, current_user.id))
            conn.commit()

        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('index'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions WHERE id = ? AND user_id = ?', (id, current_user.id))
        transaction = cursor.fetchone()

    if not transaction:
        flash('Transaction not found', 'error')
        return redirect(url_for('index'))

    return render_template('edit.html', transaction=transaction)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
            user_data = cursor.fetchone()

            if user_data and check_password_hash(user_data[2], password):
                user = User(id=user_data[0], username=user_data[1], password_hash=user_data[2])
                login_user(user)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = generate_password_hash(password)

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
                conn.commit()
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already exists', 'error')

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)