"""Admin routes for Selling-Options.com"""
from flask import Blueprint, request, redirect, url_for, render_template
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
        
        # Get recent users with admin status and login info
        cur.execute("""
            SELECT u.id, u.email, u.created_at, u.is_active, u.last_login, u.login_count,
                   CASE WHEN a.user_id IS NOT NULL THEN 'Admin' ELSE 'User' END as role,
                   CASE WHEN a.user_id IS NOT NULL THEN true ELSE false END as is_admin
            FROM users u
            LEFT JOIN admin_users a ON u.id = a.user_id 
            ORDER BY u.created_at DESC 
            LIMIT 10
        """)
        recent_users = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return render_template('admin_panel.html', 
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
            LEFT JOIN users u ON w.created_by = u.id 
            ORDER BY w.created_at DESC
        """)
        watchlists = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return render_template('manage_watchlists.html', watchlists=watchlists)
        
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

@admin_bp.route('/make-admin/<int:user_id>')
@admin_required
def make_admin(user_id):
    """Make user an admin"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        # Check if user is already admin
        cur.execute("SELECT 1 FROM admin_users WHERE user_id = %s", (user_id,))
        if not cur.fetchone():
            # Add to admin_users table
            cur.execute("INSERT INTO admin_users (user_id, granted_at) VALUES (%s, NOW())", (user_id,))
            conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('admin.admin_panel'))
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error making user admin: {str(e)}", 500

@admin_bp.route('/remove-admin/<int:user_id>')
@admin_required  
def remove_admin(user_id):
    """Remove admin privileges from user"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM admin_users WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('admin.admin_panel'))
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error removing admin privileges: {str(e)}", 500

@admin_bp.route('/delete-user/<int:user_id>')
@admin_required
def delete_user(user_id):
    """Delete a user permanently"""
    conn = get_db_connection()
    if not conn:
        return "Database connection error", 500
    
    try:
        cur = conn.cursor()
        # First remove from admin_users if they are admin
        cur.execute("DELETE FROM admin_users WHERE user_id = %s", (user_id,))
        # Then delete the user
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('admin.admin_panel'))
        
    except Exception as e:
        if conn:
            conn.close()
        return f"Error deleting user: {str(e)}", 500