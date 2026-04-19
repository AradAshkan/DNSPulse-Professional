import requests
import webbrowser
import sys
import asyncio
import time
import statistics
import random
import json
import os
from packaging import version
from datetime import datetime
from collections import defaultdict
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTableWidget, QTableWidgetItem, QLabel, QProgressBar,
    QGroupBox, QGridLayout, QMessageBox, QHeaderView, QTabWidget,
    QTextEdit, QSpinBox, QComboBox, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QSettings
from PyQt6.QtGui import QFont, QColor, QBrush, QPalette

import dns.asyncresolver
import dns.resolver
import ctypes


# ==================== CONSTANTS ====================
DEFAULT_DNS_SERVERS = {
    "Google Primary": "8.8.8.8",
    "Google Secondary": "8.8.4.4",
    "Cloudflare Primary": "1.1.1.1",
    "Cloudflare Secondary": "1.0.0.1",
    "Quad9": "9.9.9.9",
    "Quad9 Secondary": "149.112.112.112",
    "OpenDNS": "208.67.222.222",
    "OpenDNS Family": "208.67.222.123",
    "Cloudflare Security": "1.1.1.2",
    "Comodo": "8.26.56.26"
}

DEFAULT_DOMAINS = [
    "google.com", "github.com", "wikipedia.org", "cloudflare.com",
    "microsoft.com", "amazon.com", "youtube.com", "reddit.com",
    "stackoverflow.com", "netflix.com", "facebook.com", "instagram.com"
]

# ==================== CONFIGURATION MANAGER ====================
class ConfigManager:
    def __init__(self):
        self.settings = QSettings('DNSPulse', 'Professional')
        self.load_config()
    
    def load_config(self):
        """Load configuration from QSettings"""
        self.REQUESTS_PER_DOMAIN = self.settings.value('requests_per_domain', 5, type=int)
        self.MAX_CONCURRENT = self.settings.value('max_concurrent', 8, type=int)
        self.TIMEOUT = self.settings.value('timeout', 3, type=int)
        self.WARMUP_REQUESTS = self.settings.value('warmup_requests', 2, type=int)
        self.COOLDOWN_MS = self.settings.value('cooldown_ms', 50, type=int)
        self.ENABLE_JITTER = self.settings.value('enable_jitter', True, type=bool)
        self.ENABLE_PERCENTILES = self.settings.value('enable_percentiles', True, type=bool)
        
        # Load custom DNS servers and domains
        custom_servers = self.settings.value('custom_dns_servers', {})
        if custom_servers:
            self.DNS_SERVERS = {**DEFAULT_DNS_SERVERS, **custom_servers}
        else:
            self.DNS_SERVERS = DEFAULT_DNS_SERVERS.copy()
        
        custom_domains = self.settings.value('custom_domains', [])
        if custom_domains:
            self.DOMAINS = custom_domains
        else:
            self.DOMAINS = DEFAULT_DOMAINS.copy()
    
    def save_config(self):
        """Save configuration to QSettings"""
        self.settings.setValue('requests_per_domain', self.REQUESTS_PER_DOMAIN)
        self.settings.setValue('max_concurrent', self.MAX_CONCURRENT)
        self.settings.setValue('timeout', self.TIMEOUT)
        self.settings.setValue('warmup_requests', self.WARMUP_REQUESTS)
        self.settings.setValue('cooldown_ms', self.COOLDOWN_MS)
        self.settings.setValue('enable_jitter', self.ENABLE_JITTER)
        self.settings.setValue('enable_percentiles', self.ENABLE_PERCENTILES)
        
        # Save custom servers (excluding defaults)
        custom_servers = {k: v for k, v in self.DNS_SERVERS.items() if k not in DEFAULT_DNS_SERVERS}
        self.settings.setValue('custom_dns_servers', custom_servers)
        
        # Save custom domains (if different from defaults)
        if self.DOMAINS != DEFAULT_DOMAINS:
            self.settings.setValue('custom_domains', self.DOMAINS)
        else:
            self.settings.remove('custom_domains')
    
    def reset_to_default(self):
        """Reset all settings to default values"""
        self.REQUESTS_PER_DOMAIN = 5
        self.MAX_CONCURRENT = 8
        self.TIMEOUT = 3
        self.WARMUP_REQUESTS = 2
        self.COOLDOWN_MS = 50
        self.ENABLE_JITTER = True
        self.ENABLE_PERCENTILES = True
        self.DNS_SERVERS = DEFAULT_DNS_SERVERS.copy()
        self.DOMAINS = DEFAULT_DOMAINS.copy()
        self.save_config()

# ==================== SETTINGS DIALOG ====================
class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 500)
        self.setup_ui()
        self.load_current_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Test Settings Group
        test_group = QGroupBox("Test Settings")
        test_layout = QGridLayout()
        
        self.requests_spin = QSpinBox()
        self.requests_spin.setRange(1, 20)
        self.requests_spin.setSuffix(" requests")
        
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 20)
        self.concurrent_spin.setSuffix(" concurrent")
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setSuffix(" seconds")
        
        self.warmup_spin = QSpinBox()
        self.warmup_spin.setRange(0, 10)
        self.warmup_spin.setSuffix(" requests")
        
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(0, 200)
        self.cooldown_spin.setSuffix(" ms")
        
        self.jitter_check = QCheckBox("Enable Jitter Analysis")
        self.percentiles_check = QCheckBox("Enable Percentiles (P95, P99)")
        
        test_layout.addWidget(QLabel("Requests per domain:"), 0, 0)
        test_layout.addWidget(self.requests_spin, 0, 1)
        test_layout.addWidget(QLabel("Max concurrent requests:"), 1, 0)
        test_layout.addWidget(self.concurrent_spin, 1, 1)
        test_layout.addWidget(QLabel("Timeout:"), 2, 0)
        test_layout.addWidget(self.timeout_spin, 2, 1)
        test_layout.addWidget(QLabel("Warmup requests:"), 3, 0)
        test_layout.addWidget(self.warmup_spin, 3, 1)
        test_layout.addWidget(QLabel("Cooldown between requests:"), 4, 0)
        test_layout.addWidget(self.cooldown_spin, 4, 1)
        test_layout.addWidget(self.jitter_check, 5, 0, 1, 2)
        test_layout.addWidget(self.percentiles_check, 6, 0, 1, 2)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        # DNS Servers Group
        servers_group = QGroupBox("DNS Servers")
        servers_layout = QVBoxLayout()
        
        self.servers_text = QTextEdit()
        self.servers_text.setMaximumHeight(150)
        self.servers_text.setPlaceholderText("Format: Server Name: IP Address\nExample:\nMy DNS: 1.2.3.4\nAnother DNS: 5.6.7.8")
        
        servers_layout.addWidget(QLabel("Custom DNS servers (one per line, format: Name: IP):"))
        servers_layout.addWidget(self.servers_text)
        
        servers_group.setLayout(servers_layout)
        layout.addWidget(servers_group)
        
        # Domains Group
        domains_group = QGroupBox("Test Domains")
        domains_layout = QVBoxLayout()
        
        self.domains_text = QTextEdit()
        self.domains_text.setMaximumHeight(150)
        self.domains_text.setPlaceholderText("Enter one domain per line:\nexample.com\ntest.org\napi.example.net")
        
        domains_layout.addWidget(QLabel("Domains to test (one per line):"))
        domains_layout.addWidget(self.domains_text)
        
        domains_group.setLayout(domains_layout)
        layout.addWidget(domains_group)
        
        # Buttons
        button_box = QDialogButtonBox()
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self.reset_to_default)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_box.addButton(reset_btn, QDialogButtonBox.ButtonRole.ActionRole)
        button_box.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        
        layout.addWidget(button_box)
    
    def load_current_settings(self):
        """Load current settings into UI"""
        self.requests_spin.setValue(self.config_manager.REQUESTS_PER_DOMAIN)
        self.concurrent_spin.setValue(self.config_manager.MAX_CONCURRENT)
        self.timeout_spin.setValue(self.config_manager.TIMEOUT)
        self.warmup_spin.setValue(self.config_manager.WARMUP_REQUESTS)
        self.cooldown_spin.setValue(self.config_manager.COOLDOWN_MS)
        self.jitter_check.setChecked(self.config_manager.ENABLE_JITTER)
        self.percentiles_check.setChecked(self.config_manager.ENABLE_PERCENTILES)
        
        # Load DNS servers
        servers_text = ""
        for name, ip in self.config_manager.DNS_SERVERS.items():
            servers_text += f"{name}: {ip}\n"
        self.servers_text.setText(servers_text.strip())
        
        # Load domains
        domains_text = "\n".join(self.config_manager.DOMAINS)
        self.domains_text.setText(domains_text)
    
    def reset_to_default(self):
        """Reset all settings to default"""
        self.config_manager.reset_to_default()
        self.load_current_settings()
        QMessageBox.information(self, "Reset", "Settings reset to default values!")
    
    def save_settings(self):
        """Save settings from UI to config manager"""
        # Save basic settings
        self.config_manager.REQUESTS_PER_DOMAIN = self.requests_spin.value()
        self.config_manager.MAX_CONCURRENT = self.concurrent_spin.value()
        self.config_manager.TIMEOUT = self.timeout_spin.value()
        self.config_manager.WARMUP_REQUESTS = self.warmup_spin.value()
        self.config_manager.COOLDOWN_MS = self.cooldown_spin.value()
        self.config_manager.ENABLE_JITTER = self.jitter_check.isChecked()
        self.config_manager.ENABLE_PERCENTILES = self.percentiles_check.isChecked()
        
        # Parse and save DNS servers
        custom_servers = {}
        servers_lines = self.servers_text.toPlainText().strip().split('\n')
        for line in servers_lines:
            if ':' in line:
                parts = line.split(':', 1)
                name = parts[0].strip()
                ip = parts[1].strip()
                if name and ip:
                    custom_servers[name] = ip
        
        if custom_servers:
            self.config_manager.DNS_SERVERS = {**DEFAULT_DNS_SERVERS, **custom_servers}
        else:
            self.config_manager.DNS_SERVERS = DEFAULT_DNS_SERVERS.copy()
        
        # Parse and save domains
        domains = [d.strip() for d in self.domains_text.toPlainText().strip().split('\n') if d.strip()]
        if domains:
            self.config_manager.DOMAINS = domains
        else:
            self.config_manager.DOMAINS = DEFAULT_DOMAINS.copy()
        
        # Save to persistent storage
        self.config_manager.save_config()
        
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully!\nThey will be loaded on next application start.")
        self.accept()

# ==================== TEST ENGINE ====================
class AdvancedDNSPulse:
    def __init__(self, config):
        self.config = config
        self.results = {}
        self.error_counts = defaultdict(int)
        
    async def test_single_request(self, server_ip, domain, sem, request_id):
        """Test single DNS request with high accuracy"""
        async with sem:
            resolver = dns.asyncresolver.Resolver()
            resolver.nameservers = [server_ip]
            resolver.timeout = self.config.TIMEOUT / 2
            resolver.lifetime = self.config.TIMEOUT
            resolver.cache = None
            
            # Random delay to prevent bias
            await asyncio.sleep(random.uniform(0, self.config.COOLDOWN_MS / 1000))
            
            try:
                start = time.perf_counter()
                
                resolve_task = asyncio.create_task(resolver.resolve(domain, "A"))
                response = await asyncio.wait_for(resolve_task, timeout=self.config.TIMEOUT)
                
                end = time.perf_counter()
                elapsed_ms = (end - start) * 1000
                
                if response and len(response) > 0:
                    return {
                        "success": True,
                        "time_ms": elapsed_ms,
                        "domain": domain
                    }
                else:
                    self.error_counts["empty_response"] += 1
                    return None
                    
            except dns.resolver.NXDOMAIN:
                self.error_counts["nxdomain"] += 1
                return None
            except dns.resolver.Timeout:
                self.error_counts["timeout"] += 1
                return None
            except asyncio.TimeoutError:
                self.error_counts["asyncio_timeout"] += 1
                return None
            except Exception as e:
                self.error_counts[type(e).__name__] += 1
                return None
    
    async def test_server(self, server_name, server_ip, progress_callback=None):
        """Complete test for one DNS server"""
        # Warmup phase
        warmup_sem = asyncio.Semaphore(2)
        warmup_domains = ["example.com", "test.org"]
        for _ in range(self.config.WARMUP_REQUESTS):
            for domain in warmup_domains:
                await self.test_single_request(server_ip, domain, warmup_sem, -1)
                await asyncio.sleep(0.05)
        
        # Prepare all requests
        all_requests = []
        request_id = 0
        
        for domain in self.config.DOMAINS:
            for _ in range(self.config.REQUESTS_PER_DOMAIN):
                request_id += 1
                all_requests.append((domain, request_id))
        
        # Randomize order
        random.shuffle(all_requests)
        
        # Execute with concurrency limit
        sem = asyncio.Semaphore(self.config.MAX_CONCURRENT)
        tasks = []
        
        for idx, (domain, rid) in enumerate(all_requests):
            task = self.test_single_request(server_ip, domain, sem, rid)
            tasks.append(task)
            
            # Update progress
            if progress_callback and idx % 10 == 0:
                progress_callback(idx, len(all_requests))
        
        responses = await asyncio.gather(*tasks)
        
        # Filter successful results
        successful = [r for r in responses if r and r["success"]]
        
        if not successful:
            return None
        
        # Extract times
        times = [r["time_ms"] for r in successful]
        
        # Remove outliers using IQR method
        if len(times) > 4:
            sorted_times = sorted(times)
            q1 = sorted_times[len(sorted_times) // 4]
            q3 = sorted_times[3 * len(sorted_times) // 4]
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            filtered_times = [t for t in times if lower <= t <= upper]
        else:
            filtered_times = times
        
        # Statistical calculations
        stats = {
            "name": server_name,
            "ip": server_ip,
            "median": statistics.median(filtered_times),
            "mean": sum(filtered_times) / len(filtered_times),
            "min": min(filtered_times),
            "max": max(filtered_times),
            "std_dev": statistics.stdev(filtered_times) if len(filtered_times) > 1 else 0,
            "success_rate": (len(successful) / len(responses)) * 100,
            "total_requests": len(responses),
            "successful_requests": len(successful),
            "sample_count": len(filtered_times)
        }
        
        # Add jitter (stability)
        if self.config.ENABLE_JITTER:
            stats["jitter"] = stats["max"] - stats["min"]
            stats["stability_score"] = 100 - (stats["jitter"] / stats["median"] * 100) if stats["median"] > 0 else 0
        
        # Add percentiles
        if self.config.ENABLE_PERCENTILES and len(filtered_times) >= 10:
            sorted_times = sorted(filtered_times)
            stats["p95"] = sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 0 else stats["max"]
            stats["p99"] = sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 0 else stats["max"]
        
        # Final score (weighted: 60% speed + 30% stability + 10% reliability)
        speed_score = (min([s["median"] for s in self.results.values()] + [stats["median"]]) / stats["median"]) * 60 if stats["median"] > 0 else 0
        stability_score = stats.get("stability_score", 0) * 0.3
        reliability_score = stats["success_rate"] * 0.1
        
        stats["final_score"] = speed_score + stability_score + reliability_score
        
        return stats
    
    async def run_DNSPulse(self, progress_callback=None):
        """Run complete DNSPulse"""
        self.results = {}
        
        # Test servers in random order
        server_list = list(self.config.DNS_SERVERS.items())
        random.shuffle(server_list)
        
        for idx, (name, ip) in enumerate(server_list):
            if progress_callback:
                progress_callback(idx, len(server_list), f"Testing {name}...")
            
            result = await self.test_server(name, ip, progress_callback)
            if result:
                self.results[name] = result
        
        return self.results

# ==================== TEST WORKER THREAD ====================
class TestWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            DNSPulse = AdvancedDNSPulse(self.config)
            
            def progress_callback(current, total, message=""):
                self.progress.emit(current, total, message)
            
            results = loop.run_until_complete(DNSPulse.run_DNSPulse(progress_callback))
            self.finished.emit(results)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()

# ==================== MAIN WINDOW ====================
class ModernDNSPulse(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DNSPulse Professional v2.0")
        self.setMinimumSize(1200, 700)
        self.setWindowIcon(QIcon("logo.ico"))
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dnspulse.app")
        
        # Block fullscreen
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowFullscreenButtonHint)
        self.setFixedSize(self.width(), self.height())
        
        self.config_manager = ConfigManager()
        self.results = {}
        
        self.setup_ui()
        self.apply_modern_style()
        
    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("🚀 DNSPulse Professional")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2196F3;")
        
        version_label = QLabel("v2.0")
        version_label.setStyleSheet("color: #666; font-size: 12px;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(version_label)
        header_layout.addStretch()
        
        # Settings button
        settings_btn = QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self.show_settings)
        settings_btn.setFixedWidth(100)
        header_layout.addWidget(settings_btn)
        
        main_layout.addLayout(header_layout)
        
        # Tabs
        self.tab_widget = QTabWidget()
        
        # Main tab
        self.main_tab = QWidget()
        self.setup_main_tab()
        self.tab_widget.addTab(self.main_tab, "📊 Main Test")
        
        # Detailed results tab
        self.detailed_tab = QWidget()
        self.setup_detailed_tab()
        self.tab_widget.addTab(self.detailed_tab, "📈 Detailed Results")
        
        # Log tab
        self.log_tab = QWidget()
        self.setup_log_tab()
        self.tab_widget.addTab(self.log_tab, "📝 Console")
        
        main_layout.addWidget(self.tab_widget)
        
        # Status bar
        self.status_label = QLabel("✅ Ready to test")
        self.status_label.setStyleSheet("color: #4CAF50; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
    def setup_main_tab(self):
        layout = QVBoxLayout(self.main_tab)
        
        # Control group
        control_group = QGroupBox("Test Control")
        control_layout = QHBoxLayout()
        
        self.test_btn = QPushButton("▶️ Start DNS Test")
        self.test_btn.clicked.connect(self.start_test)
        self.test_btn.setMinimumHeight(40)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #666;
            }
        """)
        
        self.export_btn = QPushButton("💾 Export Results")
        self.export_btn.clicked.connect(self.export_results)
        self.export_btn.setEnabled(False)
        
        control_layout.addWidget(self.test_btn)
        control_layout.addWidget(self.export_btn)
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        
        # Results table
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(7)
        self.result_table.setHorizontalHeaderLabels([
            "DNS Server", "Median (ms)", "Avg (ms)", 
            "Min (ms)", "Max (ms)", "Success %", "Score"
        ])
        
        # Table settings
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #2d2d2d;
                gridline-color: #3d3d3d;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        
        layout.addWidget(self.result_table)
        
        # Best server box
        self.best_box = QGroupBox("🏆 Best DNS Server")
        best_layout = QGridLayout()
        
        self.best_name_label = QLabel("-")
        self.best_name_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.best_name_label.setStyleSheet("color: #FFD700;")
        
        self.best_stats_label = QLabel("-")
        
        best_layout.addWidget(self.best_name_label, 0, 0)
        best_layout.addWidget(self.best_stats_label, 1, 0)
        
        self.best_box.setLayout(best_layout)
        layout.addWidget(self.best_box)
        
    def setup_detailed_tab(self):
        layout = QVBoxLayout(self.detailed_tab)
        
        # Advanced statistics
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                font-family: 'Courier New';
                font-size: 11px;
            }
        """)
        
        layout.addWidget(self.stats_text)
        
    def setup_log_tab(self):
        layout = QVBoxLayout(self.log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                font-family: 'Courier New';
                font-size: 10px;
            }
        """)
        
        clear_log_btn = QPushButton("🗑️ Clear Log")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        
        layout.addWidget(self.log_text)
        layout.addWidget(clear_log_btn)
        
    def apply_modern_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QTabWidget::pane {
                border: 1px solid #3d3d3d;
                border-radius: 5px;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                padding: 8px 15px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
                color: white;
            }
            QProgressBar {
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 5px;
            }
            QDialog {
                background-color: #121212;
            }
        """)
        
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def show_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            # Reload config after settings change
            self.config_manager.load_config()
            self.log_message("Settings updated and saved")
            QMessageBox.information(self, "Settings", "Settings have been saved and will be used for future tests.")
        
    def start_test(self):
        self.test_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.result_table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("🔄 Running DNS test...")
        self.log_message("Starting DNS test")
        
        # Create a new config object with current settings
        class TempConfig:
            pass
        
        self.current_config = TempConfig()
        self.current_config.REQUESTS_PER_DOMAIN = self.config_manager.REQUESTS_PER_DOMAIN
        self.current_config.MAX_CONCURRENT = self.config_manager.MAX_CONCURRENT
        self.current_config.TIMEOUT = self.config_manager.TIMEOUT
        self.current_config.WARMUP_REQUESTS = self.config_manager.WARMUP_REQUESTS
        self.current_config.COOLDOWN_MS = self.config_manager.COOLDOWN_MS
        self.current_config.ENABLE_JITTER = self.config_manager.ENABLE_JITTER
        self.current_config.ENABLE_PERCENTILES = self.config_manager.ENABLE_PERCENTILES
        self.current_config.DNS_SERVERS = self.config_manager.DNS_SERVERS
        self.current_config.DOMAINS = self.config_manager.DOMAINS
        
        self.worker = TestWorker(self.current_config)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.show_results)
        self.worker.error.connect(self.show_error)
        self.worker.start()
        
    def update_progress(self, current, total, message):
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
            self.progress_label.setText(f"{message} ({current}/{total})")
            self.log_message(message)
        
    def show_results(self, results):
        self.results = results
        self.progress_bar.setVisible(False)
        self.progress_label.clear()
        self.status_label.setText("✅ Test completed successfully")
        self.log_message("Test completed")
        
        if not results:
            self.status_label.setText("❌ No results received")
            QMessageBox.warning(self, "Error", "No successful DNS servers found!")
            self.test_btn.setEnabled(True)
            return
        
        # Display in table
        sorted_results = sorted(results.items(), key=lambda x: x[1]["final_score"], reverse=True)
        
        for row, (name, data) in enumerate(sorted_results):
            self.result_table.insertRow(row)
            
            # Color coding based on score
            item_name = QTableWidgetItem(name)
            if row == 0:
                item_name.setForeground(QBrush(QColor(255, 215, 0)))  # Gold
                item_name.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            
            self.result_table.setItem(row, 0, item_name)
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{data['median']:.2f}"))
            self.result_table.setItem(row, 2, QTableWidgetItem(f"{data['mean']:.2f}"))
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{data['min']:.2f}"))
            self.result_table.setItem(row, 4, QTableWidgetItem(f"{data['max']:.2f}"))
            self.result_table.setItem(row, 5, QTableWidgetItem(f"{data['success_rate']:.1f}%"))
            self.result_table.setItem(row, 6, QTableWidgetItem(f"{data['final_score']:.1f}"))
        
        # Display best server
        best_name, best_data = sorted_results[0]
        self.best_name_label.setText(f"{best_name} ({best_data['ip']})")
        self.best_stats_label.setText(
            f"Speed: {best_data['median']:.2f} ms | "
            f"Success: {best_data['success_rate']:.1f}% | "
            f"Stability: {best_data.get('stability_score', 0):.1f}% | "
            f"Final Score: {best_data['final_score']:.1f}"
        )
        
        # Display detailed statistics
        detailed_stats = "📊 Detailed DNS Test Statistics\n" + "="*50 + "\n\n"
        for name, data in sorted_results:
            detailed_stats += f"🔹 {name} ({data['ip']})\n"
            detailed_stats += f"   • Median: {data['median']:.2f} ms\n"
            detailed_stats += f"   • Mean: {data['mean']:.2f} ms\n"
            detailed_stats += f"   • Min/Max: {data['min']:.2f} / {data['max']:.2f} ms\n"
            detailed_stats += f"   • Std Dev: {data['std_dev']:.2f} ms\n"
            if 'jitter' in data:
                detailed_stats += f"   • Jitter: {data['jitter']:.2f} ms\n"
            if 'p95' in data:
                detailed_stats += f"   • P95/P99: {data['p95']:.2f} / {data['p99']:.2f} ms\n"
            detailed_stats += f"   • Success Rate: {data['success_rate']:.1f}%\n"
            detailed_stats += f"   • Final Score: {data['final_score']:.1f}/100\n\n"
        
        self.stats_text.setText(detailed_stats)
        
        self.test_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        
        # Notification
        QMessageBox.information(self, "Test Complete", 
            f"Best DNS Server: {best_name}\n"
            f"Speed: {best_data['median']:.2f} ms | Score: {best_data['final_score']:.1f}")
        
    def show_error(self, error_msg):
        self.status_label.setText(f"❌ Error: {error_msg}")
        self.progress_bar.setVisible(False)
        self.test_btn.setEnabled(True)
        self.log_message(f"Error: {error_msg}")
        QMessageBox.critical(self, "Error", f"Error during test:\n{error_msg}")
        
    def export_results(self):
        if not self.results:
            return
        
        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Results", 
            f"dns_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "domains_tested": len(self.config_manager.DOMAINS),
                "requests_per_domain": self.config_manager.REQUESTS_PER_DOMAIN,
                "timeout": self.config_manager.TIMEOUT,
                "max_concurrent": self.config_manager.MAX_CONCURRENT,
                "warmup_requests": self.config_manager.WARMUP_REQUESTS,
                "enable_jitter": self.config_manager.ENABLE_JITTER,
                "enable_percentiles": self.config_manager.ENABLE_PERCENTILES
            },
            "dns_servers": self.config_manager.DNS_SERVERS,
            "test_domains": self.config_manager.DOMAINS,
            "results": self.results
        }
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, "Success", f"Results saved to:\n{file_path}")
            self.log_message(f"Results exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving results:\n{str(e)}")

# ==================== MAIN ENTRY POINT ====================

APP_VERSION = "2.0.0"

VERSION_URL = "https://raw.githubusercontent.com/AradAshkan/DNSPulse-Professional/main/version.json"
GITHUB_URL = "https://github.com/AradAshkan/DNSPulse-Professional"


def check_version():
    try:
        resp = requests.get(VERSION_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        latest = data.get("latest_version", APP_VERSION)
        minimum = data.get("min_allowed_version", APP_VERSION)

        if version.parse(APP_VERSION) < version.parse(minimum):
            return "BLOCK", data

        if version.parse(APP_VERSION) < version.parse(latest):
            return "WARN", data

        return "OK", data

    except:
        return "OK", {}


def open_link(url):
    webbrowser.open(url)


def get_msg(data, key, default):
    """
    Safe message loader from version.json
    """
    if not isinstance(data, dict):
        return default
    return data.get("messages", {}).get(key, default)


def resource_path(path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath("."), path)

if __name__ == "__main__":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dnspulse.app")
    app = QApplication(sys.argv)
    app.setApplicationName("DNSPulse Professional")
    app.setOrganizationName("DNSPulse")
    app.setWindowIcon(QIcon("logo.ico"))

    status, data = check_version()

    if status == "BLOCK":
        msg = get_msg(data, "block", "Version blocked. Please update.")

        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Update Required")
        box.setText(msg)

        btn_github = box.addButton("🌐 Open GitHub", QMessageBox.ButtonRole.ActionRole)
        btn_download = box.addButton("⬇ Download Latest", QMessageBox.ButtonRole.ActionRole)
        btn_exit = box.addButton("Exit", QMessageBox.ButtonRole.RejectRole)

        box.exec()
        clicked = box.clickedButton()

        if clicked == btn_github:
            open_link(GITHUB_URL)

        elif clicked == btn_download:
            open_link(GITHUB_URL + "/releases/latest")

        sys.exit(0)

    elif status == "WARN":
        msg = get_msg(data, "warn", "New version available.")

        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Update Available")
        box.setText(msg)

        btn_github = box.addButton("🌐 GitHub", QMessageBox.ButtonRole.ActionRole)
        btn_download = box.addButton("⬇ Download", QMessageBox.ButtonRole.ActionRole)
        btn_continue = box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)

        box.exec()
        clicked = box.clickedButton()

        if clicked == btn_github:
            open_link(GITHUB_URL)

        elif clicked == btn_download:
            open_link(GITHUB_URL + "/releases/latest")

    window = ModernDNSPulse()
    window.show()

    sys.exit(app.exec())