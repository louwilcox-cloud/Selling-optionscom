from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import pandas as pd
import os
import yfinance as yf
import numpy as np # Import numpy to handle NaN
import glob 
from pathlib import Path

# Import the analysis function from our bullvsbear.py file
from bullvsbear import analyze_latest_csv

app = Flask(__name__)
# Add a secret key for flash messages to work
app.secret_key = 'a-very-secret-key-you-should-change'

# --- IMPORTANT ---
# Make sure you have yfinance and numpy installed in your environment:
# pip install yfinance numpy

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/learning')
def learning():
    return render_template('learning.html')

@app.route('/tools')
def tools():
    return render_template('tools.html')

@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == 'POST':
        email = request.form['email']
        # Open waitlist.txt in 'append' mode and save the email
        with open('waitlist.txt', 'a') as f:
            f.write(email + '\n')
        flash('Thank you for joining the waitlist!')
        return redirect(url_for('index'))
    return render_template('join.html')


@app.route('/run-naked-puts')
def run_naked_puts():
    try:
        import glob
        import os

        # Look for any CSV file in the directory
        files = glob.glob("data/naked_puts/*.csv")
        if not files:
            raise FileNotFoundError("No CSV files found in data/naked_puts/")

        # Pick the first CSV file found (you can sort if you want newest first)
        data_path = files[0]

        # Read CSV and handle thousands separators
        df = pd.read_csv(data_path, thousands=',')

        # Clean and convert columns
        df['Ann Rtn'] = (
            df['Ann Rtn']
            .astype(str)
            .str.replace('%', '', regex=False)
            .str.replace(',', '', regex=False)
            .astype(float)
        )
        df['Profit Prob'] = (
            df['Profit Prob']
            .astype(str)
            .str.replace('%', '', regex=False)
            .str.replace(',', '', regex=False)
            .astype(float)
        )
        df['Delta'] = pd.to_numeric(df['Delta'], errors='coerce')
        df['Volume'] = pd.to_numeric(
            df['Volume'].astype(str).str.replace(',', ''), errors='coerce'
        )
        df['Open Int'] = pd.to_numeric(
            df['Open Int'].astype(str).str.replace(',', ''), errors='coerce'
        )

        # Apply filters
        filtered = df[
            (df['Profit Prob'] >= 70) &
            (df['Ann Rtn'] > 0) &
            (df['Delta'] <= 0.3) &
            (df['Volume'] > 100) &
            (df['Open Int'] > 100)
        ]

        # Top 5 sorted by annual return
        top5 = filtered.sort_values(by='Ann Rtn', ascending=False).head(5)

        # Render table
        table_html = top5.to_html(index=False, classes='dataframe')
        return render_template("naked_put_results.html", table=table_html)

    except Exception as e:
        return f"<h2>Error running Naked Puts script: {e}</h2><a href='/'>Back to Home</a>"

@app.route('/bull-vs-bear')
def bull_vs_bear():
    results = analyze_latest_csv(data_dir="./data/bull_vs_bear")
    return render_template('bullvsbear.html', results=results)

@app.route('/stock-analysis')
def stock_analysis():
    return render_template('StockTechSed.html')

@app.route('/price-calculator')
def price_calculator():
    """Renders the new Options Sentiment Analyzer page."""
    return render_template('price_calculator.html')

@app.route('/api/get_options_data')
def get_options_data():
    """
    Server-side endpoint to fetch options data from Yahoo Finance.
    This avoids client-side CORS and authentication issues.
    """
    symbol = request.args.get('symbol')
    exp_date = request.args.get('date')

    if not symbol:
        return jsonify({"error": "Stock symbol is required"}), 400

    try:
        ticker = yf.Ticker(symbol)
        
        if not exp_date:
            # Request for expiration dates
            expirations = ticker.options
            if not expirations:
                if not ticker.info.get('regularMarketPrice'):
                     raise ValueError(f"Invalid symbol or no market data: {symbol}")
                return jsonify({"error": f"No options data found for {symbol}"}), 404
            return jsonify(expirations)
        else:
            # Request for option chain for a specific date
            chain = ticker.option_chain(exp_date)
            if chain.calls.empty and chain.puts.empty:
                 return jsonify({"error": "No options chain data available for this date."}), 404
            
            # **BUG FIX:** Replace NaN with 0 before sending to client
            calls_df = chain.calls.replace({np.nan: 0})
            puts_df = chain.puts.replace({np.nan: 0})

            calls_data = calls_df.to_dict(orient='records')
            puts_data = puts_df.to_dict(orient='records')
            
            return jsonify({
                "calls": calls_data,
                "puts": puts_data
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
