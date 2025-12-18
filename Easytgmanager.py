import sys
import json
import base64
import os
import time
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit, 
                           QComboBox, QTableWidget, QTableWidgetItem, QFileDialog,
                           QMessageBox, QInputDialog, QHeaderView, QSplitter, QFrame,
                           QGroupBox, QFormLayout, QSpinBox, QCheckBox, QStatusBar,
                           QTreeWidget, QTreeWidgetItem, QDialog, 
                           QVBoxLayout as QVBoxLayoutDialog, QHBoxLayout as QHBoxLayoutDialog,
                           QLabel as QLabelDialog, QLineEdit as QLineEditDialog,
                           QTextEdit as QTextEditDialog, QDialogButtonBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QColor, QPalette, QDesktopServices
import telebot
from cryptography.fernet import Fernet

class BotWorker(QThread):
    """Thread for running a Telegram bot. Handles polling and emits signals back to the GUI."""
    log_signal = pyqtSignal(str, str)  # (level, message)
    status_signal = pyqtSignal(str, str)  # (bot_name, status)
    message_signal = pyqtSignal(str, dict)  # (bot_name, message_data)

    def __init__(self, bot_name, token, admin_id):
        super().__init__()
        self.bot_name = bot_name
        self.token = token
        self.admin_id = admin_id
        self.bot = None
        self.running = False
        self.webhook_url = None
        self.auto_replies = {}
        self.message_filters = {}
        self.commands = {}

    def run(self):
        self.running = True
        try:
            self.bot = telebot.TeleBot(self.token)
            self.bot.start_time = datetime.now()

            # Single dynamic handler that checks commands, auto-replies and filters at runtime
            @self.bot.message_handler(func=lambda message: True)
            def _handle_message(message):
                try:
                    text = message.text or ""
                except Exception:
                    text = ""

                # Filters
                for ft, enabled in (self.message_filters or {}).items():
                    try:
                        if enabled and self.apply_filter(message, ft):
                            self.log_signal.emit("filtered", f"[{self.bot_name}] Message filtered: {ft} from {getattr(message.from_user, 'id', 'unknown')}")
                            return
                    except Exception:
                        continue

                # Commands
                if text.startswith('/'):
                    # Keep the leading slash in the command key (commands are stored like '/start')
                    cmd = text.split()[0]
                    resp = (self.commands or {}).get(cmd)
                    if resp:
                        self.log_signal.emit("command", f"[{self.bot_name}] Command {cmd} from {getattr(message.from_user, 'id', 'unknown')}")
                        try:
                            self.bot.reply_to(message, resp)
                        except Exception as e:
                            self.log_signal.emit("error", f"[{self.bot_name}] Failed to reply to command {cmd}: {e}")
                        return

                # Auto-replies
                for trig, resp in (self.auto_replies or {}).items():
                    try:
                        if trig and trig.lower() in text.lower():
                            self.log_signal.emit("auto_reply", f"[{self.bot_name}] Auto-reply triggered for '{trig}' from {getattr(message.from_user, 'id', 'unknown')}")
                            try:
                                self.bot.reply_to(message, resp)
                            except Exception as e:
                                self.log_signal.emit("error", f"[{self.bot_name}] Failed to send auto-reply for '{trig}': {e}")
                            return
                    except Exception:
                        continue

                # Default: emit message log
                try:
                    self.log_signal.emit("message", f"[{self.bot_name}] From {getattr(message.from_user, 'id', 'unknown')}: {text[:200]}")
                except Exception:
                    pass

            # Webhook handling: if webhook_url is set, configure webhook, otherwise ensure polling
            if self.webhook_url:
                try:
                    self.bot.remove_webhook()
                    self.bot.set_webhook(url=self.webhook_url)
                    self.log_signal.emit("info", f"[{self.bot_name}] Webhook set to {self.webhook_url}")
                except Exception as e:
                    self.log_signal.emit("error", f"[{self.bot_name}] Failed to set webhook: {e}")
            else:
                try:
                    self.bot.remove_webhook()
                except Exception:
                    pass

            self.status_signal.emit(self.bot_name, "Online")
            self.bot.polling(none_stop=True)

        except Exception as e:
            self.log_signal.emit("error", f"[{self.bot_name}] Error: {str(e)}")
            self.status_signal.emit(self.bot_name, "Offline")
        finally:
            self.running = False

    def apply_filter(self, message, filter_type):
        # Implement different filter types
        try:
            text = message.text or ""
        except Exception:
            text = ""

        if filter_type == "spam":
            # Simple spam filter - block messages with too many URLs
            url_count = text.count("http")
            return url_count > 3
        elif filter_type == "bad_words":
            # Bad words filter
            bad_words = ["badword1", "badword2", "badword3"]
            for w in bad_words:
                if w in text.lower():
                    return True
        return False

class DarkDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        
        # Apply dark theme to dialog
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit, QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 3px;
            }
            QLineEdit::placeholder {
                color: #888888;
            }
            QTextEdit::placeholder {
                color: #888888;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #5d5d5d;
            }
        """)

class AddBotDialog(DarkDialog):
    def __init__(self, parent=None):
        super().__init__("Add Bot", parent)
        
        layout = QVBoxLayout(self)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Bot Name")
        layout.addWidget(QLabel("Bot Name:"))
        layout.addWidget(self.name_input)
        
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Bot Token")
        layout.addWidget(QLabel("Bot Token:"))
        layout.addWidget(self.token_input)
        
        self.admin_id_input = QLineEdit()
        self.admin_id_input.setPlaceholderText("Admin User ID")
        layout.addWidget(QLabel("Admin User ID:"))
        layout.addWidget(self.admin_id_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_bot_data(self):
        name = self.name_input.text().strip()
        token = self.token_input.text().strip()
        admin_id_text = self.admin_id_input.text().strip()
        
        # Validation
        if not name:
            QMessageBox.warning(self, "Validation Error", "Bot name cannot be empty!")
            return None
            
        if not token:
            QMessageBox.warning(self, "Validation Error", "Bot token cannot be empty!")
            return None
            
        if not admin_id_text:
            QMessageBox.warning(self, "Validation Error", "Admin User ID cannot be empty!")
            return None
            
        try:
            admin_id = int(admin_id_text)
            return {
                "name": name,
                "token": token,
                "admin_id": admin_id
            }
        except ValueError:
            QMessageBox.warning(self, "Validation Error", "Admin User ID must be a valid number!")
            return None

class CommandDialog(DarkDialog):
    def __init__(self, parent=None):
        super().__init__("Add/Edit Command", parent)
        
        layout = QVBoxLayout(self)
        
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Command (e.g., /start)")
        layout.addWidget(QLabel("Command:"))
        layout.addWidget(self.command_input)
        
        self.response_input = QTextEdit()
        self.response_input.setPlaceholderText("Response text...")
        layout.addWidget(QLabel("Response:"))
        layout.addWidget(self.response_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_command_data(self):
        command = self.command_input.text().strip()
        response = self.response_input.toPlainText().strip()
        
        if not command:
            QMessageBox.warning(self, "Validation Error", "Command cannot be empty!")
            return None
            
        if not response:
            QMessageBox.warning(self, "Validation Error", "Response cannot be empty!")
            return None
            
        return {
            "command": command,
            "response": response
        }

class EditCommandDialog(DarkDialog):
    def __init__(self, parent=None):
        super().__init__("Edit Command", parent)
        
        layout = QVBoxLayout(self)
        
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Command (e.g., /start)")
        layout.addWidget(QLabel("Command:"))
        layout.addWidget(self.command_input)
        
        self.response_input = QTextEdit()
        self.response_input.setPlaceholderText("Response text...")
        layout.addWidget(QLabel("Response:"))
        layout.addWidget(self.response_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def set_command_data(self, command, response):
        self.command_input.setText(command)
        self.response_input.setPlainText(response)
        
    def get_command_data(self):
        command = self.command_input.text().strip()
        response = self.response_input.toPlainText().strip()
        
        if not command:
            QMessageBox.warning(self, "Validation Error", "Command cannot be empty!")
            return None
            
        if not response:
            QMessageBox.warning(self, "Validation Error", "Response cannot be empty!")
            return None
            
        return {
            "command": command,
            "response": response
        }

class DeleteBotDialog(DarkDialog):
    def __init__(self, bot_name, parent=None):
        super().__init__(f"Delete Bot: {bot_name}", parent)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"Are you sure you want to delete bot '{bot_name}'?"))
        layout.addWidget(QLabel("This action cannot be undone."))
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_confirmation(self):
        return self.result() == QDialog.Accepted

class BotManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Bot Manager Pro")
        
        # Set dark theme - comprehensive styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e3e;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 10px;
            }
            QTabBar::tab:selected {
                background-color: #3d3d3d;
            }
            QGroupBox {
                border: 1px solid #3e3e3e;
                border-radius: 5px;
                margin-top: 0.5em;
                font-weight: bold;
                color: #ffffff;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #5d5d5d;
            }
            QLineEdit, QTextEdit, QComboBox, QSpinBox {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 3px;
            }
            QLineEdit::placeholder {
                color: #888888;
            }
            QTextEdit::placeholder {
                color: #888888;
            }
            QComboBox::drop-down {
                background-color: #3d3d3d;
            }
            QTableWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
                gridcolor: #3e3e3e;
            }
            QHeaderView::section {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 5px;
                border: none;
            }
            QTreeWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #5a5a5a;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QStatusBar {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QInputDialog QLabel {
                color: #ffffff;
            }
            QCheckBox {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
            }
            QSpinBox {
                min-width: 60px;
            }
            QHeaderView {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QMessageBox {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMessageBox QLabel {
                color: #ffffff;
            }
            QMessageBox QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
            }
        """)
        
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize data
        self.bots = {}
        self.bot_workers = {}
        self.config_file = "bots.easytg"
        
        # Setup UI
        self.setup_ui()
        
        # Load configuration
        self.load_config()
        
        # Setup timers
        self.setup_timers()
        
    def setup_ui(self):
        # Main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)
        
        # Create tabs
        self.statistics_tab = QWidget()
        self.command_tab = QWidget()
        self.user_tab = QWidget()
        self.backup_tab = QWidget()
        self.settings_tab = QWidget()
        
        # Add tabs
        self.tabs.addTab(self.statistics_tab, "📊 Statistics")
        self.tabs.addTab(self.command_tab, "⚙️ Command Manager")
        self.tabs.addTab(self.user_tab, "👥 User Management")
        self.tabs.addTab(self.backup_tab, "💾 Backup/Restore")
        self.tabs.addTab(self.settings_tab, "⚙️ Settings")
        
        # Setup each tab
        self.setup_statistics_tab()
        self.setup_command_tab()
        self.setup_user_tab()
        self.setup_backup_tab()
        self.setup_settings_tab()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
    def setup_statistics_tab(self):
        layout = QVBoxLayout(self.statistics_tab)
        
        # Bot profiles section
        bot_profiles_group = QGroupBox("Bot Profiles")
        bot_profiles_layout = QVBoxLayout()
        
        # Add bot button
        add_bot_btn = QPushButton("➕ Add New Bot")
        add_bot_btn.clicked.connect(self.add_bot_dialog)
        bot_profiles_layout.addWidget(add_bot_btn)
        
        # Bot profiles table
        self.bot_table = QTableWidget()
        self.bot_table.setColumnCount(6)
        self.bot_table.setHorizontalHeaderLabels(["Name", "Status", "Uptime", "Token", "Admin ID", "Webhook"])
        self.bot_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.bot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.bot_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.bot_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.bot_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.bot_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.bot_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        bot_profiles_layout.addWidget(self.bot_table)
        
        # Bot controls
        bot_controls_layout = QHBoxLayout()
        start_all_btn = QPushButton("▶️ Start All")
        start_all_btn.clicked.connect(self.start_all_bots)
        stop_all_btn = QPushButton("⏹️ Stop All")
        stop_all_btn.clicked.connect(self.stop_all_bots)
        restart_all_btn = QPushButton("🔄 Restart All")
        restart_all_btn.clicked.connect(self.restart_all_bots)
        
        bot_controls_layout.addWidget(start_all_btn)
        bot_controls_layout.addWidget(stop_all_btn)
        bot_controls_layout.addWidget(restart_all_btn)
        bot_profiles_layout.addLayout(bot_controls_layout)
        
        bot_profiles_group.setLayout(bot_profiles_layout)
        layout.addWidget(bot_profiles_group)
        
        # Activity monitor
        activity_group = QGroupBox("Activity Monitor")
        activity_layout = QVBoxLayout()
        
        # Filter and controls
        filter_layout = QHBoxLayout()
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Errors", "Messages", "Commands", "Auto-replies", "Filtered"])
        self.filter_combo.currentTextChanged.connect(self.filter_logs)
        clear_log_btn = QPushButton("🗑️ Clear Log")
        clear_log_btn.clicked.connect(self.clear_logs)
        export_log_btn = QPushButton("💾 Export Log")
        export_log_btn.clicked.connect(self.export_logs)
        
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addWidget(clear_log_btn)
        filter_layout.addWidget(export_log_btn)
        activity_layout.addLayout(filter_layout)
        
        # Log display
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        activity_layout.addWidget(self.log_text)
        
        activity_group.setLayout(activity_layout)
        layout.addWidget(activity_group)
        
        # Recent messages
        messages_group = QGroupBox("Recent Messages")
        messages_layout = QVBoxLayout()
        
        self.messages_table = QTableWidget()
        self.messages_table.setColumnCount(5)
        self.messages_table.setHorizontalHeaderLabels(["Bot", "User", "Message", "Time", "Type"])
        self.messages_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        messages_layout.addWidget(self.messages_table)
        
        messages_group.setLayout(messages_layout)
        layout.addWidget(messages_group)
        
    def setup_command_tab(self):
        layout = QVBoxLayout(self.command_tab)
        
        # Command list
        command_group = QGroupBox("Command Manager")
        command_layout = QVBoxLayout()
        
        # Add command button
        add_cmd_btn = QPushButton("➕ Add Command")
        add_cmd_btn.clicked.connect(self.add_command_dialog)
        command_layout.addWidget(add_cmd_btn)
        
        # Edit command button
        edit_cmd_btn = QPushButton("✏️ Edit Command")
        edit_cmd_btn.clicked.connect(self.edit_command_dialog)
        command_layout.addWidget(edit_cmd_btn)
        
        # Delete command button
        delete_cmd_btn = QPushButton("🗑️ Delete Command")
        delete_cmd_btn.clicked.connect(self.delete_command_dialog)
        command_layout.addWidget(delete_cmd_btn)
        
        # Bot selection for commands
        bot_select_layout = QHBoxLayout()
        bot_select_layout.addWidget(QLabel("Select Bot:"))
        self.bot_select_combo = QComboBox()
        self.bot_select_combo.currentTextChanged.connect(self.update_command_tree)
        bot_select_layout.addWidget(self.bot_select_combo)
        command_layout.addLayout(bot_select_layout)
        
        # Command tree
        self.command_tree = QTreeWidget()
        self.command_tree.setHeaderLabels(["Command", "Response"])
        self.command_tree.setColumnWidth(0, 150)
        self.command_tree.setColumnWidth(1, 400)
        command_layout.addWidget(self.command_tree)
        
        command_group.setLayout(command_layout)
        layout.addWidget(command_group)
        
    def setup_user_tab(self):
        layout = QVBoxLayout(self.user_tab)
        
        # User management
        user_group = QGroupBox("User Management")
        user_layout = QVBoxLayout()
        
        # Add user button
        add_user_btn = QPushButton("➕ Add User")
        add_user_btn.clicked.connect(self.add_user_dialog)
        user_layout.addWidget(add_user_btn)
        
        # User table
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(5)
        self.user_table.setHorizontalHeaderLabels(["ID", "Username", "First Name", "Last Name", "Actions"])
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        user_layout.addWidget(self.user_table)
        
        user_group.setLayout(user_layout)
        layout.addWidget(user_group)
        
    def setup_backup_tab(self):
        layout = QVBoxLayout(self.backup_tab)
        
        # Backup options
        backup_group = QGroupBox("Backup/Restore")
        backup_layout = QFormLayout()
        
        backup_now_btn = QPushButton("💾 Backup Now")
        backup_now_btn.clicked.connect(self.backup_now)
        restore_btn = QPushButton("📁 Restore")
        restore_btn.clicked.connect(self.restore_config)
        schedule_backup_btn = QPushButton("⏰ Schedule Backup")
        schedule_backup_btn.clicked.connect(self.schedule_backup)
        
        backup_layout.addRow("Backup Options:", None)
        backup_layout.addRow(backup_now_btn, None)
        backup_layout.addRow(restore_btn, None)
        backup_layout.addRow(schedule_backup_btn, None)
        
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)
        
    def setup_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
        # General settings
        settings_group = QGroupBox("General Settings")
        settings_layout = QFormLayout()
        
        self.auto_start_checkbox = QCheckBox()
        self.auto_start_checkbox.setChecked(True)
        settings_layout.addRow("Auto-start on boot:", self.auto_start_checkbox)
        
        self.log_level_spin = QSpinBox()
        self.log_level_spin.setRange(1, 5)
        self.log_level_spin.setValue(3)
        settings_layout.addRow("Log level:", self.log_level_spin)
        
        self.update_interval_spin = QSpinBox()
        self.update_interval_spin.setRange(1, 60)
        self.update_interval_spin.setValue(5)
        settings_layout.addRow("Update interval (seconds):", self.update_interval_spin)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Webhook settings
        webhook_group = QGroupBox("Webhook Settings")
        webhook_layout = QFormLayout()
        
        self.webhook_url_input = QLineEdit()
        self.webhook_url_input.setPlaceholderText("https://your-domain.com/webhook")
        webhook_layout.addRow("Webhook URL:", self.webhook_url_input)
        
        set_webhook_btn = QPushButton("Set Webhook")
        set_webhook_btn.clicked.connect(self.set_webhook)
        webhook_layout.addRow(set_webhook_btn)
        
        remove_webhook_btn = QPushButton("Remove Webhook")
        remove_webhook_btn.clicked.connect(self.remove_webhook)
        webhook_layout.addRow(remove_webhook_btn)
        
        webhook_group.setLayout(webhook_layout)
        layout.addWidget(webhook_group)
        
        # Message filtering
        filter_group = QGroupBox("Message Filtering")
        filter_layout = QFormLayout()
        
        self.spam_filter_checkbox = QCheckBox()
        filter_layout.addRow("Enable Spam Filter:", self.spam_filter_checkbox)
        
        self.bad_words_filter_checkbox = QCheckBox()
        filter_layout.addRow("Enable Bad Words Filter:", self.bad_words_filter_checkbox)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Auto-reply settings
        auto_reply_group = QGroupBox("Auto-Reply Settings")
        auto_reply_layout = QVBoxLayout()
        
        add_auto_reply_btn = QPushButton("➕ Add Auto-Reply")
        add_auto_reply_btn.clicked.connect(self.add_auto_reply_dialog)
        auto_reply_layout.addWidget(add_auto_reply_btn)
        
        self.auto_reply_list = QTreeWidget()
        self.auto_reply_list.setHeaderLabels(["Trigger", "Response"])
        auto_reply_layout.addWidget(self.auto_reply_list)
        
        auto_reply_group.setLayout(auto_reply_layout)
        layout.addWidget(auto_reply_group)
        
    def setup_timers(self):
        # Timer for updating UI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(1000)  # Update every second
        
        # Timer for checking bot status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_bot_status)
        self.status_timer.start(5000)  # Check every 5 seconds
        
    def add_bot_dialog(self):
        dialog = AddBotDialog(self)
        if dialog.exec_():
            bot_data = dialog.get_bot_data()
            if bot_data:
                self.add_bot(bot_data["name"], bot_data["token"], bot_data["admin_id"])
            else:
                # Show error message if validation failed
                QMessageBox.warning(self, "Bot Addition Failed", "Please fill in all fields correctly and try again.")
                
    def add_bot(self, name, token, admin_id):
        # Check if bot with same name already exists
        if name in self.bots:
            QMessageBox.warning(self, "Bot Exists", f"A bot with name '{name}' already exists!")
            return
            
        # Add to config
        self.bots[name] = {
            "token": token,
            "admin_id": admin_id,
            "status": "Offline",
            "start_time": None,
            "uptime": 0,
            "webhook_url": None,
            "auto_replies": {},
            "message_filters": {
                "spam": False,
                "bad_words": False
            },
            "commands": {}
        }
        
        # Start bot worker
        try:
            worker = BotWorker(name, token, admin_id)
            # Restore any runtime settings into the worker
            worker.commands = self.bots[name].get("commands", {})
            worker.auto_replies = self.bots[name].get("auto_replies", {})
            worker.message_filters = self.bots[name].get("message_filters", {})
            worker.webhook_url = self.bots[name].get("webhook_url")
            worker.log_signal.connect(self.add_log)
            worker.status_signal.connect(self.update_bot_status)
            worker.message_signal.connect(self.add_message)
            worker.start()
            self.bot_workers[name] = worker
            
            # Save config
            self.save_config()
            self.update_ui()
            
            QMessageBox.information(self, "Success", f"Bot '{name}' added successfully!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start bot: {str(e)}")
            # Remove bot from config if worker creation failed
            del self.bots[name]
            
    def add_command_dialog(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        dialog = CommandDialog(self)
        if dialog.exec_():
            command_data = dialog.get_command_data()
            if command_data:
                # Check if command already exists
                if command_data["command"] in self.bots[current_bot]["commands"]:
                    QMessageBox.warning(self, "Command Exists", f"Command '{command_data['command']}' already exists for this bot!")
                    return
                    
                self.bots[current_bot]["commands"][command_data["command"]] = command_data["response"]
                # If worker is running for this bot, update its commands mapping so it responds dynamically
                if current_bot in self.bot_workers:
                    try:
                        self.bot_workers[current_bot].commands = self.bots[current_bot]["commands"]
                    except Exception:
                        pass
                self.save_config()
                self.update_command_tree()
                self.add_log("info", f"Command /{command_data['command']} added to {current_bot}")
                QMessageBox.information(self, "Success", "Command added successfully!")
            else:
                QMessageBox.warning(self, "Validation Error", "Please fill in all fields correctly.")
                
    def edit_command_dialog(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        selected_items = self.command_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a command to edit")
            return
            
        command = selected_items[0].text(0)
        response = selected_items[0].text(1)
        
        dialog = EditCommandDialog(self)
        dialog.set_command_data(command, response)
        
        if dialog.exec_():
            command_data = dialog.get_command_data()
            if command_data:
                self.bots[current_bot]["commands"][command_data["command"]] = command_data["response"]
                self.save_config()
                self.update_command_tree()
                self.add_log("info", f"Command /{command_data['command']} updated for {current_bot}")
                QMessageBox.information(self, "Success", "Command updated successfully!")
            else:
                QMessageBox.warning(self, "Validation Error", "Please fill in all fields correctly.")
                
    def delete_command_dialog(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        selected_items = self.command_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a command to delete")
            return
            
        command = selected_items[0].text(0)
        
        reply = QMessageBox.question(self, "Delete Command", 
                                  f"Are you sure you want to delete command '{command}'?",
                                  QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            if command in self.bots[current_bot]["commands"]:
                del self.bots[current_bot]["commands"][command]
                self.save_config()
                self.update_command_tree()
                self.add_log("info", f"Command /{command} deleted from {current_bot}")
                QMessageBox.information(self, "Success", "Command deleted successfully!")
                
    def update_command_tree(self):
        self.command_tree.clear()
        current_bot = self.bot_select_combo.currentText()
        if current_bot in self.bots:
            for command, response in self.bots[current_bot]["commands"].items():
                item = QTreeWidgetItem(self.command_tree)
                item.setText(0, command)
                item.setText(1, response)
                
    def add_auto_reply_dialog(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        trigger, ok = QInputDialog.getText(self, "Add Auto-Reply", "Trigger text:")
        if ok and trigger:
            response, ok = QInputDialog.getText(self, "Add Auto-Reply", "Response:")
            if ok and response:
                self.bots[current_bot]["auto_replies"][trigger] = response
                self.save_config()
                # Update running worker if present
                if current_bot in self.bot_workers:
                    try:
                        self.bot_workers[current_bot].auto_replies = self.bots[current_bot]["auto_replies"]
                    except Exception:
                        pass
                self.add_log("info", f"Auto-reply added for '{trigger}' in {current_bot}")
                QMessageBox.information(self, "Success", "Auto-reply added successfully!")
                
    def set_webhook(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        url = self.webhook_url_input.text()
        if url:
            self.bots[current_bot]["webhook_url"] = url
            self.save_config()
            self.add_log("info", f"Webhook URL set for {current_bot}")
            QMessageBox.information(self, "Success", "Webhook URL set successfully!")
            # Update running worker if present
            if current_bot in self.bot_workers:
                try:
                    w = self.bot_workers[current_bot]
                    w.webhook_url = url
                    if w.bot is not None:
                        try:
                            w.bot.remove_webhook()
                            w.bot.set_webhook(url=url)
                        except Exception as e:
                            self.add_log("error", f"Failed to set webhook for {current_bot}: {e}")
                except Exception:
                    pass
        else:
            QMessageBox.warning(self, "Validation Error", "Webhook URL cannot be empty!")
            
    def remove_webhook(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        self.bots[current_bot]["webhook_url"] = None
        self.save_config()
        self.add_log("info", f"Webhook removed for {current_bot}")
        QMessageBox.information(self, "Success", "Webhook removed successfully!")
        # Update running worker if present
        if current_bot in self.bot_workers:
            try:
                w = self.bot_workers[current_bot]
                w.webhook_url = None
                if w.bot is not None:
                    try:
                        w.bot.remove_webhook()
                    except Exception as e:
                        self.add_log("error", f"Failed to remove webhook for {current_bot}: {e}")
            except Exception:
                pass
        
    def add_log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {level.upper()}: {message}")
        
        # Add to messages table
        row = self.messages_table.rowCount()
        self.messages_table.insertRow(row)
        self.messages_table.setItem(row, 0, QTableWidgetItem("Bot Name"))  # Will be updated
        self.messages_table.setItem(row, 1, QTableWidgetItem("User ID"))    # Will be updated
        self.messages_table.setItem(row, 2, QTableWidgetItem(message[:50]))
        self.messages_table.setItem(row, 3, QTableWidgetItem(timestamp))
        self.messages_table.setItem(row, 4, QTableWidgetItem(level))
        
    def add_message(self, bot_name, message_data):
        # This would be called when a message is received
        pass
        
    def update_bot_status(self, bot_name, status):
        if bot_name in self.bots:
            self.bots[bot_name]["status"] = status
            if status == "Online" and bot_name not in self.bot_workers:
                # Start the worker if it's not already running
                bot_data = self.bots[bot_name]
                worker = BotWorker(bot_name, bot_data["token"], bot_data["admin_id"])
                worker.log_signal.connect(self.add_log)
                worker.status_signal.connect(self.update_bot_status)
                worker.message_signal.connect(self.add_message)
                worker.commands = bot_data["commands"]
                worker.auto_replies = bot_data["auto_replies"]
                worker.message_filters = bot_data["message_filters"]
                worker.start()
                self.bot_workers[bot_name] = worker
                
            if status == "Online":
                self.bots[bot_name]["start_time"] = datetime.now()
            self.update_ui()
            
    def update_ui(self):
        # Update bot table and selection combo
        self.bot_table.setRowCount(len(self.bots))
        self.bot_select_combo.clear()

        for i, (name, bot) in enumerate(self.bots.items()):
            self.bot_table.setItem(i, 0, QTableWidgetItem(name))
            self.bot_table.setItem(i, 1, QTableWidgetItem(bot.get("status", "Offline")))

            # Calculate uptime
            start_time = bot.get("start_time")
            if bot.get("status") == "Online" and start_time:
                try:
                    uptime = datetime.now() - start_time
                    self.bot_table.setItem(i, 2, QTableWidgetItem(str(uptime).split('.')[0]))
                except Exception:
                    self.bot_table.setItem(i, 2, QTableWidgetItem("0:00:00"))
            else:
                self.bot_table.setItem(i, 2, QTableWidgetItem("0:00:00"))

            # Mask token
            token = bot.get("token", "")
            masked_token = token[:4] + "****" + token[-4:] if len(token) >= 8 else token
            self.bot_table.setItem(i, 3, QTableWidgetItem(masked_token))
            self.bot_table.setItem(i, 4, QTableWidgetItem(str(bot.get("admin_id", ""))))

            # Webhook status
            webhook_status = bot.get("webhook_url") or "None"
            self.bot_table.setItem(i, 5, QTableWidgetItem(webhook_status))

            # Add to bot selection combo
            self.bot_select_combo.addItem(name)
            
    def start_all_bots(self):
        for name, worker in self.bot_workers.items():
            if not worker.running:
                worker.start()
                
    def stop_all_bots(self):
        for worker in self.bot_workers.values():
            if worker.running:
                worker.terminate()
                
    def restart_all_bots(self):
        self.stop_all_bots()
        time.sleep(2)
        self.start_all_bots()
        
    def check_bot_status(self):
        for name, worker in self.bot_workers.items():
            if worker.running:
                self.bots[name]["status"] = "Online"
            else:
                self.bots[name]["status"] = "Offline"
        self.update_ui()
        
    def filter_logs(self, filter_type):
        # Implementation for filtering logs
        pass
        
    def clear_logs(self):
        self.log_text.clear()
        
    def export_logs(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt)")
        if filename:
            with open(filename, 'w') as f:
                f.write(self.log_text.toPlainText())
                
    def add_user_dialog(self):
        # Implementation for adding users
        pass
        
    def backup_now(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Backup Configuration", "", "EasyTG Files (*.easytg)")
        if filename:
            self.save_config(filename)
            QMessageBox.information(self, "Backup", "Configuration backed up successfully!")
            
    def restore_config(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Restore Configuration", "", "EasyTG Files (*.easytg)")
        if filename:
            self.load_config(filename)
            self.update_ui()
            QMessageBox.information(self, "Restore", "Configuration restored successfully!")
            
    def schedule_backup(self):
        # Implementation for scheduled backups
        pass
        
    def save_config(self, filename=None):
        if not filename:
            filename = self.config_file
            
        # Convert datetime objects to strings for JSON serialization
        bots_for_save = {}
        for name, bot_data in self.bots.items():
            bots_for_save[name] = bot_data.copy()
            if bot_data["start_time"] is not None:
                bots_for_save[name]["start_time"] = bot_data["start_time"].isoformat()
        
        # Encrypt configuration
        config_data = {
            "version": "1.0",
            "bots": bots_for_save,
            "settings": {
                "auto_start": self.auto_start_checkbox.isChecked(),
                "log_level": self.log_level_spin.value(),
                "update_interval": self.update_interval_spin.value()
            }
        }
        
        # For simplicity, saving as JSON (add encryption for production)
        with open(filename, 'w') as f:
            json.dump(config_data, f, indent=2)
            
    def load_config(self, filename=None):
        if not filename:
            filename = self.config_file
            
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    config_data = json.load(f)
            except json.JSONDecodeError:
                # Backup the corrupted config and continue with defaults
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    corrupt_name = f"{filename}.corrupt.{ts}"
                    os.replace(filename, corrupt_name)
                    QMessageBox.warning(self, "Configuration Error",
                                        f"Configuration file was corrupt and has been moved to:\n{corrupt_name}\nA new default configuration will be created.")
                except Exception:
                    # If backup fails, still warn and proceed
                    QMessageBox.warning(self, "Configuration Error",
                                        "Configuration file is corrupt and could not be backed up. A new default configuration will be used.")
                # Reset to empty/default config
                self.bots = {}
                return
            except Exception as e:
                QMessageBox.warning(self, "Configuration Error", f"Failed to read configuration: {e}\nUsing defaults.")
                self.bots = {}
                return

            bots_data = config_data.get("bots", {})
            settings = config_data.get("settings", {})

            # Convert string timestamps back to datetime objects
            self.bots = {}
            for name, bot_data in bots_data.items():
                self.bots[name] = bot_data.copy()
                if bot_data.get("start_time") is not None:
                    try:
                        self.bots[name]["start_time"] = datetime.fromisoformat(bot_data["start_time"])
                    except (ValueError, TypeError):
                        self.bots[name]["start_time"] = None

            if "auto_start" in settings and hasattr(self, 'auto_start_checkbox'):
                self.auto_start_checkbox.setChecked(settings["auto_start"])
            if "log_level" in settings and hasattr(self, 'log_level_spin'):
                self.log_level_spin.setValue(settings["log_level"])
            if "update_interval" in settings and hasattr(self, 'update_interval_spin'):
                self.update_interval_spin.setValue(settings["update_interval"])

            # Recreate BotWorker instances for saved bots and optionally auto-start them
            for name, bot_data in self.bots.items():
                try:
                    worker = BotWorker(name, bot_data.get("token"), bot_data.get("admin_id"))
                    # Restore runtime settings
                    worker.auto_replies = bot_data.get("auto_replies", {}) or {}
                    worker.message_filters = bot_data.get("message_filters", {}) or {}
                    worker.commands = bot_data.get("commands", {}) or {}
                    worker.webhook_url = bot_data.get("webhook_url")
                    worker.log_signal.connect(self.add_log)
                    worker.status_signal.connect(self.update_bot_status)
                    worker.message_signal.connect(self.add_message)
                    self.bot_workers[name] = worker

                    # Auto-start if setting enabled or the bot was previously Online
                    should_start = False
                    if hasattr(self, 'auto_start_checkbox') and self.auto_start_checkbox.isChecked():
                        should_start = True
                    if bot_data.get("status") == "Online":
                        should_start = True

                    if should_start:
                        try:
                            worker.start()
                        except RuntimeError:
                            # Thread already started or unable to start; log and continue
                            self.add_log("error", f"Failed to start worker for {name}")
                except Exception as e:
                    self.add_log("error", f"Failed to recreate worker for {name}: {e}")
                
    def delete_bot_dialog(self):
        current_bot = self.bot_select_combo.currentText()
        if not current_bot or current_bot not in self.bots:
            QMessageBox.warning(self, "Warning", "Please select a bot first")
            return
            
        dialog = DeleteBotDialog(current_bot, self)
        if dialog.get_confirmation():
            self.delete_bot(current_bot)
            
    def delete_bot(self, bot_name):
        if bot_name in self.bots:
            # Stop the bot worker
            if bot_name in self.bot_workers:
                worker = self.bot_workers[bot_name]
                if worker.running:
                    worker.terminate()
                del self.bot_workers[bot_name]
                
            # Remove from config
            del self.bots[bot_name]
            
            # Save config
            self.save_config()
            self.update_ui()
            
            QMessageBox.information(self, "Success", f"Bot '{bot_name}' deleted successfully!")
            
    def closeEvent(self, event):
        # Stop all bots before closing
        self.stop_all_bots()
        self.save_config()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BotManagerApp()
    window.show()
    sys.exit(app.exec_())