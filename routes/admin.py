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
                    <a href="{{ url_for('admin.manage_watchlists') }}" class="btn">Manage Watchlists</a>
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

@admin_bp.route('/watchlists')
@admin_required
def manage_watchlists():
    """Manage watchlists"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        
        # Get all watchlists with user info
        cur.execute("""
            SELECT w.id, w.name, w.symbols, w.created_at, u.email 
            FROM watchlists w 
            LEFT JOIN users u ON w.user_id = u.id 
            ORDER BY w.created_at DESC
        """)
        watchlists = cur.fetchall()
        
        cur.close()
        conn.close()
        
        watchlist_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Manage Watchlists - Admin</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
        </head>
        <body>
            <div class="admin-container">
                <h1>Manage Watchlists</h1>
                
                <div class="watchlists-section">
                    <table class="admin-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Symbols</th>
                                <th>Owner</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for watchlist in watchlists %}
                            <tr>
                                <td>{{ watchlist[0] }}</td>
                                <td>{{ watchlist[1] }}</td>
                                <td>{{ watchlist[2][:50] }}{% if watchlist[2]|length > 50 %}...{% endif %}</td>
                                <td>{{ watchlist[4] or 'Unknown' }}</td>
                                <td>{{ watchlist[3].strftime('%Y-%m-%d') if watchlist[3] else 'N/A' }}</td>
                                <td>
                                    <a href="{{ url_for('admin.delete_watchlist', watchlist_id=watchlist[0]) }}" 
                                       class="btn btn-sm btn-danger"
                                       onclick="return confirm('Delete this watchlist?')">Delete</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                
                <div class="admin-actions">
                    <a href="{{ url_for('admin.admin_panel') }}" class="btn">Back to Admin</a>
                </div>
            </div>
        </body>
        </html>
        '''
        
        return render_template_string(watchlist_html, watchlists=watchlists)
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error loading watchlists: {str(e)}", 500

@admin_bp.route('/watchlist/<int:watchlist_id>/delete')
@admin_required
def delete_watchlist(watchlist_id):
    """Delete a watchlist"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM watchlists WHERE id = %s", (watchlist_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('admin.manage_watchlists'))
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error deleting watchlist: {str(e)}", 500