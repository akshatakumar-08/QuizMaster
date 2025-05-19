from flask import Blueprint, render_template, session, redirect, url_for

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('auth.login'))
    return render_template('adm_dashboard.html')

@admin_bp.route('/summary')
def admin_summary():
    if 'admin' not in session:
        return redirect(url_for('auth.login'))
    return render_template('adm_summary.html')
