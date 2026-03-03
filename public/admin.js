// ============================================
// admin.js — Admin Dashboard Logic
// Handles pending reviews, approval/rejection, and test chat
// ============================================

const API_BASE = window.location.origin;
let currentReviewId = null;

// ---- Tab Switching ----
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');

    if (tabName === 'pending') loadPending();
    if (tabName === 'history') loadHistory();
}

// ---- Load Stats ----
async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`);
        const data = await res.json();
        document.getElementById('statPending').textContent = data.pending;
        document.getElementById('statApproved').textContent = data.approved;
        document.getElementById('statRejected').textContent = data.rejected;
        document.getElementById('pendingBadge').textContent = data.pending;
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

// ---- Load Pending Reviews ----
async function loadPending() {
    try {
        const res = await fetch(`${API_BASE}/api/admin/pending`);
        const data = await res.json();
        const container = document.getElementById('pendingList');

        if (!data.reviews || data.reviews.length === 0) {
            container.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">📭</span>
          <p>No pending reviews</p>
          <small>Applications will appear here when users submit forms via chat</small>
        </div>`;
            return;
        }

        container.innerHTML = data.reviews.map(r => `
      <div class="review-card" onclick="openReview('${r.id}', '${escapeHtml(r.scheme_name)}', \`${escapeHtml(r.form_summary)}\`)">
        <div class="review-card-header">
          <span class="review-scheme">📝 ${escapeHtml(r.scheme_name)}</span>
          <span class="review-status status-pending">⏳ Pending</span>
        </div>
        <div class="review-summary">${escapeHtml(r.form_summary)}</div>
        <div class="review-time">Submitted: ${new Date(r.created_at).toLocaleString()}</div>
      </div>
    `).join('');
    } catch (e) {
        console.error('Failed to load pending:', e);
    }
    loadStats();
}

// ---- Load History ----
async function loadHistory() {
    try {
        const res = await fetch(`${API_BASE}/api/admin/all`);
        const data = await res.json();
        const container = document.getElementById('historyList');

        if (!data.reviews || data.reviews.length === 0) {
            container.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">📋</span>
          <p>No review history yet</p>
        </div>`;
            return;
        }

        container.innerHTML = data.reviews.map(r => {
            const statusClass = r.status === 'approved' ? 'status-approved' : r.status === 'rejected' ? 'status-rejected' : 'status-pending';
            const statusIcon = r.status === 'approved' ? '✅' : r.status === 'rejected' ? '❌' : '⏳';
            return `
        <div class="review-card">
          <div class="review-card-header">
            <span class="review-scheme">📝 ${escapeHtml(r.scheme_name)}</span>
            <span class="review-status ${statusClass}">${statusIcon} ${r.status}</span>
          </div>
          <div class="review-summary">${escapeHtml(r.form_summary)}</div>
          ${r.reviewer_notes ? `<div class="review-time">Notes: ${escapeHtml(r.reviewer_notes)}</div>` : ''}
          <div class="review-time">${r.reviewed_at ? 'Reviewed: ' + new Date(r.reviewed_at).toLocaleString() : 'Submitted: ' + new Date(r.created_at).toLocaleString()}</div>
        </div>
      `;
        }).join('');
    } catch (e) {
        console.error('Failed to load history:', e);
    }
}

// ---- Modal ----
function openReview(reviewId, schemeName, summary) {
    currentReviewId = reviewId;
    document.getElementById('modalTitle').textContent = `Review: ${schemeName}`;
    document.getElementById('modalBody').textContent = summary;
    document.getElementById('reviewNotes').value = '';
    document.getElementById('modalOverlay').classList.add('open');
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('open');
    currentReviewId = null;
}

async function approveReview() {
    if (!currentReviewId) return;
    const notes = document.getElementById('reviewNotes').value;
    try {
        await fetch(`${API_BASE}/api/admin/approve/${currentReviewId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes }),
        });
        closeModal();
        loadPending();
        loadStats();
    } catch (e) {
        alert('Error approving review');
    }
}

async function rejectReview() {
    if (!currentReviewId) return;
    const notes = document.getElementById('reviewNotes').value;
    try {
        await fetch(`${API_BASE}/api/admin/reject/${currentReviewId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes }),
        });
        closeModal();
        loadPending();
        loadStats();
    } catch (e) {
        alert('Error rejecting review');
    }
}

// ---- Test Chat ----
async function sendChat(e) {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    // Show user message
    addChatMessage(message, 'user');
    input.value = '';

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, userId: 'admin-test-user', phone: '9999999999' }),
        });
        const data = await res.json();
        addChatMessage(data.reply, 'bot');

        // Refresh pending if a form might have been submitted
        loadStats();
    } catch (e) {
        addChatMessage('⚠️ Error connecting to server', 'bot');
    }
}

function addChatMessage(text, type) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `chat-msg ${type}`;
    div.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

// ---- Helpers ----
function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    loadPending();
    loadStats();
    // Auto-refresh every 10 seconds
    setInterval(() => { loadPending(); loadStats(); }, 10000);
});
