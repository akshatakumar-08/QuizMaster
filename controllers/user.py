from flask import Blueprint, render_template, session, redirect, url_for, g
import sqlite3

user_bp = Blueprint('user', __name__)

def get_db_connection():
    conn = sqlite3.connect('quiz_master.db')
    conn.row_factory = sqlite3.Row
    return conn

@user_bp.route('/dashboard')
def user_dashboard():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    return render_template('user_dashboard.html')

@user_bp.route('/scores')
def scores():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    conn = get_db_connection()
    scores = conn.execute("SELECT * FROM scores WHERE user_id = ?", (session['user'],)).fetchall()
    conn.close()
    return render_template('scores.html', scores=scores)

@user_bp.route('/summary')
def user_summary():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    return render_template('user_summary.html')
