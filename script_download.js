const elements = {
  navLinks: Array.from(document.querySelectorAll('.nav-link')),
  dateButtons: Array.from(document.querySelectorAll('.date-button')),
  dashboardCards: Array.from(document.querySelectorAll('.kpi-card')),
  caseRows: Array.from(document.querySelectorAll('.case-row')),
  chart: document.querySelector('.svg-chart')
};

// Simple UI polish interactions
for (const link of elements.navLinks) {
  link.addEventListener('click', (event) => {
    event.preventDefault();
    elements.navLinks.forEach(item => item.classList.toggle('active', item === link));
  });
}

for (const button of elements.dateButtons) {
  button.addEventListener('click', () => {
    elements.dateButtons.forEach(item => item.classList.toggle('active', item === button));
  });
}

for (const card of elements.dashboardCards) {
  card.addEventListener('mousemove', () => {
    card.style.transform = 'translateY(-4px)';
  });

  card.addEventListener('mouseleave', () => {
    card.style.transform = 'translateY(0)';
  });
}

for (const row of elements.caseRows) {
  row.addEventListener('click', () => {
    elements.caseRows.forEach(item => item.style.borderLeft = 'none');
    row.style.borderLeft = '4px solid var(--primary)';
  });
}

// Keyboard accessibility animation for chart title area: pulse lines
if (elements.chart) {
  elements.chart.animate([
    { transform: 'scaleY(1)', opacity: 1 },
    { transform: 'scaleY(1.015)', opacity: 0.98 },
    { transform: 'scaleY(1)', opacity: 1 }
  ], { duration: 900, iterations: 1, easing: 'ease-out' });
}
