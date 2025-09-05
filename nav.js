// Navigation functionality for selling-options.com
// This file provides all JavaScript functionality for the navigation bar

// Navigation stock quote functionality
async function getNavQuote() {
  const symbol = document.getElementById('navQuoteSymbol').value.trim().toUpperCase();
  const resultDiv = document.getElementById('navQuoteResult');
  
  if (!symbol) {
    resultDiv.innerHTML = '<div class="nav-quote-error">Enter symbol</div>';
    setTimeout(() => resultDiv.innerHTML = '', 3000);
    return;
  }
  
  resultDiv.innerHTML = '<div class="nav-quote-loading">Loading...</div>';
  
  try {
    const response = await fetch(`/api/quote?symbol=${symbol}`);
    const data = await response.json();
    
    if (data.error) {
      resultDiv.innerHTML = `<div class="nav-quote-error">Not found</div>`;
    } else {
      resultDiv.innerHTML = `
        <div class="nav-quote-success">
          ${data.symbol}: $${data.price}
        </div>
      `;
    }
    
    // Clear result after 5 seconds
    setTimeout(() => resultDiv.innerHTML = '', 5000);
  } catch (error) {
    resultDiv.innerHTML = '<div class="nav-quote-error">Error</div>';
    setTimeout(() => resultDiv.innerHTML = '', 3000);
  }
}

// Allow Enter key for nav quote search
document.addEventListener('DOMContentLoaded', function() {
  const navQuoteInput = document.getElementById('navQuoteSymbol');
  if (navQuoteInput) {
    navQuoteInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') {
        getNavQuote();
      }
    });
  }
});