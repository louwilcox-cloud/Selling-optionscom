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
        const data = await response.json();
        
        // Handle both array of dates (when no date param) and options chain object (when date param provided)
        if (Array.isArray(data)) {
            return data;
        } else if (data.error) {
            throw new Error(data.error);
        } else {
            // If we got an options chain instead of expiration list, return empty array
            return [];
        }
    }
    
    populateExpirations(expirations) {
        this.expirationSelect.innerHTML = '<option value="">Select expiration date</option>';
        
        if (!expirations || expirations.length === 0) {
            this.expirationSelect.innerHTML = '<option value="">No expirations available</option>';
            return;
        }
        
        expirations.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = this.formatDate(date);
            this.expirationSelect.appendChild(option);
        });
    }
    
    formatDate(dateString) {
        const date = new Date(dateString + 'T00:00:00');
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const daysToExp = Math.round((date.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
        return `${dateString} (${daysToExp} days)`;
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
            
            await this.displayResults(symbol, currentPrice, analysisData);
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
    
    async calculatePCRatios(symbol, expiration) {
        try {
            // Fetch the full options chain to calculate ratios
            const response = await fetch(`/api/get_options_data?symbol=${symbol}&date=${expiration}`);
            if (!response.ok) {
                return { moneyRatio: 'N/A', volumeRatio: 'N/A', oiRatio: 'N/A' };
            }
            
            const chainData = await response.json();
            const calls = chainData.calls || [];
            const puts = chainData.puts || [];
            
            console.log(`Calculating P/C ratios for ${symbol} ${expiration}:`, {
                callsCount: calls.length,
                putsCount: puts.length
            });
            
            // Calculate Money P/C Ratio (Put Premium Value / Call Premium Value)
            // Premium Value = lastPrice × openInterest × 100 (contract multiplier)
            let putsPremium = 0;
            let callsPremium = 0;
            
            puts.forEach(put => {
                const premium = (put.lastPrice || 0) * (put.openInterest || 0) * 100;
                putsPremium += premium;
            });
            
            calls.forEach(call => {
                const premium = (call.lastPrice || 0) * (call.openInterest || 0) * 100;
                callsPremium += premium;
            });
            
            console.log('Premium calculations:', { putsPremium, callsPremium });
            
            // Money P/C Ratio = Put Premium Value / Call Premium Value
            const moneyRatio = callsPremium > 0 ? (putsPremium / callsPremium).toFixed(2) : 'N/A';
            
            // Calculate Volume P/C Ratio (Put Volume / Call Volume)
            const putsVolume = puts.reduce((sum, put) => sum + (put.volume || 0), 0);
            const callsVolume = calls.reduce((sum, call) => sum + (call.volume || 0), 0);
            const volumeRatio = callsVolume > 0 ? (putsVolume / callsVolume).toFixed(2) : 'N/A';
            
            console.log('Volume calculations:', { putsVolume, callsVolume });
            
            // Calculate OI P/C Ratio (Put Open Interest / Call Open Interest)
            const putsOI = puts.reduce((sum, put) => sum + (put.openInterest || 0), 0);
            const callsOI = calls.reduce((sum, call) => sum + (call.openInterest || 0), 0);
            const oiRatio = callsOI > 0 ? (putsOI / callsOI).toFixed(2) : 'N/A';
            
            console.log('OI calculations:', { putsOI, callsOI });
            console.log('Final ratios:', { moneyRatio, volumeRatio, oiRatio });
            
            return { moneyRatio, volumeRatio, oiRatio };
            
        } catch (error) {
            console.error('Error calculating P/C ratios:', error);
            return { moneyRatio: 'Error', volumeRatio: 'Error', oiRatio: 'Error' };
        }
    }
    
    async displayResults(symbol, currentPrice, analysisData) {
        // Display current price
        document.getElementById('currentPrice').textContent = `$${currentPrice.toFixed(2)}`;
        
        // Use the analysis data directly from the /api/results_both endpoint
        if (analysisData.error) {
            throw new Error(analysisData.error);
        }
        
        // Display prediction values using the API response structure
        const volumePrediction = analysisData.volume?.prediction;
        const oiPrediction = analysisData.openInterest?.prediction;
        const avgPrediction = analysisData.average?.prediction;
        
        document.getElementById('bullsValue').textContent = volumePrediction ? `$${volumePrediction.toFixed(2)}` : 'N/A';
        document.getElementById('consensusValue').textContent = avgPrediction ? `$${avgPrediction.toFixed(2)}` : 'N/A';
        document.getElementById('bearsValue').textContent = oiPrediction ? `$${oiPrediction.toFixed(2)}` : 'N/A';
        
        // Calculate proper P/C ratios from the options chain data
        // We need to fetch the options chain to calculate these ratios properly
        const ratios = await this.calculatePCRatios(symbol, this.expirationSelect.value);
        
        document.getElementById('moneyRatio').textContent = ratios.moneyRatio;
        document.getElementById('volumeRatio').textContent = ratios.volumeRatio;
        document.getElementById('oiRatio').textContent = ratios.oiRatio;
        
        this.showResults();
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