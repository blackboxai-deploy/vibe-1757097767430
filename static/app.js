/**
 * Telegram eBook Downloader - Frontend JavaScript
 */

class TelegramDownloader {
    constructor() {
        this.isAuthenticated = false;
        this.currentPhone = null;
        this.websocket = null;
        this.activeDownloads = new Map();
        
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.loadDownloadHistory();
        this.loadActiveDownloads();
    }

    setupEventListeners() {
        // Authentication
        document.getElementById('sendCodeBtn').addEventListener('click', () => this.sendCode());
        document.getElementById('verifyCodeBtn').addEventListener('click', () => this.verifyCode());
        
        // Download controls
        document.getElementById('startDownloadBtn').addEventListener('click', () => this.startDownload());
        
        // Input validation
        document.getElementById('phoneNumber').addEventListener('input', () => this.validateForm());
        document.getElementById('channelName').addEventListener('input', () => this.validateForm());
        
        // Toast close
        document.getElementById('toastClose').addEventListener('click', () => this.hideToast());
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                this.updateConnectionStatus(true);
                this.showToast('Connected', 'WebSocket connected successfully', 'success');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.websocket.onclose = () => {
                this.updateConnectionStatus(false);
                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.connectWebSocket(), 5000);
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus(false);
            };
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.updateConnectionStatus(false);
        }
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connectionStatus');
        const dot = statusElement.querySelector('div');
        const text = statusElement.querySelector('span');
        
        if (connected) {
            dot.className = 'w-3 h-3 rounded-full bg-green-500 mr-2';
            text.textContent = 'Connected';
        } else {
            dot.className = 'w-3 h-3 rounded-full bg-red-500 mr-2';
            text.textContent = 'Disconnected';
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'download_started':
                this.showToast('Download Started', `Started downloading from ${data.channel}`, 'success');
                this.loadActiveDownloads();
                break;
            case 'download_paused':
                this.showToast('Download Paused', 'Download has been paused', 'warning');
                this.updateDownloadStatus(data.download_id, 'paused');
                break;
            case 'download_resumed':
                this.showToast('Download Resumed', 'Download has been resumed', 'success');
                this.updateDownloadStatus(data.download_id, 'active');
                break;
            case 'download_cancelled':
                this.showToast('Download Cancelled', 'Download has been cancelled', 'danger');
                this.updateDownloadStatus(data.download_id, 'cancelled');
                break;
            case 'progress_update':
                this.updateProgressBar(data.download_id, data.progress, data);
                break;
        }
    }

    async sendCode() {
        const phoneNumber = document.getElementById('phoneNumber').value.trim();
        
        if (!phoneNumber) {
            this.showToast('Error', 'Please enter your phone number', 'danger');
            return;
        }

        try {
            const response = await this.apiCall('/api/authenticate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `phone_number=${encodeURIComponent(phoneNumber)}`
            });

            if (response.success) {
                this.currentPhone = phoneNumber;
                document.getElementById('phoneStep').classList.add('hidden');
                document.getElementById('codeStep').classList.remove('hidden');
                this.showToast('Code Sent', response.message, 'success');
            } else {
                this.showToast('Error', response.detail || 'Failed to send code', 'danger');
            }
        } catch (error) {
            console.error('Authentication error:', error);
            this.showToast('Error', 'Failed to send authentication code', 'danger');
        }
    }

    async verifyCode() {
        const code = document.getElementById('verificationCode').value.trim();
        
        if (!code) {
            this.showToast('Error', 'Please enter the verification code', 'danger');
            return;
        }

        try {
            const response = await this.apiCall('/api/verify-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `phone_number=${encodeURIComponent(this.currentPhone)}&code=${encodeURIComponent(code)}`
            });

            if (response.success) {
                this.isAuthenticated = true;
                document.getElementById('codeStep').classList.add('hidden');
                document.getElementById('authSuccess').classList.remove('hidden');
                this.validateForm();
                this.showToast('Success', 'Authentication successful!', 'success');
            } else {
                this.showToast('Error', response.detail || 'Invalid verification code', 'danger');
            }
        } catch (error) {
            console.error('Code verification error:', error);
            this.showToast('Error', 'Failed to verify code', 'danger');
        }
    }

    async startDownload() {
        const channelName = document.getElementById('channelName').value.trim();
        const maxFiles = document.getElementById('maxFiles').value;
        const skipDuplicates = document.getElementById('skipDuplicates').checked;
        
        // Get selected file types
        const fileTypes = Array.from(document.querySelectorAll('.file-type-checkbox:checked'))
            .map(cb => cb.value);

        if (!channelName) {
            this.showToast('Error', 'Please enter a channel name', 'danger');
            return;
        }

        if (fileTypes.length === 0) {
            this.showToast('Error', 'Please select at least one file type', 'danger');
            return;
        }

        try {
            const requestData = {
                channel_name: channelName,
                file_types: fileTypes,
                skip_duplicates: skipDuplicates
            };

            if (maxFiles) {
                requestData.max_files = parseInt(maxFiles);
            }

            const response = await this.apiCall('/api/start-download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            if (response.success) {
                this.showToast('Download Started', response.message, 'success');
                // Clear form
                document.getElementById('channelName').value = '';
                document.getElementById('maxFiles').value = '';
                // Refresh displays
                setTimeout(() => {
                    this.loadActiveDownloads();
                    this.loadDownloadHistory();
                }, 1000);
            } else {
                this.showToast('Error', response.detail || 'Failed to start download', 'danger');
            }
        } catch (error) {
            console.error('Download start error:', error);
            this.showToast('Error', 'Failed to start download', 'danger');
        }
    }

    async loadActiveDownloads() {
        try {
            const response = await this.apiCall('/api/download-status');
            
            if (response.success) {
                const activeDownloads = response.data.filter(download => 
                    ['active', 'paused', 'pending'].includes(download.status)
                );
                this.displayActiveDownloads(activeDownloads);
            }
        } catch (error) {
            console.error('Failed to load active downloads:', error);
        }
    }

    async loadDownloadHistory() {
        try {
            const response = await this.apiCall('/api/download-history');
            
            if (response.success) {
                this.displayDownloadHistory(response.data);
            }
        } catch (error) {
            console.error('Failed to load download history:', error);
        }
    }

    displayActiveDownloads(downloads) {
        const container = document.getElementById('activeDownloads');
        
        if (downloads.length === 0) {
            container.innerHTML = '<div class="text-gray-500 text-center py-8">No active downloads</div>';
            return;
        }

        container.innerHTML = downloads.map(download => this.createDownloadCard(download, true)).join('');
    }

    displayDownloadHistory(downloads) {
        const container = document.getElementById('downloadHistory');
        
        if (downloads.length === 0) {
            container.innerHTML = '<div class="text-gray-500 text-center py-8">No downloads yet</div>';
            return;
        }

        container.innerHTML = downloads.map(download => this.createDownloadCard(download, false)).join('');
    }

    createDownloadCard(download, isActive) {
        const statusColors = {
            pending: 'bg-yellow-100 text-yellow-800',
            active: 'bg-blue-100 text-blue-800',
            paused: 'bg-orange-100 text-orange-800',
            completed: 'bg-green-100 text-green-800',
            failed: 'bg-red-100 text-red-800',
            cancelled: 'bg-gray-100 text-gray-800'
        };

        const controls = isActive ? `
            <div class="flex space-x-2">
                ${download.status === 'active' ? 
                    `<button onclick="app.pauseDownload(${download.id})" class="px-3 py-1 bg-orange-500 text-white text-sm rounded hover:bg-orange-600">Pause</button>` :
                    `<button onclick="app.resumeDownload(${download.id})" class="px-3 py-1 bg-green-500 text-white text-sm rounded hover:bg-green-600">Resume</button>`
                }
                <button onclick="app.cancelDownload(${download.id})" class="px-3 py-1 bg-red-500 text-white text-sm rounded hover:bg-red-600">Cancel</button>
            </div>
        ` : '';

        const progressBar = download.progress > 0 ? `
            <div class="mt-3">
                <div class="flex justify-between text-sm text-gray-600 mb-1">
                    <span>Progress: ${download.progress.toFixed(1)}%</span>
                    <span>${download.completed_files}/${download.total_files} files</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                    <div class="bg-blue-500 h-2 rounded-full transition-all duration-300" style="width: ${download.progress}%"></div>
                </div>
            </div>
        ` : '';

        return `
            <div class="border border-gray-200 rounded-lg p-4" id="download-${download.id}">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <div class="flex items-center space-x-3">
                            <h3 class="font-medium text-gray-900">${download.channel_name}</h3>
                            <span class="px-2 py-1 text-xs rounded-full ${statusColors[download.status]}">${download.status}</span>
                        </div>
                        <div class="text-sm text-gray-600 mt-1">
                            Started: ${new Date(download.created_at).toLocaleString()}
                        </div>
                        ${download.file_types ? `
                            <div class="text-sm text-gray-600 mt-1">
                                File types: ${download.file_types.join(', ').toUpperCase()}
                            </div>
                        ` : ''}
                        ${progressBar}
                    </div>
                    ${controls}
                </div>
            </div>
        `;
    }

    async pauseDownload(downloadId) {
        try {
            const response = await this.apiCall(`/api/pause-download/${downloadId}`, {
                method: 'POST'
            });

            if (response.success) {
                this.showToast('Download Paused', response.message, 'warning');
            } else {
                this.showToast('Error', response.detail || 'Failed to pause download', 'danger');
            }
        } catch (error) {
            console.error('Pause download error:', error);
            this.showToast('Error', 'Failed to pause download', 'danger');
        }
    }

    async resumeDownload(downloadId) {
        try {
            const response = await this.apiCall(`/api/resume-download/${downloadId}`, {
                method: 'POST'
            });

            if (response.success) {
                this.showToast('Download Resumed', response.message, 'success');
            } else {
                this.showToast('Error', response.detail || 'Failed to resume download', 'danger');
            }
        } catch (error) {
            console.error('Resume download error:', error);
            this.showToast('Error', 'Failed to resume download', 'danger');
        }
    }

    async cancelDownload(downloadId) {
        if (!confirm('Are you sure you want to cancel this download?')) {
            return;
        }

        try {
            const response = await this.apiCall(`/api/cancel-download/${downloadId}`, {
                method: 'DELETE'
            });

            if (response.success) {
                this.showToast('Download Cancelled', response.message, 'danger');
                this.loadActiveDownloads();
            } else {
                this.showToast('Error', response.detail || 'Failed to cancel download', 'danger');
            }
        } catch (error) {
            console.error('Cancel download error:', error);
            this.showToast('Error', 'Failed to cancel download', 'danger');
        }
    }

    updateDownloadStatus(downloadId, status) {
        const downloadCard = document.getElementById(`download-${downloadId}`);
        if (downloadCard) {
            // Reload active downloads to reflect the change
            setTimeout(() => this.loadActiveDownloads(), 500);
        }
    }

    updateProgressBar(downloadId, progress, data) {
        const downloadCard = document.getElementById(`download-${downloadId}`);
        if (downloadCard) {
            const progressBar = downloadCard.querySelector('.bg-blue-500');
            if (progressBar) {
                progressBar.style.width = `${progress}%`;
            }
        }
    }

    validateForm() {
        const phoneNumber = document.getElementById('phoneNumber').value.trim();
        const channelName = document.getElementById('channelName').value.trim();
        const startBtn = document.getElementById('startDownloadBtn');
        
        const isValid = this.isAuthenticated && channelName.length > 0;
        startBtn.disabled = !isValid;
    }

    showToast(title, message, type = 'info') {
        const toast = document.getElementById('toast');
        const titleEl = document.getElementById('toastTitle');
        const messageEl = document.getElementById('toastMessage');
        const iconEl = document.getElementById('toastIcon');
        
        titleEl.textContent = title;
        messageEl.textContent = message;
        
        // Set icon based on type
        const icons = {
            success: '<svg class="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>',
            danger: '<svg class="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>',
            warning: '<svg class="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>',
            info: '<svg class="w-5 h-5 text-blue-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>'
        };
        
        iconEl.innerHTML = icons[type] || icons.info;
        
        toast.classList.remove('hidden');
        
        // Auto-hide after 5 seconds
        setTimeout(() => this.hideToast(), 5000);
    }

    hideToast() {
        document.getElementById('toast').classList.add('hidden');
    }

    async apiCall(endpoint, options = {}) {
        const response = await fetch(endpoint, options);
        return await response.json();
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new TelegramDownloader();
});