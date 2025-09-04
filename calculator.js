// Options Sentiment Analyzer JavaScript
class OptionsCalculator {
    constructor() {
        this.form = document.getElementById('calculatorForm');
        this.symbolInput = document.getElementById('symbol');
        this.expirationSelect = document.getElementById('expiration');
        this.analyzeBtn = document.getElementById('analyzeBtn');
        
        this.loadingState = document.getElementById('loadingState');
        this.errorState = document.getElementById('errorState');
        this.resultsSection = document.getElementById('resultsSection');
        
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.symbolInput.addEventListener('input', this.debounce(this.onSymbolChange.bind(this), 500));
        this.form.addEventListener('submit', this.onFormSubmit.bind(this));
    }
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    async onSymbolChange() {
        const symbol = this.symbolInput.value.trim().toUpperCase();
        if (symbol.length < 1) {
            this.expirationSelect.innerHTML = '<option value="">Enter symbol first</option>';
            return;
        }
        
        try {
            this.expirationSelect.innerHTML = '<option value="">Loading...</option>';
            const expirations = await this.fetchExpirations(symbol);
            this.populateExpirations(expirations);
        } catch (error) {
            this.expirationSelect.innerHTML = '<option value="">Error loading dates</option>';
        }
    }
    
    async fetchExpirations(symbol) {
        const response = await fetch(`/api/get_options_data?symbol=${symbol}`);
        if (!response.ok) {
            throw new Error('Failed to fetch expirations');
        }
        return await response.json();
    }
    
    populateExpirations(expirations) {
        this.expirationSelect.innerHTML = '<option value="">Select expiration date</option>';
        expirations.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = this.formatDate(date);
            this.expirationSelect.appendChild(option);
        });
    }
    
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
    
    async onFormSubmit(e) {
        e.preventDefault();
        
        const symbol = this.symbolInput.value.trim().toUpperCase();
        const expiration = this.expirationSelect.value;
        
        if (!symbol || !expiration) {
            this.showError('Please enter a symbol and select an expiration date');
            return;
        }
        
        this.showLoading();
        
        try {
            const [currentPrice, analysisData] = await Promise.all([
                this.fetchCurrentPrice(symbol),
                this.fetchAnalysis(symbol, expiration)
            ]);
            
            this.displayResults(symbol, currentPrice, analysisData);
        } catch (error) {
            this.showError(`Analysis failed: ${error.message}`);
        }
    }
    
    async fetchCurrentPrice(symbol) {
        const response = await fetch(`/api/quote?symbol=${symbol}`);
        if (!response.ok) {
            throw new Error('Failed to fetch current price');
        }
        const data = await response.json();
        return data.price;
    }
    
    async fetchAnalysis(symbol, expiration) {
        const response = await fetch(`/api/results_both?symbol=${symbol}&date=${expiration}`);
        if (!response.ok) {
            throw new Error('Failed to fetch analysis data');
        }
        return await response.json();
    }
    
    displayResults(symbol, currentPrice, analysisData) {
        // Display current price
        document.getElementById('currentPrice').textContent = `$${currentPrice.toFixed(2)}`;
        
        // Calculate sentiment values from the analysis data
        const results = this.calculateSentiment(analysisData);
        
        // Display prediction values
        document.getElementById('bullsValue').textContent = `$${results.volumePrediction.toFixed(2)}`;
        document.getElementById('consensusValue').textContent = `$${results.avgPrediction.toFixed(2)}`;
        document.getElementById('bearsValue').textContent = `$${results.oiPrediction.toFixed(2)}`;
        
        // Display P/C ratios
        document.getElementById('moneyRatio').textContent = results.ratios.money.toFixed(2);
        document.getElementById('trueRatio').textContent = results.ratios.true.toFixed(2);
        document.getElementById('premiumRatio').textContent = results.ratios.premium.toFixed(2);
        document.getElementById('volumeRatio').textContent = results.ratios.volume.toFixed(2);
        document.getElementById('volOiRatio').textContent = results.ratios.volOi.toFixed(2);
        
        this.showResults();
    }
    
    calculateSentiment(analysisData) {
        const allRows = analysisData.rows;
        const calls = allRows.filter(row => row.Type === 'Call');
        const puts = allRows.filter(row => row.Type === 'Put');
        
        // Filter contributing rows (premium > 0 and volume > 0 or OI > 0)
        const contributingRows = allRows.filter(row => 
            row.AvgLast > 0 && (row.Volume > 0 || row.OI > 0)
        );
        
        // Calculate volume-weighted prediction
        let volumeWeightSum = 0;
        let volumeNumerator = 0;
        let oiWeightSum = 0;
        let oiNumerator = 0;
        
        contributingRows.forEach(row => {
            const premium = row.AvgLast;
            const volume = row.Volume || 0;
            const oi = row.OI || 0;
            const breakeven = row.BreakEven;
            
            // Volume weighting
            if (volume > 0) {
                const volumeWeight = premium * volume;
                volumeWeightSum += volumeWeight;
                volumeNumerator += breakeven * volumeWeight;
            }
            
            // OI weighting
            if (oi > 0) {
                const oiWeight = premium * oi;
                oiWeightSum += oiWeight;
                oiNumerator += breakeven * oiWeight;
            }
        });
        
        const volumePrediction = volumeWeightSum > 0 ? volumeNumerator / volumeWeightSum : 0;
        const oiPrediction = oiWeightSum > 0 ? oiNumerator / oiWeightSum : 0;
        const avgPrediction = (volumePrediction + oiPrediction) / 2;
        
        // Calculate P/C ratios
        const callsPremium = calls.reduce((sum, row) => sum + row.TotPre, 0);
        const putsPremium = puts.reduce((sum, row) => sum + row.TotPre, 0);
        
        const callsVolume = calls.reduce((sum, row) => sum + (row.Volume || 0), 0);
        const putsVolume = puts.reduce((sum, row) => sum + (row.Volume || 0), 0);
        
        const callsOI = calls.reduce((sum, row) => sum + row.OI, 0);
        const putsOI = puts.reduce((sum, row) => sum + row.OI, 0);
        
        return {
            volumePrediction,
            oiPrediction,
            avgPrediction,
            ratios: {
                money: putsPremium / (callsPremium || 1),
                true: putsOI / (callsOI || 1),
                premium: putsPremium / (callsPremium || 1),
                volume: putsVolume / (callsVolume || 1),
                volOi: (putsVolume / (putsOI || 1)) / (callsVolume / (callsOI || 1) || 1)
            }
        };
    }
    
    showLoading() {
        this.hideAll();
        this.loadingState.classList.remove('hidden');
        this.analyzeBtn.disabled = true;
        this.analyzeBtn.textContent = 'Analyzing...';
    }
    
    showResults() {
        this.hideAll();
        this.resultsSection.classList.remove('hidden');
        this.analyzeBtn.disabled = false;
        this.analyzeBtn.textContent = 'Get Analysis';
    }
    
    showError(message) {
        this.hideAll();
        this.errorState.classList.remove('hidden');
        document.getElementById('errorMessage').textContent = message;
        this.analyzeBtn.disabled = false;
        this.analyzeBtn.textContent = 'Get Analysis';
    }
    
    hideAll() {
        this.loadingState.classList.add('hidden');
        this.errorState.classList.add('hidden');
        this.resultsSection.classList.add('hidden');
    }
}

// Initialize the calculator when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new OptionsCalculator();
});