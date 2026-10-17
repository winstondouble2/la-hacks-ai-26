(() => {
  const runId = document.body.dataset.runId;
  // A browser reload is the presenter's next-case shortcut. Normal links and
  // form submissions carry run_id and never advance the mutation.
  const navigation = performance.getEntriesByType('navigation')[0];
  if (document.body.dataset.demoMode === 'true' && navigation && navigation.type === 'reload') {
    document.documentElement.classList.add('reload-switching');
    const form = document.createElement('form');
    form.method = 'post';
    form.action = '/demo/advance';
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = 'run_id'; input.value = runId;
    form.append(input); document.body.append(form); form.submit();
    return;
  }
  document.querySelectorAll('[data-remove-item]').forEach(button => {
    button.addEventListener('click', () => {
      button.form.elements.quantity.value = '0';
      button.form.requestSubmit();
    });
  });
  const panel = document.querySelector('.diagnostics');
  let busy = false;
  async function refreshUsage() {
    if (busy || !panel.open || document.hidden) return;
    busy = true;
    try {
      const response = await fetch('/__telemetry?' + new URLSearchParams({ run_id: runId }), { cache: 'no-store' });
      if (!response.ok) throw new Error('Usage unavailable');
      const report = await response.json();
      const available = report.status === 'reported';
      panel.querySelector('[data-usage-status]').textContent = available ? 'Reported usage for this run' : 'Awaiting runtime data';
      panel.querySelectorAll('[data-metric]').forEach(element => {
        element.textContent = available ? report.totals[element.dataset.metric].toLocaleString() : '—';
      });
    } catch (error) {
      panel.querySelector('[data-usage-status]').textContent = 'Usage is temporarily unavailable';
    } finally { busy = false; }
  }
  panel.addEventListener('toggle', refreshUsage);
  window.setInterval(refreshUsage, 2000);
  const popup = document.querySelector('[role="dialog"]');
  if (popup) {
    const close = popup.querySelector('button');
    close.focus();
    document.querySelectorAll('header,main,footer,.demo-dock').forEach(el => { el.inert = true; });
    popup.addEventListener('keydown', event => {
      if (event.key === 'Escape') close.click();
      if (event.key === 'Tab') { event.preventDefault(); close.focus(); }
    });
  }
})();
