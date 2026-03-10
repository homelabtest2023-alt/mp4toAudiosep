import sys
import os
import shutil
import asyncio
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QProgressBar,
                               QFileDialog, QMessageBox, QGroupBox, QFormLayout,
                               QInputDialog, QDialog, QDialogButtonBox, QSpinBox,
                               QTabWidget)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# Add the project root to the path so 'core' can be found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.audio_processor import AudioProcessor
from core.ssh_manager import SSHManager

APP_NAME = "AudioSepClient"
ORG_NAME = "AudioSepOrg"


class SSHSettingsDialog(QDialog):
    """Dialog to configure SSH connection settings."""
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SSH / GPU Server Settings")
        self.setMinimumWidth(400)
        self.settings = settings

        layout = QVBoxLayout(self)

        # Tab widget for organizing settings
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- Tab 1: SSH Connection ---
        ssh_tab = QWidget()
        ssh_layout = QFormLayout(ssh_tab)

        self.txt_host = QLineEdit(self.settings.value("ssh_host", ""))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(int(self.settings.value("ssh_port", 22)))
        self.txt_user = QLineEdit(self.settings.value("ssh_user", ""))
        self.txt_pass = QLineEdit(self.settings.value("ssh_pass", ""))
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key = QLineEdit(self.settings.value("ssh_key", ""))

        btn_browse_key = QPushButton("Browse...")
        btn_browse_key.clicked.connect(self._browse_key)
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.txt_key)
        key_layout.addWidget(btn_browse_key)
        
        # Add hint label below Key path
        lbl_key_hint = QLabel("<span style='color:gray; font-size:10px;'>If using password, leave Key Path empty.</span>")
        
        ssh_layout.addRow("Host IP:", self.txt_host)
        ssh_layout.addRow("SSH Port:", self.spin_port)
        ssh_layout.addRow("Username:", self.txt_user)
        ssh_layout.addRow("Password:", self.txt_pass)
        ssh_layout.addRow("Key Path:", key_layout)
        ssh_layout.addRow("", lbl_key_hint)
        tabs.addTab(ssh_tab, "SSH Connection")

        # --- Tab 2: AudioSep API ---
        api_tab = QWidget()
        api_layout = QFormLayout(api_tab)

        self.txt_script = QLineEdit(self.settings.value("ssh_script", "/home/ubuntu/audiosep/lan_server.py"))
        self.txt_python = QLineEdit(self.settings.value("ssh_python", "python3"))
        self.spin_api_port = QSpinBox()
        self.spin_api_port.setRange(1, 65535)
        self.spin_api_port.setValue(int(self.settings.value("api_port", 8001)))

        api_layout.addRow("lan_server.py Path:", self.txt_script)
        api_layout.addRow("Python Command:", self.txt_python)
        api_layout.addRow("API Port:", self.spin_api_port)
        tabs.addTab(api_tab, "AudioSep API")

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select SSH Private Key")
        if path:
            self.txt_key.setText(path)

    def accept(self):
        # Save settings when OK is clicked
        self.settings.setValue("ssh_host", self.txt_host.text().strip())
        self.settings.setValue("ssh_port", self.spin_port.value())
        self.settings.setValue("ssh_user", self.txt_user.text().strip())
        # NOTE: QSettings stores this in the Windows Registry (HKCU) in plaintext.
        # For production use, replace with the `keyring` library for secure storage.
        self.settings.setValue("ssh_pass", self.txt_pass.text())
        self.settings.setValue("ssh_key", self.txt_key.text().strip())
        
        self.settings.setValue("ssh_script", self.txt_script.text().strip())
        self.settings.setValue("ssh_python", self.txt_python.text().strip())
        self.settings.setValue("api_port", self.spin_api_port.value())
        super().accept()


class WorkerThread(QThread):
    """Runs the audio pipeline (FFmpeg + HTTP post) in a background thread."""
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, mp4_path: str, query: str, server_url: str):
        super().__init__()
        self.mp4_path = mp4_path
        self.query = query
        self.server_url = server_url

    def run(self):
        processor = AudioProcessor(self.server_url)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_path = loop.run_until_complete(
                processor.process_audio(
                    self.mp4_path, self.query,
                    progress_callback=lambda msg: self.progress.emit(msg)
                )
            )
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class SSHWorkerThread(QThread):
    """Background thread for SSH operations so the GUI doesn't freeze."""
    result = Signal(str)
    error = Signal(str)

    def __init__(self, action: str, ssh_manager: SSHManager):
        super().__init__()
        self.action = action
        self.ssh = ssh_manager

    def run(self):
        try:
            if self.action == "connect":
                msg = self.ssh.connect()
                self.result.emit(msg)
            elif self.action == "start":
                msg = self.ssh.start_server()
                self.result.emit(msg)
            elif self.action == "stop":
                msg = self.ssh.stop_server()
                self.result.emit(msg)
            elif self.action == "check":
                msg = self.ssh.check_status()
                self.result.emit(msg)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioSep Desktop Client")
        self.resize(750, 550)

        self.mp4_path = None
        self.result_wav_path = None
        self.worker = None
        self.ssh_worker = None
        
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.ssh_manager = SSHManager()

        # Audio player setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)

        self._init_ui()
        self._load_ssh_settings()

    def _init_ui(self):
        # Menu Bar
        menu_bar = self.menuBar()
        
        # AudioSep API Menu
        api_menu = menu_bar.addMenu("AudioSep API (HTTP)")
        api_action = api_menu.addAction("Set Custom HTTP URL")
        api_action.triggered.connect(self._show_http_settings)
        
        # Remote Server Menu
        server_menu = menu_bar.addMenu("Remote Server (SSH)")
        ssh_settings_action = server_menu.addAction("SSH Settings...")
        ssh_settings_action.triggered.connect(self._show_ssh_settings)
        server_menu.addSeparator()
        
        self.action_ssh_connect = server_menu.addAction("Test SSH Connection")
        self.action_ssh_connect.triggered.connect(lambda: self._run_ssh_task("connect"))
        
        self.action_api_start = server_menu.addAction("🚀 Start AudioSep API")
        self.action_api_start.triggered.connect(lambda: self._run_ssh_task("start"))
        
        self.action_api_stop = server_menu.addAction("🛑 Stop AudioSep API")
        self.action_api_stop.triggered.connect(lambda: self._run_ssh_task("stop"))
        
        self.action_api_check = server_menu.addAction("🔍 Check API Status")
        self.action_api_check.triggered.connect(lambda: self._run_ssh_task("check"))

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 10, 20, 20)
        main_layout.setSpacing(15)
        
        # Server Status Bar
        self.lbl_server_status = QLabel("Server: Unknown")
        self.lbl_server_status.setStyleSheet("color: #aaa; font-weight: bold;")
        self.lbl_server_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.lbl_server_status)

        # --- 1. Upload Section ---
        upload_group = QGroupBox("1. Video Input")
        upload_layout = QVBoxLayout()
        self.lbl_file = QLabel("No MP4 file selected.")
        self.lbl_file.setAlignment(Qt.AlignCenter)
        self.lbl_file.setMinimumHeight(60)
        self.lbl_file.setStyleSheet("color: #888; border: 2px dashed #555; padding: 10px; border-radius: 5px;")
        btn_browse = QPushButton("Browse MP4 File...")
        btn_browse.clicked.connect(self._browse_file)
        upload_layout.addWidget(self.lbl_file)
        upload_layout.addWidget(btn_browse)
        upload_group.setLayout(upload_layout)
        main_layout.addWidget(upload_group)

        # --- 2. Query Section ---
        prompt_group = QGroupBox("2. Target Sound Description")
        prompt_layout = QFormLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("e.g., 'dog barking', 'speech', 'keyboard typing'")
        self.txt_query.setMinimumHeight(32)
        prompt_layout.addRow("Query:", self.txt_query)
        prompt_group.setLayout(prompt_layout)
        main_layout.addWidget(prompt_group)

        # --- 3. Execute Button ---
        self.btn_extract = QPushButton("⚡  Extract & Separate")
        self.btn_extract.setMinimumHeight(50)
        self.btn_extract.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_extract.clicked.connect(self._start_processing)
        main_layout.addWidget(self.btn_extract)

        self.lbl_status = QLabel("Ready.")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #aaa;")
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- 4. Result Section ---
        self.result_group = QGroupBox("3. Result")
        result_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶  Play Audio")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_playback)
        self.btn_save = QPushButton("💾  Save WAV As...")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_result)
        result_layout.addWidget(self.btn_play)
        result_layout.addWidget(self.btn_save)
        self.result_group.setLayout(result_layout)
        main_layout.addWidget(self.result_group)

    # ---------------------------------------------------------------
    # SSH Management
    # ---------------------------------------------------------------
    def _load_ssh_settings(self):
        """Load settings from QSettings into the SSHManager instance."""
        self.ssh_manager.host = self.settings.value("ssh_host", "")
        self.ssh_manager.port = int(self.settings.value("ssh_port", 22))
        self.ssh_manager.username = self.settings.value("ssh_user", "")
        self.ssh_manager.password = self.settings.value("ssh_pass", "")
        self.ssh_manager.key_path = self.settings.value("ssh_key", "")
        
        self.ssh_manager.server_script_path = self.settings.value("ssh_script", "/home/ubuntu/audiosep/lan_server.py")
        self.ssh_manager.python_path = self.settings.value("ssh_python", "python3")
        self.ssh_manager.api_port = int(self.settings.value("api_port", 8001))
        
        if self.ssh_manager.host:
            self.lbl_server_status.setText(f"Server: {self.ssh_manager.host} (Offline/Unknown)")

    def _show_ssh_settings(self):
        dialog = SSHSettingsDialog(self.settings, self)
        if dialog.exec():
            # User clicked OK, reload settings
            self._load_ssh_settings()
            
    def _show_http_settings(self):
        # Allow overriding the HTTP URL directly if they don't want to use SSH
        current_url = self.settings.value("server_url", f"http://{self.ssh_manager.host}:{self.ssh_manager.api_port}/separate")
        url, ok = QInputDialog.getText(
            self, "Manual HTTP Override",
            "Normally, the HTTP URL is generated from the SSH settings.\nIf you want to override it, enter it below:",
            QLineEdit.Normal, current_url
        )
        if ok and url.strip():
            self.settings.setValue("server_url", url.strip())

    def _get_api_url(self) -> str:
        """Construct the URL to hit for separation based on settings."""
        # 1. Check if user manually overrode the URL
        if self.settings.contains("server_url"):
            manual_override = self.settings.value("server_url")
            # If they just entered an IP without the path, we can try to fix it, but let's trust them
            if manual_override and "://" in manual_override:
                return manual_override
                
        # 2. Derive from SSH settings
        host = self.ssh_manager.host
        if not host:
            host = "localhost" # Fallback
        
        port = self.ssh_manager.api_port
        return f"http://{host}:{port}/separate"

    def _run_ssh_task(self, action: str):
        if not self.ssh_manager.host:
            QMessageBox.warning(self, "No Host", "Please configure SSH settings first.")
            self._show_ssh_settings()
            return

        # FIX: Guard against Race Condition — prevent launching a second SSH task
        # while a previous one is still running (they share the same SSHManager client)
        if self.ssh_worker and self.ssh_worker.isRunning():
            QMessageBox.information(self, "Busy", "An SSH operation is already in progress. Please wait.")
            return

        self.btn_extract.setEnabled(False)
        self.lbl_status.setText(f"SSH: '{action}' running...")

        self.ssh_worker = SSHWorkerThread(action, self.ssh_manager)
        self.ssh_worker.result.connect(self._on_ssh_success)
        self.ssh_worker.error.connect(self._on_ssh_error)
        self.ssh_worker.start()

    def _on_ssh_success(self, msg: str):
        self.btn_extract.setEnabled(True)
        self.lbl_status.setText("Ready.")
        QMessageBox.information(self, "SSH Success", msg)
        
        if "🟢" in msg or "started successfully" in msg:
            self.lbl_server_status.setText(f"Server: {self.ssh_manager.host}:{self.ssh_manager.api_port} 🟢 ONLINE")
            self.lbl_server_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        elif "🔴" in msg or "stopped successfully" in msg:
            self.lbl_server_status.setText(f"Server: {self.ssh_manager.host}:{self.ssh_manager.api_port} 🔴 OFFLINE")
            self.lbl_server_status.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _on_ssh_error(self, err_msg: str):
        self.btn_extract.setEnabled(True)
        self.lbl_status.setText("SSH Error.")
        self.lbl_server_status.setText(f"Server: {self.ssh_manager.host} (SSH Error)")
        self.lbl_server_status.setStyleSheet("color: #e67e22; font-weight: bold;")
        QMessageBox.critical(self, "SSH Failed", err_msg)

    # ---------------------------------------------------------------
    # Processing Pipeline
    # ---------------------------------------------------------------
    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select MP4 File", "", "Video Files (*.mp4);;All Files (*)")
        if file_path:
            self.mp4_path = file_path
            fname = os.path.basename(file_path)
            fsize = os.path.getsize(file_path) / (1024 * 1024)
            self.lbl_file.setText(f"✔  {fname}  ({fsize:.1f} MB)")
            self.lbl_file.setStyleSheet("color: #2ecc71; border: 2px solid #2ecc71; padding: 10px; border-radius: 5px;")

    def _start_processing(self):
        if not self.mp4_path:
            QMessageBox.warning(self, "Missing File", "Please select an MP4 file.")
            return

        query = self.txt_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Missing Query", "Please enter a description.")
            return
            
        api_url = self._get_api_url()

        self.btn_extract.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._update_status(f"Starting... (using {api_url})")

        self.worker = WorkerThread(self.mp4_path, query, api_url)
        self.worker.progress.connect(self._update_status)
        self.worker.finished.connect(self._processing_finished)
        self.worker.error.connect(self._processing_error)
        self.worker.start()

    def _update_status(self, msg: str):
        self.lbl_status.setText(msg)

    def _processing_finished(self, result_path: str):
        self.btn_extract.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._update_status("✅  Separation complete!")

        self.result_wav_path = result_path
        self.btn_play.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_play.setText("▶  Play Audio")
        self.player.setSource(QUrl.fromLocalFile(self.result_wav_path))

    def _processing_error(self, err_msg: str):
        self.btn_extract.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._update_status("❌  Processing failed.")
        QMessageBox.critical(self, "Processing Failed", err_msg)

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.Playing:
            self.player.pause()
            self.btn_play.setText("▶  Play Audio")
        else:
            self.player.play()
            self.btn_play.setText("⏸  Pause Audio")

    def _save_result(self):
        if not self.result_wav_path: return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Separated WAV", "separated_audio.wav", "Audio Files (*.wav)")
        if save_path:
            try:
                shutil.copyfile(self.result_wav_path, save_path)
                QMessageBox.information(self, "Saved", f"File saved to:\n{save_path}")
            except OSError as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{str(e)}")

    def closeEvent(self, event):
        self.player.stop()
        if self.worker and self.worker.isRunning():
            self.worker.quit()
        if self.ssh_worker and self.ssh_worker.isRunning():
            self.ssh_worker.quit()
        # Ensure SSH is closed nicely
        if self.ssh_manager:
            self.ssh_manager.disconnect()
        event.accept()
