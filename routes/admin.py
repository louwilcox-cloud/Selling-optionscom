"""Admin routes for Selling-Options.com"""
from flask import Blueprint, request, redirect, url_for, render_template_string
from services.database import get_db_connection
from utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@admin_required
def admin_panel():
    """Admin panel main page"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        
        # Get user statistics
        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = true")
        active_users_result = cur.fetchone()
        active_users = active_users_result[0] if active_users_result else 0
        
        cur.execute("SELECT COUNT(*) FROM watchlists")
        watchlists_result = cur.fetchone()
        total_watchlists = watchlists_result[0] if watchlists_result else 0
        
        # Get recent users
        cur.execute("""
            SELECT id, email, created_at, is_active 
            FROM users 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_users = cur.fetchall()
        
        cur.close()
        conn.close()
        
        admin_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Panel - Selling-options.com</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
        </head>
        <body>
            <div class="admin-container">
                <h1>Admin Panel</h1>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3>Active Users</h3>
                        <p class="stat-number">{{ active_users }}</p>
                    </div>
                    <div class="stat-card">
                        <h3>Total Watchlists</h3>
                        <p class="stat-number">{{ total_watchlists }}</p>
                    </div>
                </div>
                
                <div class="users-section">
                    <h2>Recent Users</h2>
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Email</th>
                                <th>Created</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for user in recent_users %}
                            <tr>
                                <td>{{ user[0] }}</td>
                                <td>{{ user[1] }}</td>
                                <td>{{ user[2] }}</td>
                                <td>{{ user[3].strftime('%Y-%m-%d') if user[3] else 'N/A' }}</td>
                                <td>
                                    <span class="status-badge {{ 'active' if user[4] else 'inactive' }}">
                                        {{ 'Active' if user[4] else 'Inactive' }}
                                    </span>
                                </td>
                                <td>
                                    <a href="{{ url_for('admin.toggle_user', user_id=user[0]) }}" 
                                       class="btn btn-sm">
                                        {{ 'Deactivate' if user[4] else 'Activate' }}
                                    </a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <div class="admin-actions">
                    <a href="{{ url_for('main.index') }}" class="btn">Back to Site</a>
                    <a href="{{ url_for('auth.logout') }}" class="btn btn-secondary">Logout</a>
                </div>
            </div>
        </body>
        </html>
        '''
        
        return render_template_string(admin_html, 
                                    active_users=active_users,
                                    total_watchlists=total_watchlists,
                                    recent_users=recent_users)
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error loading admin panel: {str(e)}", 500

@admin_bp.route('/toggle-user/<int:user_id>')
@admin_required
def toggle_user(user_id):
    """Toggle user active status"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_active = NOT is_active WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('admin.admin_panel'))
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error toggling user: {str(e)}", 500