const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
const month = document.body.dataset.month;

async function getInsight(kind, btn) {
  const box = document.getElementById('insight-box');
  btn.disabled = true; const old = btn.textContent; btn.textContent = 'Thinking…';
  try {
    const r = await fetch(`/api/insights?month=${month}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
      body: JSON.stringify({kind})});
    const d = await r.json();
    box.innerHTML = `<span class="tag">${d.source === 'ai' ? 'Gemini AI' : 'Rule-based'} · ${kind}</span><div class="pre"></div>`;
    box.querySelector('.pre').textContent = d.text;
  } catch (e) { box.textContent = 'Could not fetch insight.'; }
  btn.disabled = false; btn.textContent = old;
}

async function drawCharts() {
  if (!document.getElementById('catChart')) return;
  const d = await (await fetch(`/api/dashboard-data?month=${month}`)).json();
  const cats = d.summary.categories.filter(c => c.spent > 0 || c.limit);
  new Chart(catChart, {type: 'doughnut',
    data: {labels: cats.map(c => c.name), datasets: [{data: cats.map(c => c.spent)}]},
    options: {plugins: {legend: {position: 'bottom'}}}});
  new Chart(budgetChart, {type: 'bar',
    data: {labels: cats.map(c => c.name), datasets: [
      {label: 'Spent', data: cats.map(c => c.spent), backgroundColor: '#2f6fed'},
      {label: 'Limit', data: cats.map(c => c.limit || 0), backgroundColor: '#b8c4de'}]}});
  new Chart(trendChart, {type: 'line',
    data: {labels: d.trend.map(t => t.label), datasets: [
      {label: 'Income', data: d.trend.map(t => t.income), borderColor: '#1a9e5c'},
      {label: 'Expenses', data: d.trend.map(t => t.expenses), borderColor: '#d64545'},
      {label: 'Savings', data: d.trend.map(t => t.savings), borderColor: '#2f6fed'}]}});
}
window.addEventListener('DOMContentLoaded', drawCharts);
