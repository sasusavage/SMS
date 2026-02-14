/**
 * NaCCA School Management System
 * Main JavaScript
 */

// ============================================
// UTILITIES
// ============================================
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

// Format number as currency
const formatCurrency = (amount, currency = 'GHS') => {
    return `${currency} ${parseFloat(amount).toLocaleString('en-GH', { minimumFractionDigits: 2 })}`;
};

// Format date
const formatDate = (dateStr, format = 'short') => {
    const date = new Date(dateStr);
    const options = format === 'short'
        ? { month: 'short', day: 'numeric', year: 'numeric' }
        : { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    return date.toLocaleDateString('en-GH', options);
};

// Debounce function
const debounce = (fn, delay) => {
    let timeoutId;
    return (...args) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
};

// ============================================
// SIDEBAR
// ============================================
function toggleSidebar() {
    const sidebar = $('#sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Close sidebar on outside click (mobile)
document.addEventListener('click', (e) => {
    const sidebar = $('#sidebar');
    const menuBtn = $('.mobile-menu-btn');

    if (sidebar && sidebar.classList.contains('open')) {
        if (!sidebar.contains(e.target) && !menuBtn?.contains(e.target)) {
            sidebar.classList.remove('open');
        }
    }
});

// ============================================
// MODALS
// ============================================
function openModal(modalId) {
    const modal = $(`#${modalId}`);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = $(`#${modalId}`);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const activeModal = $('.modal-overlay.active');
        if (activeModal) {
            activeModal.classList.remove('active');
            document.body.style.overflow = '';
        }
    }
});

// ============================================
// ALERTS / NOTIFICATIONS
// ============================================
function showAlert(message, type = 'info', duration = 5000) {
    const alertContainer = $('#alert-container') || createAlertContainer();

    const alert = document.createElement('div');
    alert.className = `alert alert-${type} animate-slide-up`;
    alert.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            ${getAlertIcon(type)}
        </svg>
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="margin-left: auto; background: none; border: none; color: inherit; cursor: pointer;">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;

    alertContainer.appendChild(alert);

    if (duration > 0) {
        setTimeout(() => alert.remove(), duration);
    }
}

function createAlertContainer() {
    const container = document.createElement('div');
    container.id = 'alert-container';
    container.style.cssText = 'position: fixed; top: 80px; right: 20px; z-index: 1000; display: flex; flex-direction: column; gap: 10px; max-width: 400px;';
    document.body.appendChild(container);
    return container;
}

function getAlertIcon(type) {
    const icons = {
        success: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
        error: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
        warning: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'
    };
    return icons[type] || icons.info;
}

// ============================================
// FORM VALIDATION
// ============================================
function validateForm(formId) {
    const form = $(`#${formId}`);
    if (!form) return false;

    let isValid = true;
    const inputs = form.querySelectorAll('[required]');

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('error');
            isValid = false;
        } else {
            input.classList.remove('error');
        }
    });

    return isValid;
}

// ============================================
// SEARCH
// ============================================
async function searchStudents(query) {
    if (query.length < 2) return [];

    try {
        const response = await fetch(`/api/students/search?q=${encodeURIComponent(query)}`);
        return await response.json();
    } catch (error) {
        console.error('Search error:', error);
        return [];
    }
}

// ============================================
// ASSESSMENT FUNCTIONS
// ============================================
function calculateGrade(classwork, homework, project, exam, level = 'PRIMARY') {
    const total = parseFloat(classwork || 0) + parseFloat(homework || 0) +
        parseFloat(project || 0) + parseFloat(exam || 0);

    const scales = {
        PRIMARY: [
            [80, 100, '1', 'Highest'],
            [70, 79, '2', 'Higher'],
            [60, 69, '3', 'High'],
            [50, 59, '4', 'High Average'],
            [40, 49, '5', 'Average'],
            [30, 39, '6', 'Low Average'],
            [25, 29, '7', 'Below Average'],
            [20, 24, '8', 'Low'],
            [0, 19, '9', 'Very Low']
        ],
        JHS: [
            [80, 100, '1', 'Excellent'],
            [70, 79, '2', 'Very Good'],
            [60, 69, '3', 'Good'],
            [55, 59, '4', 'Credit'],
            [50, 54, '5', 'Credit'],
            [45, 49, '6', 'Credit'],
            [40, 44, '7', 'Pass'],
            [35, 39, '8', 'Pass'],
            [0, 34, '9', 'Fail']
        ],
        SHS: [
            [80, 100, 'A1', 'Excellent'],
            [70, 79, 'B2', 'Very Good'],
            [60, 69, 'B3', 'Good'],
            [55, 59, 'C4', 'Credit'],
            [50, 54, 'C5', 'Credit'],
            [45, 49, 'C6', 'Credit'],
            [40, 44, 'D7', 'Pass'],
            [35, 39, 'E8', 'Pass'],
            [0, 34, 'F9', 'Fail']
        ]
    };

    const scale = scales[level] || scales.PRIMARY;

    for (const [min, max, grade, remark] of scale) {
        if (total >= min && total <= max) {
            return { total, grade, remark };
        }
    }

    return { total, grade: null, remark: null };
}

// ============================================
// TABLE FUNCTIONS
// ============================================
function sortTable(tableId, columnIndex, type = 'string') {
    const table = $(`#${tableId}`);
    if (!table) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    const sorted = rows.sort((a, b) => {
        const aVal = a.cells[columnIndex]?.textContent.trim();
        const bVal = b.cells[columnIndex]?.textContent.trim();

        if (type === 'number') {
            return parseFloat(aVal) - parseFloat(bVal);
        }
        return aVal.localeCompare(bVal);
    });

    tbody.innerHTML = '';
    sorted.forEach(row => tbody.appendChild(row));
}

// ============================================
// INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages after 5 seconds
    $$('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Add loading state to forms on submit
    $$('form').forEach(form => {
        form.addEventListener('submit', function () {
            const btn = this.querySelector('[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner"></span> Processing...';
            }
        });
    });
});
