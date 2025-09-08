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

        // Display raw expirations data for debugging
        document.getElementById('rawExpirations').textContent = JSON.stringify(data, null, 2);
        console.log('Raw expirations response:', data);

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

        // Show results section immediately so we can see debug data
        this.showResults();
        document.getElementById('rawExpirations').textContent = 'Loading...';
        document.getElementById('rawOptionsChain').textContent = 'Loading...';
        document.getElementById('calculationSteps').innerHTML = 'Loading calculations...';

        this.analyzeBtn.disabled = true;
        this.analyzeBtn.textContent = 'Analyzing...';

        try {
            const [currentPrice, analysisData] = await Promise.all([
                this.fetchCurrentPrice(symbol),
                this.fetchAnalysis(symbol, expiration)
            ]);

            await this.displayResults(symbol, currentPrice, analysisData);
        } catch (error) {
            this.showError(`Analysis failed: ${error.message}`);
        } finally {
            this.analyzeBtn.disabled = false;
            this.analyzeBtn.textContent = 'Get Analysis';
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
                return { volumeRatio: 'N/A', oiRatio: 'N/A' };
            }

            const chainData = await response.json();

            // Display raw options chain data for debugging
            document.getElementById('rawOptionsChain').textContent = JSON.stringify(chainData, null, 2);

            const calls = chainData.calls || [];
            const puts = chainData.puts || [];

            console.log(`Calculating P/C ratios for ${symbol} ${expiration}:`, {
                callsCount: calls.length,
                putsCount: puts.length
            });

            // Calculate Put/Call ratios from Polygon data
            let totalPutVolume = 0;
            let totalCallVolume = 0;
            let totalPutOI = 0;
            let totalCallOI = 0;

            let volumeDetails = [`Volume calculations for ${symbol} ${expiration}:`];
            let oiDetails = [`OI calculations for ${symbol} ${expiration}:`];

            // Sum up puts
            if (chainData.puts && Array.isArray(chainData.puts)) {
                chainData.puts.forEach(put => {
                    const volume = parseInt(put.volume) || 0;
                    const oi = parseInt(put.openInterest) || 0;
                    totalPutVolume += volume;
                    totalPutOI += oi;
                    if (volume > 0 || oi > 0) {
                        volumeDetails.push(`Put ${put.strike}: volume=${volume}`);
                        oiDetails.push(`Put ${put.strike}: OI=${oi}`);
                    }
                });
            }

            // Sum up calls  
            if (chainData.calls && Array.isArray(chainData.calls)) {
                chainData.calls.forEach(call => {
                    const volume = parseInt(call.volume) || 0;
                    const oi = parseInt(call.openInterest) || 0;
                    totalCallVolume += volume;
                    totalCallOI += oi;
                    if (volume > 0 || oi > 0) {
                        volumeDetails.push(`Call ${call.strike}: volume=${volume}`);
                        oiDetails.push(`Call ${call.strike}: OI=${oi}`);
                    }
                });
            }

            // Add totals and final calculations
            volumeDetails.push(`\nTotals:`);
            volumeDetails.push(`Total Put Volume: ${totalPutVolume}`);
            volumeDetails.push(`Total Call Volume: ${totalCallVolume}`);
            volumeDetails.push(`Put/Call Volume Ratio: ${totalCallVolume > 0 ? (totalPutVolume / totalCallVolume).toFixed(2) : 'N/A (no call volume)'}`);

            oiDetails.push(`\nTotals:`);
            oiDetails.push(`Total Put OI: ${totalPutOI}`);
            oiDetails.push(`Total Call OI: ${totalCallOI}`);
            oiDetails.push(`Put/Call OI Ratio: ${totalCallOI > 0 ? (totalPutOI / totalCallOI).toFixed(2) : 'N/A (no call OI)'}`);

            // Display calculation steps
            document.getElementById('volumeCalcs').innerHTML = volumeDetails.join('<br>');
            document.getElementById('oiCalcs').innerHTML = oiDetails.join('<br>');

            console.log(`Totals - Put Volume: ${totalPutVolume}, Call Volume: ${totalCallVolume}, Put OI: ${totalPutOI}, Call OI: ${totalCallOI}`);

            // Calculate ratios (Put/Call)
            const volumePCRatio = totalCallVolume > 0 ? (totalPutVolume / totalCallVolume).toFixed(2) : 'N/A';
            const oiPCRatio = totalCallOI > 0 ? (totalPutOI / totalCallOI).toFixed(2) : 'N/A';

            console.log(`Final P/C Ratios - Volume: ${volumePCRatio}, OI: ${oiPCRatio}`);

            return { volumeRatio: volumePCRatio, oiRatio: oiPCRatio };

        } catch (error) {
            console.error('Error calculating P/C ratios:', error);
            document.getElementById('calculationSteps').innerHTML = `<div style="color: red;">Error calculating P/C ratios: ${error.message}</div>`;
            return { volumeRatio: 'Error', oiRatio: 'Error' };
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

        document.getElementById('volumePCRatio').textContent = ratios.volumeRatio;
        document.getElementById('oiPCRatio').textContent = ratios.oiRatio;

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

// Helper function to fetch options chain data
function fetchOptionsChain(symbol, date) {
      return fetch(`/api/get_options_data?symbol=${symbol}&date=${date}`)
        .then(response => response.json())
        .then(data => {
          if (data.error) {
            throw new Error(data.error);
          }

          // Display the data source information
          displayDataDebugInfo(data);

          // Display the options chain data
          displayOptionsChainData(data);

          // Display P/C ratios
          displayPCRatios(data);

          return data;
        });
    }

    function displayDataDebugInfo(data) {
      const container = document.getElementById('dataDebugContainer');
      const content = document.getElementById('dataDebugContent');

      if (data.metadata) {
        const metadata = data.metadata;
        content.innerHTML = `
          <div class="debug-info">
            <p><strong>Data Source:</strong> ${metadata.dataSource}</p>
            <p><strong>Market Phase:</strong> ${metadata.marketPhase}</p>
            <p><strong>Symbol:</strong> ${data.symbol}</p>
            <p><strong>Expiration:</strong> ${data.date}</p>
            <p><strong>Last Updated:</strong> ${new Date().toLocaleString()}</p>
          </div>
        `;
        container.style.display = 'block';
      }
    }

    function displayOptionsChainData(data) {
      const container = document.getElementById('optionsChainContainer');
      const content = document.getElementById('optionsChainContent');

      const calls = data.calls || [];
      const puts = data.puts || [];

      let html = `
        <div class="chain-summary">
          <p><strong>Total Contracts:</strong> ${calls.length} calls, ${puts.length} puts</p>
        </div>
        <div class="chain-tables">
          <div class="calls-table">
            <h4>Calls (${calls.length})</h4>
            <table>
              <thead>
                <tr>
                  <th>Strike</th>
                  <th>Last</th>
                  <th>Volume</th>
                  <th>OI</th>
                </tr>
              </thead>
              <tbody>
      `;

      // Show first 10 calls
      calls.slice(0, 10).forEach(call => {
        html += `
          <tr>
            <td>$${call.strike}</td>
            <td>$${call.lastPrice}</td>
            <td>${call.volume.toLocaleString()}</td>
            <td>${call.openInterest.toLocaleString()}</td>
          </tr>
        `;
      });

      if (calls.length > 10) {
        html += `<tr><td colspan="4">... and ${calls.length - 10} more</td></tr>`;
      }

      html += `
              </tbody>
            </table>
          </div>
          <div class="puts-table">
            <h4>Puts (${puts.length})</h4>
            <table>
              <thead>
                <tr>
                  <th>Strike</th>
                  <th>Last</th>
                  <th>Volume</th>
                  <th>OI</th>
                </tr>
              </thead>
              <tbody>
      `;

      // Show first 10 puts
      puts.slice(0, 10).forEach(put => {
        html += `
          <tr>
            <td>$${put.strike}</td>
            <td>$${put.lastPrice}</td>
            <td>${put.volume.toLocaleString()}</td>
            <td>${put.openInterest.toLocaleString()}</td>
          </tr>
        `;
      });

      if (puts.length > 10) {
        html += `<tr><td colspan="4">... and ${puts.length - 10} more</td></tr>`;
      }

      html += `
              </tbody>
            </table>
          </div>
        </div>
      `;

      content.innerHTML = html;
      container.style.display = 'block';
    }

    function displayPCRatios(data) {
      const container = document.getElementById('pcRatiosContainer');
      const content = document.getElementById('pcRatiosContent');

      if (data.metadata) {
        const meta = data.metadata;
        content.innerHTML = `
          <div class="pc-ratios">
            <div class="ratio-item">
              <h4>Volume P/C Ratio</h4>
              <p class="ratio-value">${meta.volumePCRatio || 'N/A'}</p>
              <p class="ratio-detail">Put Volume: ${meta.totalPutVolume?.toLocaleString() || 0}</p>
              <p class="ratio-detail">Call Volume: ${meta.totalCallVolume?.toLocaleString() || 0}</p>
            </div>
            <div class="ratio-item">
              <h4>Open Interest P/C Ratio</h4>
              <p class="ratio-value">${meta.oiPCRatio || 'N/A'}</p>
              <p class="ratio-detail">Put OI: ${meta.totalPutOI?.toLocaleString() || 0}</p>
              <p class="ratio-detail">Call OI: ${meta.totalCallOI?.toLocaleString() || 0}</p>
            </div>
          </div>
        `;
        container.style.display = 'block';
      }
    }


// Initialize the calculator when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new OptionsCalculator();
});