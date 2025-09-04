# Options Sentiment Analyzer

## Overview

This is a Flask-based web application for options trading analysis, inspired by TipRanks.com. The system provides a comprehensive suite of tools for options traders including sentiment analysis, options calculators, risk assessment, and data visualization. The application focuses on helping traders make data-driven decisions by analyzing options chains, calculating probabilities, and providing real-time market insights.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Static HTML/CSS/JS**: Traditional server-side rendered pages with vanilla JavaScript
- **Responsive Design**: Mobile-first approach using CSS Grid and Flexbox
- **Component Structure**: Modular JavaScript classes (OptionsCalculator) for interactive features
- **Styling Framework**: Custom CSS inspired by modern financial platforms, with TipRanks-style layout patterns

### Backend Architecture
- **Framework**: Flask (Python) - lightweight web framework for API endpoints
- **API Structure**: RESTful endpoints following `/api/` pattern
- **Data Processing**: Pandas for data manipulation and calculations
- **Error Handling**: Safe data conversion with fallback values for financial calculations

### Core API Endpoints
- `/api/quote` - Stock quote data
- `/api/get_options_data` - Options chain data with optional date filtering
- `/api/results_both` - Combined analysis results for calls and puts
- `/api/prediction` - Options sentiment predictions

### Data Layer
- **Primary Data Source**: Yahoo Finance API via yfinance library
- **Data Format**: JSON responses with standardized field structure
- **Real-time Processing**: Live options chain fetching and calculation
- **Data Validation**: Safe type conversion with mathematical validation for financial data

### Key Design Patterns
- **Separation of Concerns**: Clear division between data fetching, processing, and presentation
- **Defensive Programming**: Extensive error handling for financial data edge cases
- **Modular Structure**: Reusable functions for common operations (strike price formatting, volume calculations)

## External Dependencies

### Third-Party Services
- **Yahoo Finance**: Primary data provider for stock quotes and options chains
- **yfinance Library**: Python wrapper for Yahoo Finance API

### JavaScript Libraries
- **Native Browser APIs**: Fetch API for HTTP requests, DOM manipulation
- **No heavy frameworks**: Vanilla JavaScript approach for better performance

### Development Tools
- **Node.js**: For development server and package management
- **http-server**: Static file serving during development

### Python Dependencies
- **Flask**: Web framework and API routing
- **pandas**: Data analysis and manipulation
- **yfinance**: Financial data retrieval
- **math**: Mathematical operations and validation

The application is designed to be lightweight and performant, with minimal external dependencies while providing comprehensive options trading analysis capabilities.