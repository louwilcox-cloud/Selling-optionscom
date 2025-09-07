"""Main routes for Selling-Options.com"""
from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage with market pulse dashboard"""
    return render_template('index.html')

@main_bp.route('/video-tutorials')
def video_tutorials():
    """Video tutorials page"""
    return render_template('video-tutorials.html')