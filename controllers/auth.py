from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import sqlite3

auth_bp = Blueprint('auth', __name__)

# Database Connection Helper
def get_db_connection():
    conn = sqlite3.connect('quiz_master.db')
    conn.row_factory = sqlite3.Row
    return conn

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        admin = conn.execute("SELECT * FROM admin WHERE username = ? AND password = ?", (username, password)).fetchone()
        conn.close()

        if user:
            session['user'] = user['username']
            return redirect(url_for('user.user_dashboard'))
        elif admin:
            session['admin'] = admin['username']
            return redirect(url_for('admin.admin_dashboard'))
        else:
            flash("Invalid credentials!", "danger")
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password, full_name) VALUES (?, ?, ?)", (username, password, full_name))
            conn.commit()
            flash("Registration successful! Please log in.", "success")
        except sqlite3.IntegrityError:
            flash("User already exists.", "danger")
        conn.close()
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
