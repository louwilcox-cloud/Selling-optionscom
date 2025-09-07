"""Calculator routes for Selling-Options.com"""
from flask import Blueprint, render_template

calculator_bp = Blueprint('calculator', __name__)

@calculator_bp.route('/calculator')
def calculator():
    """Options calculator page"""
    return render_template('calculator.html')

# Note: The calculator functionality is primarily frontend JavaScript,
# so this route mainly serves the template. The actual calculations
# happen client-side in calculator.js which will be moved to static/