// QiBits Frontend Controller
document.addEventListener('DOMContentLoaded', () => {
  // Global State
  let activeTariffs = [];
  let activeEVs = [];
  let chartTariffsInstance = null;
  let chartFleetInstance = null;
  let chartClassicalHourlyInstance = null;
  let chartQuantumProbInstance = null;

  // DOM Elements
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');
  const globalAlert = document.getElementById('global-alert');
  const systemStatus = document.getElementById('system-status');
  const systemStatusText = document.getElementById('system-status-text');

  // Helper: Show Alert
  function showAlert(msg, type = 'info', timeout = 5000) {
    globalAlert.className = `alert alert-${type}`;
    globalAlert.textContent = msg;
    globalAlert.style.display = 'block';
    if (timeout > 0) {
      setTimeout(() => {
        globalAlert.style.display = 'none';
      }, timeout);
    }
  }

  // Safe numeric formatters
  function toCurrency(val, fallback = 0.0) {
    if (val === undefined || val === null) return Number(fallback).toFixed(2);
    const n = Number(val);
    return isNaN(n) ? Number(fallback).toFixed(2) : n.toFixed(2);
  }

  function toFloat(val, digits = 4, fallback = 0.0) {
    if (val === undefined || val === null) return Number(fallback).toFixed(digits);
    const n = Number(val);
    return isNaN(n) ? Number(fallback).toFixed(digits) : n.toFixed(digits);
  }

  // Tab Switching
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const target = document.getElementById(btn.getAttribute('data-tab'));
      if (target) target.classList.add('active');
    });
  });

  // Check Health & Initial Load
  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        systemStatus.className = 'status-badge';
        systemStatusText.textContent = `Backend Ready • Aer Simulator: ${data.aer_simulator_available ? 'Active' : 'Fallback'}`;
        await refreshDatasets();
      } else {
        systemStatus.className = 'status-badge badge-red';
        systemStatusText.textContent = 'Backend Error';
      }
    } catch (err) {
      systemStatus.className = 'status-badge badge-red';
      systemStatusText.textContent = 'Backend Offline';
    }
  }

  // Refresh Active Datasets from Backend
  async function refreshDatasets() {
    try {
      const [tRes, eRes] = await Promise.all([
        fetch('/api/data/tariffs'),
        fetch('/api/data/ev-sessions')
      ]);

      if (tRes.ok) {
        activeTariffs = await tRes.json();
        renderTariffTable(activeTariffs);
      }
      if (eRes.ok) {
        activeEVs = await eRes.json();
        renderEVTable(activeEVs);
        populateQuantumEVSelector(activeEVs);
      }
    } catch (e) {
      console.error("Error refreshing datasets:", e);
    }
  }

  // Render Tariff Table
  function renderTariffTable(tariffs) {
    const badge = document.getElementById('tariff-count-badge');
    badge.textContent = `${tariffs.length} records`;
    const tbody = document.getElementById('tbody-tariffs');
    if (!tariffs.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--text-muted);">No records</td></tr>';
      return;
    }
    // Show first 24 records (one full day) for concise preview
    const preview = tariffs.slice(0, 24);
    tbody.innerHTML = preview.map(t => `
      <tr>
        <td><span class="badge badge-blue">${t.price_profile}</span></td>
        <td>Slot ${t.slot}</td>
        <td>${t.start_time} - ${t.end_time}</td>
        <td style="font-weight:600; color:var(--accent-cyan);">₹${toCurrency(t.price_inr_per_kwh)}</td>
      </tr>
    `).join('');
  }

  // Render EV Fleet Table
  function renderEVTable(evs) {
    const badge = document.getElementById('ev-count-badge');
    badge.textContent = `${evs.length} vehicles`;
    const tbody = document.getElementById('tbody-evs');
    if (!evs.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color: var(--text-muted);">No EV sessions loaded</td></tr>';
      return;
    }
    tbody.innerHTML = evs.map(e => `
      <tr>
        <td style="font-weight:600;">${e.ev_id}</td>
        <td><span class="badge badge-purple">${e.charger_id}</span></td>
        <td>[${e.arrival_slot} ➔ ${e.departure_slot}]</td>
        <td>${e.battery_capacity_kwh} kWh</td>
        <td>${e.initial_soc_percent}% ➔ ${e.target_soc_percent}%</td>
        <td>${e.maximum_charging_power_kw} kW</td>
        <td>${e.required_energy_kwh} kWh</td>
        <td>
          <button class="btn btn-danger btn-sm" style="padding: 0.2rem 0.5rem; font-size:0.75rem;" onclick="deleteEV('${e.ev_id}')">
            Delete
          </button>
        </td>
      </tr>
    `).join('');
  }

  // Window delete function
  window.deleteEV = async function(evId) {
    if (!confirm(`Remove vehicle ${evId} from dataset?`)) return;
    try {
      const res = await fetch(`/api/ev-sessions/${encodeURIComponent(evId)}`, { method: 'DELETE' });
      if (res.ok) {
        showAlert(`EV ${evId} removed.`, 'warning');
        await refreshDatasets();
      } else {
        const err = await res.json();
        showAlert(err.detail || 'Failed to delete EV', 'danger');
      }
    } catch (e) {
      showAlert(e.message, 'danger');
    }
  };

  // Populate EV Selector Checkboxes for Quantum tab
  function populateQuantumEVSelector(evs) {
    const container = document.getElementById('quantum-ev-selector');
    if (!evs.length) {
      container.innerHTML = '<span style="color:var(--text-muted); font-size:0.8rem;">No EVs loaded</span>';
      return;
    }
    container.innerHTML = evs.slice(0, 8).map((e, idx) => `
      <label style="display:inline-flex; align-items:center; gap:0.25rem; font-size:0.8rem; background:var(--bg-card); padding:0.25rem 0.5rem; border-radius:4px; border:1px solid var(--border-color); cursor:pointer;">
        <input type="checkbox" name="q-ev-cb" value="${e.ev_id}" ${idx < 2 ? 'checked' : ''} />
        ${e.ev_id} (${e.charger_id})
      </label>
    `).join('');
  }

  // Button: Load Built-in Datasets
  document.getElementById('btn-load-sample').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/presets/load-sample', { method: 'POST' });
      const data = await res.json();
      showAlert(`Loaded ${data.tariffs_count} tariffs and ${data.evs_count} EV sessions.`, 'success');
      await refreshDatasets();
    } catch (e) {
      showAlert(`Failed to load preset data: ${e.message}`, 'danger');
    }
  });

  // Button: Upload Tariff CSV
  document.getElementById('btn-upload-tariff').addEventListener('click', async () => {
    const fileInput = document.getElementById('input-tariff-file');
    if (!fileInput.files.length) {
      showAlert('Please select a Tariff CSV file first.', 'warning');
      return;
    }
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
      const res = await fetch('/api/upload/tariffs', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        showAlert(data.message, 'success');
        await refreshDatasets();
      } else {
        showAlert(data.detail || 'Upload failed', 'danger');
      }
    } catch (e) {
      showAlert(e.message, 'danger');
    }
  });

  // Button: Upload EV Fleet CSV
  document.getElementById('btn-upload-ev').addEventListener('click', async () => {
    const fileInput = document.getElementById('input-ev-file');
    if (!fileInput.files.length) {
      showAlert('Please select an EV Sessions CSV file first.', 'warning');
      return;
    }
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
      const res = await fetch('/api/upload/ev-sessions', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        showAlert(data.message, 'success');
        await refreshDatasets();
      } else {
        showAlert(data.detail || 'Upload failed', 'danger');
      }
    } catch (e) {
      showAlert(e.message, 'danger');
    }
  });

  // Form: Manual EV Entry
  document.getElementById('form-ev-manual').addEventListener('submit', async (e) => {
    e.preventDefault();
    const evData = {
      ev_id: document.getElementById('manual-ev-id').value.trim(),
      charger_id: document.getElementById('manual-charger-id').value.trim(),
      arrival_slot: parseInt(document.getElementById('manual-arrival-slot').value, 10),
      departure_slot: parseInt(document.getElementById('manual-departure-slot').value, 10),
      battery_capacity_kwh: parseFloat(document.getElementById('manual-battery-kwh').value),
      initial_soc_percent: parseFloat(document.getElementById('manual-init-soc').value),
      target_soc_percent: parseFloat(document.getElementById('manual-target-soc').value),
      maximum_charging_power_kw: parseFloat(document.getElementById('manual-max-power').value),
      charging_efficiency: parseFloat(document.getElementById('manual-efficiency').value),
      required_energy_kwh: parseFloat(document.getElementById('manual-req-energy').value)
    };

    try {
      const res = await fetch('/api/ev-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(evData)
      });
      const data = await res.json();
      if (res.ok) {
        showAlert(data.message, 'success');
        await refreshDatasets();
      } else {
        showAlert(data.detail || 'Failed to save EV session', 'danger');
      }
    } catch (err) {
      showAlert(err.message, 'danger');
    }
  });

  // Button: Validate Datasets
  document.getElementById('btn-validate').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/validate', { method: 'POST' });
      const data = await res.json();

      const outBox = document.getElementById('validation-output');
      const valAlert = document.getElementById('validation-alert');
      const errCount = document.getElementById('val-error-count');
      const warnCount = document.getElementById('val-warn-count');
      const tbodyErr = document.getElementById('tbody-val-errors');
      const tbodyWarn = document.getElementById('tbody-val-warnings');

      outBox.style.display = 'block';
      errCount.textContent = data.errors.length;
      warnCount.textContent = data.warnings.length;

      if (data.valid) {
        valAlert.className = 'alert alert-success';
        valAlert.textContent = `✓ Datasets passed all validation checks! (${data.total_tariff_records} tariff slots, ${data.total_ev_records} EV sessions, profiles: ${data.tariff_profiles_found.join(', ')})`;
      } else {
        valAlert.className = 'alert alert-danger';
        valAlert.textContent = `✗ Schema validation failed with ${data.errors.length} errors. Please fix before running optimization.`;
      }

      tbodyErr.innerHTML = data.errors.length
        ? data.errors.map(e => `<tr><td>Row ${e.row || '-'}</td><td><code>${e.field || '-'}</code></td><td>${e.message}</td></tr>`).join('')
        : '<tr><td colspan="3" style="color:var(--text-muted); text-align:center;">No errors detected</td></tr>';

      tbodyWarn.innerHTML = data.warnings.length
        ? data.warnings.map(w => `<tr><td>Row ${w.row || '-'}</td><td><code>${w.field || '-'}</code></td><td>${w.message}</td></tr>`).join('')
        : '<tr><td colspan="3" style="color:var(--text-muted); text-align:center;">No warnings</td></tr>';

    } catch (e) {
      showAlert(e.message, 'danger');
    }
  });

  // Button: Run Telemetry / Analysis
  document.getElementById('btn-run-analysis').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/analyze', { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Analysis failed');
      }
      const data = await res.json();

      // Update KPI cards
      document.getElementById('metric-total-energy').textContent = `${data.fleet.total_required_energy_kwh} kWh`;
      document.getElementById('metric-total-evs').textContent = `${data.fleet.total_evs}`;
      document.getElementById('metric-peak-demand').textContent = `${data.theoretical_peak_demand_kw} kW`;
      document.getElementById('metric-avg-stay').textContent = `${data.fleet.avg_stay_duration_slots} hrs`;

      // Feasibility status badge
      const feasBadge = document.getElementById('analysis-feasibility-badge');
      feasBadge.textContent = data.feasibility_status;
      feasBadge.className = data.feasibility_status.includes('OPTIMAL') ? 'badge badge-green' : 'badge badge-amber';

      const feasNotes = document.getElementById('analysis-feasibility-notes');
      feasNotes.innerHTML = data.feasibility_notes.length
        ? data.feasibility_notes.map(n => `<div>• ${n}</div>`).join('')
        : '<div>No charger contention detected. Problem is well-conditioned for optimization.</div>';

      // Render Charts
      renderAnalysisCharts(data);
      showAlert('Telemetry and charts successfully computed.', 'success');
    } catch (e) {
      showAlert(e.message, 'danger');
    }
  });

  function renderAnalysisCharts(data) {
    // 1. Tariffs Chart
    const ctxTariff = document.getElementById('chart-tariffs').getContext('2d');
    if (chartTariffsInstance) chartTariffsInstance.destroy();

    const profiles = {};
    activeTariffs.forEach(t => {
      profiles[t.price_profile] = profiles[t.price_profile] || [];
      profiles[t.price_profile].push({ x: t.slot, y: t.price_inr_per_kwh });
    });

    const colors = {
      TimeOfUse: '#06b6d4',
      Peak_OffPeak: '#f59e0b',
      SolarSurplus: '#10b981',
      Flat: '#8b5cf6'
    };

    const datasets = Object.keys(profiles).map(name => ({
      label: name,
      data: profiles[name].sort((a,b) => a.x - b.x).map(p => p.y),
      borderColor: colors[name] || '#3b82f6',
      backgroundColor: colors[name] || '#3b82f6',
      tension: 0.2,
      borderWidth: 2,
      pointRadius: 2
    }));

    chartTariffsInstance = new Chart(ctxTariff, {
      type: 'line',
      data: {
        labels: Array.from({length: 24}, (_, i) => `S${i}`),
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: '₹ / kWh', color: '#9ca3af' } },
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Hourly Slot (0-23)', color: '#9ca3af' } }
        },
        plugins: { legend: { labels: { color: '#f9fafb' } } }
      }
    });

    // 2. Fleet Arrival vs Departure Chart
    const ctxFleet = document.getElementById('chart-fleet-distribution').getContext('2d');
    if (chartFleetInstance) chartFleetInstance.destroy();

    const arrData = Array.from({length: 24}, (_, i) => data.fleet.arrival_distribution[i] || 0);
    const depData = Array.from({length: 24}, (_, i) => data.fleet.departure_distribution[i] || 0);

    chartFleetInstance = new Chart(ctxFleet, {
      type: 'bar',
      data: {
        labels: Array.from({length: 24}, (_, i) => `S${i}`),
        datasets: [
          { label: 'Arrivals', data: arrData, backgroundColor: '#3b82f6' },
          { label: 'Departures', data: depData, backgroundColor: '#8b5cf6' }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Vehicle Count', color: '#9ca3af' } },
          x: { grid: { color: 'rgba(255,255,255,0.05)' } }
        },
        plugins: { legend: { labels: { color: '#f9fafb' } } }
      }
    });
  }

  // Button: Execute Classical CP-SAT Optimizer
  document.getElementById('btn-run-classical').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-classical');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Solving with OR-Tools CP-SAT...';

    const reqData = {
      price_profile: document.getElementById('classical-profile').value,
      grid_power_limit_kw: parseFloat(document.getElementById('classical-grid-limit').value),
      peak_penalty_weight: parseFloat(document.getElementById('classical-peak-penalty').value),
      time_limit_seconds: parseFloat(document.getElementById('classical-timeout').value)
    };

    try {
      const res = await fetch('/api/optimize/classical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqData)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Classical solver failed');

      // Display results
      document.getElementById('classical-results').style.display = 'block';
      document.getElementById('res-c-status').textContent = data.status;
      document.getElementById('res-c-time').textContent = `Solve Duration: ${toFloat(data.execution_time_seconds, 4)}s`;
      document.getElementById('res-c-cost').textContent = `₹${toCurrency(data.objective_cost_inr)}`;
      document.getElementById('res-c-peak').textContent = `${data.grid_peak_power_kw} kW`;
      document.getElementById('res-c-headroom').textContent = `Limit: ${data.grid_power_limit_kw} kW (${toFloat(data.grid_power_limit_kw - data.grid_peak_power_kw, 1)} kW headroom)`;
      document.getElementById('res-c-fulfillment').textContent = `${data.overall_fulfillment_percent}%`;
      document.getElementById('res-c-energy').textContent = `${data.total_energy_delivered_kwh} / ${data.total_energy_required_kwh} kWh delivered`;

      // Render Hourly Chart
      renderClassicalHourlyChart(data.hourly_metrics, data.grid_power_limit_kw);

      // Render Schedule Matrix Table
      renderClassicalSchedules(data.ev_schedules);

      showAlert(`CP-SAT Solved to ${data.status} in ${data.execution_time_seconds}s!`, 'success');
    } catch (e) {
      showAlert(e.message, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>▶</span> Execute Classical Optimization (CP-SAT)';
    }
  });

  function renderClassicalHourlyChart(metrics, gridLimit) {
    const ctx = document.getElementById('chart-classical-hourly').getContext('2d');
    if (chartClassicalHourlyInstance) chartClassicalHourlyInstance.destroy();

    const powers = metrics.map(m => m.total_power_kw);
    const limits = metrics.map(() => gridLimit);
    const costs = metrics.map(m => m.slot_cost_inr);

    chartClassicalHourlyInstance = new Chart(ctx, {
      data: {
        labels: metrics.map(m => `${m.slot}h (${m.start_time})`),
        datasets: [
          {
            type: 'bar',
            label: 'Total Power (kW)',
            data: powers,
            backgroundColor: '#06b6d4',
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Substation Limit (kW)',
            data: limits,
            borderColor: '#ef4444',
            borderDash: [5, 5],
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: 'y'
          },
          {
            type: 'line',
            label: 'Slot Cost (₹)',
            data: costs,
            borderColor: '#f59e0b',
            borderWidth: 2,
            pointRadius: 2,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            position: 'left',
            grid: { color: 'rgba(255,255,255,0.05)' },
            title: { display: true, text: 'Power (kW)', color: '#06b6d4' }
          },
          y1: {
            position: 'right',
            grid: { drawOnChartArea: false },
            title: { display: true, text: 'Slot Cost (₹)', color: '#f59e0b' }
          },
          x: { grid: { color: 'rgba(255,255,255,0.05)' } }
        },
        plugins: { legend: { labels: { color: '#f9fafb' } } }
      }
    });
  }

  function renderClassicalSchedules(schedules) {
    const tbody = document.getElementById('tbody-classical-schedules');
    tbody.innerHTML = schedules.map(s => {
      // Build 24 slot cells
      let cells = '';
      for (let t = 0; t < 24; t++) {
        const p = s.hourly_power_kw[t];
        if (p > 0.01) {
          cells += `<span class="gantt-cell cell-charge" title="Slot ${t}: ${p} kW">${Math.round(p)}</span>`;
        } else if (t >= s.arrival_slot && t < s.departure_slot) {
          cells += `<span class="gantt-cell cell-window" title="Slot ${t}: Window Idle">-</span>`;
        } else {
          cells += `<span class="gantt-cell cell-idle" title="Slot ${t}: Outside">.</span>`;
        }
      }

      return `
        <tr>
          <td style="font-weight:600;">${s.ev_id}</td>
          <td><span class="badge badge-purple">${s.charger_id}</span></td>
          <td>[${s.arrival_slot} - ${s.departure_slot}]</td>
          <td>${s.initial_soc_percent}%</td>
          <td style="font-weight:600; color:var(--accent-green);">${s.final_soc_percent}%</td>
          <td>${s.delivered_energy_kwh} / ${s.required_energy_kwh} kWh</td>
          <td><span class="badge ${s.energy_fulfillment_percent >= 99 ? 'badge-green' : 'badge-amber'}">${s.energy_fulfillment_percent}%</span></td>
          <td style="font-weight:600; color:var(--accent-cyan);">₹${toCurrency(s.charging_cost_inr)}</td>
          <td><div style="display:flex;">${cells}</div></td>
        </tr>
      `;
    }).join('');
  }

  // Button: Execute Genuine Qiskit QAOA
  document.getElementById('btn-run-quantum').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-quantum');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Running Genuine Qiskit QAOA Circuit...';

    const errBox = document.getElementById('quantum-error-box');
    const errTrace = document.getElementById('quantum-error-trace');
    const resultsBox = document.getElementById('quantum-results');
    errBox.style.display = 'none';
    resultsBox.style.display = 'none';

    // Collect selected EVs
    const selectedEvs = Array.from(document.querySelectorAll('input[name="q-ev-cb"]:checked')).map(cb => cb.value);

    const reqData = {
      ev_ids: selectedEvs.length ? selectedEvs : null,
      price_profile: document.getElementById('quantum-profile').value,
      qaoa_reps: parseInt(document.getElementById('quantum-p').value, 10),
      shots: parseInt(document.getElementById('quantum-shots').value, 10),
      max_iter: parseInt(document.getElementById('quantum-max-iter').value, 10),
      penalty_demand: parseFloat(document.getElementById('quantum-penalty-a').value),
      penalty_conflict: parseFloat(document.getElementById('quantum-penalty-b').value)
    };

    try {
      const res = await fetch('/api/optimize/quantum', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqData)
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        // Show genuine error, do NOT substitute fake results
        errBox.style.display = 'block';
        errTrace.textContent = data.error || data.detail || 'Unknown QAOA execution error';
        showAlert('Quantum optimization encountered a real error. See diagnostic output.', 'danger');
        return;
      }

      // Success
      resultsBox.style.display = 'block';
      document.getElementById('res-q-qubits').textContent = `${data.qubit_count || 0} Qubits`;
      const quboE = data.optimal_qubo_energy !== undefined ? data.optimal_qubo_energy : (data.top_states && data.top_states[0] ? data.top_states[0].qubo_energy : 0);
      document.getElementById('res-q-depth').textContent = `Depth: ${data.circuit_depth || 0} • QUBO Energy: ${toFloat(quboE, 2)}`;
      document.getElementById('res-q-time').textContent = `${toFloat(data.execution_time_seconds, 4)}s`;
      const econCost = data.optimal_economic_cost_inr !== undefined ? data.optimal_economic_cost_inr : (data.optimal_cost_inr !== undefined ? data.optimal_cost_inr : 0);
      document.getElementById('res-q-cost').textContent = `₹${toCurrency(econCost)}`;
      const varBits = data.optimal_variable_bitstring || data.optimal_bitstring || '--';
      const qisBits = data.optimal_qiskit_bitstring || varBits.split('').reverse().join('');
      document.getElementById('res-q-bitstring').textContent = `Vars: [${varBits}] • Qiskit: |${qisBits}⟩`;
      document.getElementById('res-q-feasible').textContent = data.is_feasible ? 'FEASIBLE' : 'INFEASIBLE';
      document.getElementById('res-q-feasible').style.color = data.is_feasible ? 'var(--accent-green)' : 'var(--accent-red)';
      document.getElementById('res-q-violations').textContent = `Violations: ${(data.constraint_violations || []).length}`;

      // Gate stats
      const gateStr = Object.entries(data.gate_counts || {}).map(([g, c]) => `<code>${g}: ${c}</code>`).join(' ');
      document.getElementById('quantum-gate-stats').innerHTML = `Circuit Operations: ${gateStr || 'N/A'}`;

      // Probability chart
      if (data.top_states) {
        renderQuantumProbabilities(data.top_states);
      }

      // Top states table
      const tbodyStates = document.getElementById('tbody-quantum-states');
      tbodyStates.innerHTML = (data.top_states || []).map(s => `
        <tr>
          <td><code style="color:var(--accent-purple); font-weight:bold;">${s.variable_bitstring || s.bitstring || ''}</code> <span style="font-size:0.7rem; color:var(--text-muted);">(|${s.qiskit_bitstring || ''}⟩)</span></td>
          <td>${toFloat((s.probability || 0) * 100, 1)}%</td>
          <td>${s.shots_count || 0}</td>
          <td style="color:var(--accent-cyan);">₹${toCurrency(s.economic_cost_inr !== undefined ? s.economic_cost_inr : s.qubo_energy)}</td>
          <td><span class="badge ${s.is_feasible ? 'badge-green' : 'badge-red'}">${s.is_feasible ? 'FEASIBLE' : 'VIOLATION'}</span></td>
        </tr>
      `).join('');

      // Decoded schedule table
      const tbodySched = document.getElementById('tbody-quantum-schedules');
      tbodySched.innerHTML = (data.schedules || []).map(sc => `
        <tr>
          <td style="font-weight:600;">${sc.ev_id}</td>
          <td><span class="badge badge-purple">${sc.charger_id}</span></td>
          <td>${sc.required_slots} slots</td>
          <td><code>[${(sc.scheduled_slots || []).join(', ')}]</code></td>
          <td>${sc.energy_delivered_kwh || 0} kWh</td>
          <td style="color:var(--accent-cyan); font-weight:600;">₹${toCurrency(sc.cost_inr)}</td>
          <td><span class="badge ${sc.is_demand_satisfied ? 'badge-green' : 'badge-amber'}">${sc.is_demand_satisfied ? 'Satisfied' : 'Deficit'}</span></td>
        </tr>
      `).join('');

      showAlert(`Genuine QAOA completed in ${toFloat(data.execution_time_seconds, 4)}s!`, 'success');
    } catch (e) {
      errBox.style.display = 'block';
      errTrace.textContent = `Client Rendering Exception:\n${e.message}\n\nStack:\n${e.stack || ''}`;
      showAlert(`Client Rendering Error: ${e.message}`, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>⚛</span> Execute Genuine QAOA Optimization';
    }
  });

  function renderQuantumProbabilities(states) {
    const ctx = document.getElementById('chart-quantum-probabilities').getContext('2d');
    if (chartQuantumProbInstance) chartQuantumProbInstance.destroy();

    const labels = states.map(s => `|${s.qiskit_bitstring || s.variable_bitstring || s.bitstring}⟩`);
    const probs = states.map(s => toFloat((s.probability || 0) * 100, 1));
    const bgColors = states.map(s => s.is_feasible ? '#8b5cf6' : '#ef4444');

    chartQuantumProbInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Measurement Probability (%)',
          data: probs,
          backgroundColor: bgColors
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: 'Probability (%)', color: '#8b5cf6' } },
          x: { grid: { color: 'rgba(255,255,255,0.05)' } }
        },
        plugins: { legend: { labels: { color: '#f9fafb' } } }
      }
    });
  }

  // Function to render benchmark results
  function renderBenchmarkResults(data) {
    if (!data) return;
    document.getElementById('benchmark-results').style.display = 'block';
    const alertEl = document.getElementById('benchmark-summary-alert');
    if (alertEl) {
      alertEl.textContent = data.summary || 'Benchmark execution completed successfully.';
    }

    // Input parameters summary (Task 1) - Defensive extraction
    const inp = data.benchmark_inputs || {};
    const candidateSlots = data.candidate_slots || inp.candidate_slots || [0, 1, 2];
    const tariffPrices = inp.tariff_prices_inr || data.tariffs_dict || {};
    const stationCap = (data.station_capacity_units !== undefined && data.station_capacity_units !== null)
      ? data.station_capacity_units
      : (inp.station_capacity_units !== undefined ? inp.station_capacity_units : 1);
    const unitEnergy = inp.unit_energy_mode !== undefined ? inp.unit_energy_mode : true;
    const evSpecs = Array.isArray(inp.ev_specifications) ? inp.ev_specifications : [];

    const capBadge = document.getElementById('bm-station-capacity-badge');
    if (capBadge) {
      capBadge.textContent = `Station Capacity: ${stationCap} simultaneous unit(s)`;
    }

    const summaryEl = document.getElementById('bm-inputs-summary');
    if (summaryEl) {
      const evSpecStr = evSpecs.length
        ? evSpecs.map(e => `<code>${e.ev_id}</code> (Arr: ${e.arrival_slot}, Dep: ${e.departure_slot}, Req: ${e.required_energy_kwh} kWh, Charger: ${e.charger_id})`).join(' • ')
        : (data.ev_ids ? data.ev_ids.map(id => `<code>${id}</code>`).join(' • ') : '--');

      summaryEl.innerHTML = `
        <div><strong>Candidate Slots:</strong> [${candidateSlots.join(', ')}] • <strong>Tariff Rates (₹/kWh):</strong> ${JSON.stringify(tariffPrices)} • <strong>Unit Energy Mode:</strong> ${unitEnergy ? 'Active (1.0 kWh/slot)' : 'Full Power (P_max × dt)'}</div>
        <div><strong>Participating Vehicles:</strong> ${evSpecStr}</div>
      `;
    }

    // Explicit Qubit-to-Variable Mapping Table (Task 3)
    const tbodyMap = document.getElementById('tbody-qubit-mappings');
    if (tbodyMap) {
      const qMappings = Array.isArray(data.qubit_mappings) ? data.qubit_mappings : [];
      if (qMappings.length > 0) {
        tbodyMap.innerHTML = qMappings.map(m => `
          <tr>
            <td><code>q${m.qubit_index}</code></td>
            <td style="font-weight:600;">${m.ev_id}</td>
            <td>Slot ${m.slot}</td>
            <td><span class="badge badge-purple">${m.charger_id}</span></td>
            <td>${toFloat(m.grid_energy_kwh, 2)} kWh</td>
            <td>₹${toCurrency(m.tariff_inr_per_kwh)}</td>
            <td style="color:var(--accent-cyan); font-weight:600;">₹${toCurrency(m.cost_coefficient_inr)}</td>
          </tr>
        `).join('');
      } else {
        tbodyMap.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted);">No decision variables registered for this benchmark.</td></tr>`;
      }
    }

    // Classical values
    const c = data.classical_cpsat || {};
    const cStatusEl = document.getElementById('bm-c-status');
    if (cStatusEl) cStatusEl.textContent = c.status || 'OPTIMAL';
    const cCostEl = document.getElementById('bm-c-cost');
    if (cCostEl) cCostEl.textContent = `₹${toCurrency(c.economic_cost_inr !== undefined ? c.economic_cost_inr : (c.optimal_cost_inr !== undefined ? c.optimal_cost_inr : 0))}`;
    const cTimeEl = document.getElementById('bm-c-time');
    if (cTimeEl) cTimeEl.textContent = `Runtime: ${toFloat(c.solve_time_seconds, 4)}s`;
    const cVarBitEl = document.getElementById('bm-c-var-bitstring');
    if (cVarBitEl) cVarBitEl.textContent = c.variable_bitstring || c.optimal_bitstring || '--';
    const cQisBitEl = document.getElementById('bm-c-qiskit-bitstring');
    if (cQisBitEl) cQisBitEl.textContent = `|${c.qiskit_bitstring || ''}⟩`;
    const cFeasEl = document.getElementById('bm-c-feas-badge');
    if (cFeasEl) {
      cFeasEl.className = c.is_feasible ? 'badge badge-green' : 'badge badge-red';
      cFeasEl.textContent = c.is_feasible ? 'FEASIBLE' : 'VIOLATION';
    }

    // Quantum values
    const q = data.quantum_qaoa || {};
    const qStatusEl = document.getElementById('bm-q-status');
    if (qStatusEl) qStatusEl.textContent = q.status || 'FEASIBLE';
    const qCostEl = document.getElementById('bm-q-cost');
    if (qCostEl) qCostEl.textContent = `₹${toCurrency(q.economic_cost_inr !== undefined ? q.economic_cost_inr : (q.optimal_cost_inr !== undefined ? q.optimal_cost_inr : 0))}`;
    const qQubo = q.qubo_objective_value !== undefined ? q.qubo_objective_value : (q.qubo_energy || 0);
    const qQuboEl = document.getElementById('bm-q-qubo');
    if (qQuboEl) qQuboEl.textContent = `QUBO Penalized Energy: ${toFloat(qQubo, 2)} • Runtime: ${toFloat(q.execution_time_seconds, 4)}s`;
    const qVarBitEl = document.getElementById('bm-q-var-bitstring');
    if (qVarBitEl) qVarBitEl.textContent = q.variable_bitstring || q.optimal_bitstring || '--';
    const qQisBitEl = document.getElementById('bm-q-qiskit-bitstring');
    if (qQisBitEl) qQisBitEl.textContent = `|${q.qiskit_bitstring || ''}⟩`;
    const qFeasEl = document.getElementById('bm-q-feas-badge');
    if (qFeasEl) {
      qFeasEl.className = q.is_feasible ? 'badge badge-green' : 'badge badge-red';
      qFeasEl.textContent = q.is_feasible ? 'FEASIBLE' : 'VIOLATION';
    }

    const violBox = document.getElementById('bm-q-violations');
    if (violBox) {
      if (q.constraint_violations && q.constraint_violations.length) {
        violBox.innerHTML = `<strong>Violations:</strong> ${q.constraint_violations.join('; ')}`;
      } else {
        violBox.innerHTML = '';
      }
    }

    // Direct comparison metrics (Task 5)
    const diffEl = document.getElementById('bm-diff-cost');
    if (diffEl) diffEl.textContent = `₹${toCurrency(data.cost_difference_inr !== undefined ? data.cost_difference_inr : 0)}`;
    const matchEl = document.getElementById('bm-match-badge');
    if (matchEl) {
      matchEl.textContent = data.exact_match ? '100% MATCH' : 'DIFFERENT BITS';
      matchEl.style.color = data.exact_match ? 'var(--accent-green)' : 'var(--accent-amber)';
    }
    const gapEl = document.getElementById('bm-gap-inr');
    if (gapEl) gapEl.textContent = `₹${toCurrency(data.qaoa_objective_gap_inr !== undefined ? data.qaoa_objective_gap_inr : 0)}`;
    const ratioEl = document.getElementById('bm-runtime-ratio');
    if (ratioEl) ratioEl.textContent = `${toFloat(data.runtime_speedup_ratio || data.runtime_ratio, 2)}x`;
  }

  // Button: Direct Side-by-Side Benchmark (Active Dataset)
  document.getElementById('btn-run-benchmark').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-benchmark');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Running Classical & Quantum Solvers on Identical Input...';

    const unitEnergyCb = document.getElementById('bm-unit-energy-mode');
    const unitEnergyMode = unitEnergyCb ? unitEnergyCb.checked : true;

    const reqData = {
      ev_ids: ["EV001", "EV003"],
      candidate_slots: [0, 1, 2],
      price_profile: "TimeOfUse",
      qaoa_reps: 1,
      shots: 2048,
      max_iter: 25,
      penalty_demand: 25.0,
      penalty_conflict: 30.0,
      station_capacity_units: 1,
      unit_energy_mode: unitEnergyMode
    };

    try {
      const res = await fetch('/api/optimize/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqData)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Benchmark failed');

      renderBenchmarkResults(data);
      showAlert('Side-by-side benchmark completed successfully!', 'success');
    } catch (e) {
      showAlert(e.message, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>⚡</span> Run Benchmark on Active Dataset';
    }
  });

  // Button: Task 6 Reproducible Reference Test
  document.getElementById('btn-run-reference-test').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-reference-test');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Executing Task 6 Reference Test ([8, 3, 6] ₹/kWh)...';

    try {
      const res = await fetch('/api/benchmark/reference-test?reps=1&shots=2048&max_iter=30', {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Reference test failed');

      renderBenchmarkResults(data);
      showAlert('Task 6 Reproducible Reference Test executed successfully!', 'success');
    } catch (e) {
      showAlert(e.message, 'danger');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🎯</span> Run Task 6 Reproducible Reference Test (Min ₹9.00)';
    }
  });

  // Start initialization
  checkHealth();
});
