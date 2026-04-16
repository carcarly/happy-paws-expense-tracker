/**
 * Vet Expense Tracker - Frontend Application
 */

// ==================== STATE ====================
let categories = [];
let currentReceipt = null;
let trendChart = null;
let categoryChart = null;
let darkMode = localStorage.getItem('darkMode') !== 'false'; // Default dark

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    initDarkMode();
    loadCategories();
    loadDashboard();
    setupNavigation();
    setupUpload();
    setupForms();
    setDefaultDates();
});

// ==================== DARK MODE ====================
function initDarkMode() {
    applyDarkMode();
    
    document.getElementById('dark-mode-toggle').addEventListener('click', (e) => {
        e.preventDefault();
        darkMode = !darkMode;
        localStorage.setItem('darkMode', darkMode);
        applyDarkMode();
    });
}

function applyDarkMode() {
    const toggle = document.getElementById('dark-mode-toggle');
    if (darkMode) {
        document.body.classList.remove('light-mode');
        toggle.innerHTML = '<i class="bi bi-moon-stars"></i><span>Dark Mode</span>';
    } else {
        document.body.classList.add('light-mode');
        toggle.innerHTML = '<i class="bi bi-sun"></i><span>Light Mode</span>';
    }
    
    // Update charts if they exist
    if (trendChart || categoryChart) {
        loadDashboard();
    }
}

function setDefaultDates() {
    const today = new Date().toISOString().split('T')[0];
    const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    document.getElementById('report-start').value = monthAgo;
    document.getElementById('report-end').value = today;
    document.getElementById('filter-start').value = monthAgo;
    document.getElementById('filter-end').value = today;
}

// ==================== NAVIGATION ====================
function setupNavigation() {
    document.querySelectorAll('[data-page]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            showPage(page);
        });
    });
}

function showPage(page) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    // Show selected page
    document.getElementById(`page-${page}`).classList.add('active');
    // Update nav
    document.querySelectorAll('.sidebar .nav-link').forEach(l => l.classList.remove('active'));
    document.querySelector(`.sidebar .nav-link[data-page="${page}"]`).classList.add('active');
    
    // Load page data
    if (page === 'dashboard') loadDashboard();
    if (page === 'expenses') loadExpenses();
    if (page === 'reports') generateReport();
}

// ==================== API CALLS ====================
async function api(endpoint, options = {}) {
    const response = await fetch(`/api/${endpoint}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options
    });
    return response.json();
}

async function loadCategories() {
    const data = await api('categories');
    categories = data.categories || [];
    
    // Populate all category dropdowns
    const selects = ['form-category', 'edit-category', 'filter-category'];
    selects.forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;
        
        const firstOption = id === 'filter-category' 
            ? '<option value="">All Categories</option>' 
            : '';
        select.innerHTML = firstOption + categories.map(c => 
            `<option value="${c.name}">${c.name}</option>`
        ).join('');
    });
    
    // Render settings page categories
    renderSettingsCategories();
}

function renderSettingsCategories() {
    const container = document.getElementById('settings-categories');
    if (!container) return;
    
    if (!categories.length) {
        container.innerHTML = '<p class="text-muted">No categories yet</p>';
        return;
    }
    
    container.innerHTML = categories.map(cat => {
        const keywords = (cat.keywords || []).join(', ');
        return `
            <div class="d-flex justify-content-between align-items-start py-3 border-bottom">
                <div class="flex-grow-1">
                    <div class="fw-medium">${escapeHtml(cat.name)}</div>
                    ${keywords ? `<small class="text-muted">Keywords: ${escapeHtml(keywords)}</small>` : '<small class="text-muted fst-italic">No keywords set</small>'}
                </div>
                <div class="d-flex gap-1">
                    <button class="btn btn-sm btn-outline-primary" onclick="editCategory(${cat.id})">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteCategory(${cat.id}, '${escapeHtml(cat.name)}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function showAddCategory() {
    document.getElementById('category-form').classList.remove('d-none');
    document.getElementById('category-form-title').textContent = 'Add Category';
    document.getElementById('cat-edit-id').value = '';
    document.getElementById('cat-edit-old-name').value = '';
    document.getElementById('cat-name').value = '';
    document.getElementById('cat-keywords').value = '';
}

function hideCategoryForm() {
    document.getElementById('category-form').classList.add('d-none');
}

function editCategory(id) {
    const cat = categories.find(c => c.id === id);
    if (!cat) return;
    
    document.getElementById('category-form').classList.remove('d-none');
    document.getElementById('category-form-title').textContent = 'Edit Category';
    document.getElementById('cat-edit-id').value = cat.id;
    document.getElementById('cat-edit-old-name').value = cat.name;
    document.getElementById('cat-name').value = cat.name;
    document.getElementById('cat-keywords').value = (cat.keywords || []).join(', ');
}

async function saveCategory() {
    const id = document.getElementById('cat-edit-id').value;
    const oldName = document.getElementById('cat-edit-old-name').value;
    const name = document.getElementById('cat-name').value.trim();
    const keywordsStr = document.getElementById('cat-keywords').value.trim();
    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];
    
    if (!name) {
        alert('Please enter a category name');
        return;
    }
    
    if (id) {
        // Update
        const result = await api(`categories/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ name, keywords, old_name: oldName })
        });
        if (result.success) {
            hideCategoryForm();
            loadCategories();
        } else {
            alert('Error: ' + (result.error || 'Failed to update'));
        }
    } else {
        // Create
        const result = await api('categories', {
            method: 'POST',
            body: JSON.stringify({ name, keywords })
        });
        if (result.success) {
            hideCategoryForm();
            loadCategories();
        } else {
            alert('Error: ' + (result.error || 'Failed to create'));
        }
    }
}

async function deleteCategory(id, name) {
    if (!confirm(`Delete "${name}"?\n\nExpenses in this category will move to "Other".`)) return;
    
    const result = await api(`categories/${id}`, { method: 'DELETE' });
    if (result.success) {
        loadCategories();
    }
}

// ==================== DASHBOARD ====================
async function loadDashboard() {
    const data = await api('dashboard');
    
    // Update stats
    document.getElementById('stat-today').textContent = formatCurrency(data.summary.today);
    document.getElementById('stat-month').textContent = formatCurrency(data.summary.this_month);
    document.getElementById('stat-change').textContent = 
        (data.summary.month_change_pct >= 0 ? '+' : '') + data.summary.month_change_pct.toFixed(1) + '%';
    document.getElementById('stat-count').textContent = data.summary.month_count;
    
    // Update change color
    const changeEl = document.getElementById('stat-change');
    changeEl.className = 'stat-value ' + (data.summary.month_change_pct > 0 ? 'text-danger' : 'text-success');
    
    // Render charts
    renderTrendChart(data.monthly_trend);
    renderCategoryChart(data.category_breakdown);
    
    // Render recent expenses
    renderRecentExpenses(data.recent_expenses);
    
    // Render top vendors
    renderTopVendors(data.top_vendors);
}

function renderTrendChart(trendData) {
    const ctx = document.getElementById('trendChart').getContext('2d');
    
    if (trendChart) trendChart.destroy();
    
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trendData.map(d => d.month),
            datasets: [{
                label: 'Monthly Spending',
                data: trendData.map(d => d.total),
                borderColor: '#7c3aed',
                backgroundColor: 'rgba(124, 58, 237, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => '$' + value.toLocaleString()
                    }
                }
            }
        }
    });
}

function renderCategoryChart(categoryData) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    
    if (categoryChart) categoryChart.destroy();
    
    const colors = [
        '#7c3aed', '#6d28d9', '#8b5cf6', '#a78bfa', '#c4b5fd',
        '#5b21b6', '#4c1d95', '#ddd6fe', '#a855f7', '#9333ea'
    ];
    
    categoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: categoryData.map(d => d.category),
            datasets: [{
                data: categoryData.map(d => d.total),
                backgroundColor: colors.slice(0, categoryData.length)
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            }
        }
    });
}

function renderRecentExpenses(expenses) {
    const container = document.getElementById('recent-expenses');
    if (!expenses.length) {
        container.innerHTML = '<p class="text-muted">No recent expenses</p>';
        return;
    }
    
    container.innerHTML = expenses.map(exp => `
        <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
            <div>
                <div class="fw-medium">${escapeHtml(exp.vendor)}</div>
                <small class="text-muted">${exp.date} · ${exp.category}</small>
            </div>
            <div class="fw-bold">${formatCurrency(exp.amount)}</div>
        </div>
    `).join('');
}

function renderTopVendors(vendors) {
    const container = document.getElementById('top-vendors');
    if (!vendors.length) {
        container.innerHTML = '<p class="text-muted">No vendor data</p>';
        return;
    }
    
    const maxTotal = Math.max(...vendors.map(v => v.total));
    
    container.innerHTML = vendors.map(v => `
        <div class="mb-3">
            <div class="d-flex justify-content-between mb-1">
                <span>${escapeHtml(v.vendor)}</span>
                <span class="fw-bold">${formatCurrency(v.total)}</span>
            </div>
            <div class="progress" style="height: 6px;">
                <div class="progress-bar" style="width: ${(v.total / maxTotal * 100)}%; background: linear-gradient(90deg, #7c3aed, #a78bfa);"></div>
            </div>
        </div>
    `).join('');
}

// ==================== UPLOAD ====================
let uploadQueue = [];

function setupUpload() {
    const zone = document.getElementById('upload-zone');
    const input = document.getElementById('file-input');
    const cameraBtn = document.getElementById('camera-btn');
    const cameraInput = document.getElementById('camera-input');
    const skipLink = document.getElementById('skip-upload');
    
    // Show form by default with today's date
    document.getElementById('form-date').value = new Date().toISOString().split('T')[0];
    
    zone.addEventListener('click', () => input.click());
    
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });
    
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files);
        if (files.length === 1) {
            processReceipt(files[0]);
        } else if (files.length > 1) {
            processBulkUpload(files);
        }
    });
    
    input.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        if (files.length === 1) {
            processReceipt(files[0]);
        } else if (files.length > 1) {
            processBulkUpload(files);
        }
    });
    
    cameraBtn.addEventListener('click', () => cameraInput.click());
    cameraInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) processReceipt(file);
        cameraInput.value = '';
    });
    
    skipLink.addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('form-vendor').value = '';
        document.getElementById('form-amount').value = '';
        document.getElementById('form-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('form-category').selectedIndex = 0;
        document.getElementById('form-description').value = '';
        document.getElementById('form-receipt-image').value = '';
        document.getElementById('form-extracted-text').value = '';
        document.getElementById('form-payment').selectedIndex = 0;
        document.getElementById('form-vendor').focus();
    });
}

async function processBulkUpload(files) {
    const queueDiv = document.getElementById('bulk-queue');
    const queueList = document.getElementById('bulk-queue-list');
    queueDiv.classList.remove('d-none');
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const item = document.createElement('div');
        item.className = 'd-flex justify-content-between align-items-center py-2 border-bottom';
        item.innerHTML = `<span>${escapeHtml(file.name)}</span><span class="text-muted">Processing...</span>`;
        queueList.appendChild(item);
        
        try {
            const formData = new FormData();
            formData.append('receipt', file);
            const resp = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await resp.json();
            
            if (data.success) {
                const p = data.parsed;
                const saveData = {
                    vendor: p.vendor,
                    amount: p.amount,
                    date: p.date,
                    category: p.category,
                    description: '',
                    receipt_image: p.receipt_image,
                    extracted_text: p.extracted_text,
                    payment_method: 'Unknown'
                };
                const saveResp = await api('expenses', {
                    method: 'POST',
                    body: JSON.stringify(saveData)
                });
                
                if (saveResp.success) {
                    item.innerHTML = `<span>${escapeHtml(file.name)}</span><span class="text-success fw-bold">✓ ${formatCurrency(p.amount)}</span>`;
                } else {
                    item.innerHTML = `<span>${escapeHtml(file.name)}</span><span class="text-warning">Saved (no amount)</span>`;
                }
            } else {
                item.innerHTML = `<span>${escapeHtml(file.name)}</span><span class="text-danger">Failed</span>`;
            }
        } catch (err) {
            item.innerHTML = `<span>${escapeHtml(file.name)}</span><span class="text-danger">Error</span>`;
        }
    }
    
    const doneMsg = document.createElement('div');
    doneMsg.className = 'text-success mt-2 fw-bold';
    doneMsg.textContent = `✅ ${files.length} receipt(s) processed! Check Expenses for details.`;
    queueList.appendChild(doneMsg);
}

async function processReceipt(file) {
    const formData = new FormData();
    formData.append('receipt', file);
    
    // Show loading
    const zone = document.getElementById('upload-zone');
    zone.innerHTML = '<div class="spinner-border text-primary"></div><p class="mt-2">Processing receipt...</p>';
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (data.success) {
            currentReceipt = data.parsed;
            
            // Show preview
            const preview = document.getElementById('receipt-preview');
            preview.src = URL.createObjectURL(file);
            preview.classList.remove('d-none');
            
            // Reset upload zone
            zone.innerHTML = `
                <i class="bi bi-cloud-arrow-up"></i>
                <h5>Drop another receipt or click to upload</h5>
                <p class="text-muted">Supports JPG, PNG, GIF, BMP, WebP</p>
            `;
            
            // Fill form
            document.getElementById('form-vendor').value = data.parsed.vendor;
            document.getElementById('form-amount').value = data.parsed.amount;
            document.getElementById('form-date').value = data.parsed.date;
            document.getElementById('form-category').value = data.parsed.category;
            document.getElementById('form-description').value = '';
            document.getElementById('form-receipt-image').value = data.parsed.receipt_image;
            document.getElementById('form-extracted-text').value = data.parsed.extracted_text;
            
            // Show form
            document.getElementById('extracted-data').classList.remove('d-none');
        } else {
            alert('Error: ' + data.error);
            resetUploadZone();
        }
    } catch (err) {
        alert('Upload failed: ' + err.message);
        resetUploadZone();
    }
}

function resetUploadZone() {
    const zone = document.getElementById('upload-zone');
    zone.innerHTML = `
        <i class="bi bi-cloud-arrow-up"></i>
        <h5>Drop receipt here or click to upload</h5>
        <p class="text-muted">Supports JPG, PNG, GIF, BMP, WebP</p>
    `;
}

// ==================== FORMS ====================
function setupForms() {
    document.getElementById('expense-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveExpense();
    });
    
    document.getElementById('edit-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveEdit();
    });
}

async function saveExpense() {
    const data = {
        vendor: document.getElementById('form-vendor').value,
        amount: parseFloat(document.getElementById('form-amount').value),
        date: document.getElementById('form-date').value,
        category: document.getElementById('form-category').value,
        description: document.getElementById('form-description').value,
        receipt_image: document.getElementById('form-receipt-image').value,
        extracted_text: document.getElementById('form-extracted-text').value,
        payment_method: document.getElementById('form-payment').value
    };
    
    const result = await api('expenses', {
        method: 'POST',
        body: JSON.stringify(data)
    });
    
    if (result.success) {
        alert('Expense saved!');
        // Reset form
        document.getElementById('expense-form').reset();
        document.getElementById('extracted-data').classList.add('d-none');
        document.getElementById('receipt-preview').classList.add('d-none');
        resetUploadZone();
        showPage('expenses');
    } else {
        alert('Error: ' + (result.error || 'Failed to save'));
    }
}

// ==================== EXPENSES LIST ====================
async function loadExpenses() {
    const params = new URLSearchParams();
    
    const startDate = document.getElementById('filter-start').value;
    const endDate = document.getElementById('filter-end').value;
    const category = document.getElementById('filter-category').value;
    const search = document.getElementById('filter-search').value;
    
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (category) params.append('category', category);
    if (search) params.append('search', search);
    
    const data = await api('expenses?' + params.toString());
    renderExpenses(data.expenses || []);
}

function renderExpenses(expenses) {
    const tbody = document.getElementById('expenses-list');
    
    if (!expenses.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No expenses found</td></tr>';
        return;
    }
    
    tbody.innerHTML = expenses.map(exp => `
        <tr>
            <td>${exp.date}</td>
            <td>
                <div class="fw-medium">${escapeHtml(exp.vendor)}</div>
                ${exp.description ? `<small class="text-muted">${escapeHtml(exp.description)}</small>` : ''}
            </td>
            <td><span class="category-badge bg-primary bg-opacity-10 text-primary">${exp.category}</span></td>
            <td class="fw-bold">${formatCurrency(exp.amount)}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="editExpense(${exp.id})">
                    <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteExpense(${exp.id})">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        </tr>
    `).join('');
}

async function editExpense(id) {
    const data = await api('expenses?search=&limit=1&offset=0');
    const expense = data.expenses.find(e => e.id === id);
    if (!expense) return;
    
    document.getElementById('edit-id').value = expense.id;
    document.getElementById('edit-vendor').value = expense.vendor;
    document.getElementById('edit-amount').value = expense.amount;
    document.getElementById('edit-date').value = expense.date;
    document.getElementById('edit-category').value = expense.category;
    document.getElementById('edit-description').value = expense.description || '';
    
    new bootstrap.Modal(document.getElementById('editModal')).show();
}

async function saveEdit() {
    const id = document.getElementById('edit-id').value;
    const data = {
        vendor: document.getElementById('edit-vendor').value,
        amount: parseFloat(document.getElementById('edit-amount').value),
        date: document.getElementById('edit-date').value,
        category: document.getElementById('edit-category').value,
        description: document.getElementById('edit-description').value
    };
    
    const result = await api(`expenses/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
    
    if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
        loadExpenses();
    }
}

async function deleteExpense(id) {
    if (!confirm('Delete this expense?')) return;
    
    const result = await api(`expenses/${id}`, { method: 'DELETE' });
    if (result.success) {
        loadExpenses();
    }
}

// ==================== REPORTS ====================
async function generateReport() {
    const type = document.getElementById('report-type').value;
    const startDate = document.getElementById('report-start').value;
    const endDate = document.getElementById('report-end').value;
    
    const params = new URLSearchParams({
        type, start_date: startDate, end_date: endDate
    });
    
    const data = await api('reports?' + params.toString());
    renderReport(data);
}

function renderReport(data) {
    const container = document.getElementById('report-results');
    
    if (!data.data || !data.data.length) {
        container.innerHTML = '<div class="alert alert-info">No data for this period</div>';
        return;
    }
    
    let html = `<h6 class="mb-3">${data.type.charAt(0).toUpperCase() + data.type.slice(1)} Report: ${data.period}</h6>`;
    
    html += '<div class="expense-table"><table class="table table-hover mb-0"><thead><tr>';
    
    if (data.type === 'summary') {
        html += '<th>Category</th><th>Transactions</th><th>Average</th><th>Total</th>';
        html += '</tr></thead><tbody>';
        data.data.forEach(row => {
            html += `<tr>
                <td>${row.category}</td>
                <td>${row.count}</td>
                <td>${formatCurrency(row.average)}</td>
                <td class="fw-bold">${formatCurrency(row.total)}</td>
            </tr>`;
        });
    } else if (data.type === 'daily') {
        html += '<th>Date</th><th>Transactions</th><th>Total</th>';
        html += '</tr></thead><tbody>';
        data.data.forEach(row => {
            html += `<tr>
                <td>${row.date}</td>
                <td>${row.count}</td>
                <td class="fw-bold">${formatCurrency(row.total)}</td>
            </tr>`;
        });
    } else if (data.type === 'vendor') {
        html += '<th>Vendor</th><th>Categories</th><th>Transactions</th><th>Total</th>';
        html += '</tr></thead><tbody>';
        data.data.forEach(row => {
            html += `<tr>
                <td>${escapeHtml(row.vendor)}</td>
                <td>${row.categories}</td>
                <td>${row.count}</td>
                <td class="fw-bold">${formatCurrency(row.total)}</td>
            </tr>`;
        });
    }
    
    // Add total row
    const total = data.data.reduce((sum, r) => sum + r.total, 0);
    html += `<tr class="table-light">
        <td colspan="3" class="text-end fw-bold">TOTAL</td>
        <td class="fw-bold">${formatCurrency(total)}</td>
    </tr>`;
    
    html += '</tbody></table></div>';
    
    container.innerHTML = html;
}

// ==================== EXPORT ====================
function exportCSV() {
    const startDate = document.getElementById('filter-start').value;
    const endDate = document.getElementById('filter-end').value;
    const category = document.getElementById('filter-category').value;
    
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (category) params.append('category', category);
    
    window.location.href = '/api/export?' + params.toString();
}

// ==================== UTILITIES ====================
function formatCurrency(amount) {
    return '$' + parseFloat(amount || 0).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
