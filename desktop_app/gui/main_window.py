import sys
import os
import shutil
import asyncio
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QProgressBar,
                               QFileDialog, QMessageBox, QGroupBox, QFormLayout,
                               QInputDialog)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# Add the project root to the path so 'core' can be found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.audio_processor import AudioProcessor

APP_NAME = "AudioSepClient"
ORG_NAME = "AudioSepOrg"


class WorkerThread(QThread):
    """
    Runs the audio processing pipeline in a background thread so the UI
    remains responsive during FFmpeg extraction and the LAN Server call.
    """
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

        # Create a new asyncio event loop for this thread (required by httpx)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result_path = loop.run_until_complete(
                processor.process_audio(
                    self.mp4_path,
                    self.query,
                    progress_callback=lambda msg: self.progress.emit(msg)
                )
            )
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioSep Desktop Client")
        self.resize(700, 520)

        self.mp4_path = None
        self.result_wav_path = None
        self.worker = None

        # FIX: Load server URL from persistent settings (survives app restart)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.server_url = self.settings.value("server_url", "http://localhost:8001/separate")

        # Audio player setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)
        self.player.setAudioOutput(self.audio_output)

        self._init_ui()

    def _init_ui(self):
        # Menu Bar
        menu_bar = self.menuBar()
        settings_menu = menu_bar.addMenu("Settings")
        server_action = settings_menu.addAction("Set LAN Server IP / URL")
        server_action.triggered.connect(self._show_server_settings)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- 1. Upload Section ---
        upload_group = QGroupBox("1. Video Input")
        upload_layout = QVBoxLayout()

        self.lbl_file = QLabel("No MP4 file selected.")
        self.lbl_file.setAlignment(Qt.AlignCenter)
        self.lbl_file.setMinimumHeight(60)
        self.lbl_file.setStyleSheet(
            "color: #888; border: 2px dashed #555; padding: 10px; border-radius: 5px;"
        )

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

        # Status and progress bar
        self.lbl_status = QLabel("Ready. Select an MP4 file and enter a query to begin.")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #aaa; font-size: 12px;")
        main_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate spinner mode
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
    # File Selection
    # ---------------------------------------------------------------
    def _browse_file(self):
        # FIX: Removed deprecated QFileDialog.Options() argument
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select MP4 File", "", "Video Files (*.mp4);;All Files (*)"
        )
        if file_path:
            self.mp4_path = file_path
            fname = os.path.basename(file_path)
            fsize = os.path.getsize(file_path) / (1024 * 1024)
            self.lbl_file.setText(f"✔  {fname}  ({fsize:.1f} MB)")
            self.lbl_file.setStyleSheet(
                "color: #2ecc71; border: 2px solid #2ecc71; padding: 10px; border-radius: 5px;"
            )

    # ---------------------------------------------------------------
    # Settings Dialog
    # ---------------------------------------------------------------
    def _show_server_settings(self):
        url, ok = QInputDialog.getText(
            self,
            "LAN GPU Server Settings",
            "Enter the full URL of the GPU inference API:\n"
            "(e.g., http://192.168.1.100:8001/separate)",
            QLineEdit.Normal,
            self.server_url
        )
        if ok and url.strip():
            self.server_url = url.strip()
            # FIX: Persist settings so the URL survives app restarts
            self.settings.setValue("server_url", self.server_url)

    # ---------------------------------------------------------------
    # Processing Pipeline
    # ---------------------------------------------------------------
    def _start_processing(self):
        if not self.mp4_path or not os.path.exists(self.mp4_path):
            QMessageBox.warning(self, "Missing File", "Please select a valid MP4 file first.")
            return

        query = self.txt_query.text().strip()
        if not query:
            QMessageBox.warning(self, "Missing Query", "Please enter a description of the sound to extract.")
            return

        # Update UI to processing state
        self.btn_extract.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._update_status("Starting...")

        # Launch background worker
        self.worker = WorkerThread(self.mp4_path, query, self.server_url)
        self.worker.progress.connect(self._update_status)
        self.worker.finished.connect(self._processing_finished)
        self.worker.error.connect(self._processing_error)
        self.worker.start()

    def _update_status(self, msg: str):
        self.lbl_status.setText(msg)

    def _processing_finished(self, result_path: str):
        self.btn_extract.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._update_status("✅  Separation complete! You can now play or save the result.")

        self.result_wav_path = result_path
        self.btn_play.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_play.setText("▶  Play Audio")

        # Load the audio file into the player
        self.player.setSource(QUrl.fromLocalFile(self.result_wav_path))

    def _processing_error(self, err_msg: str):
        self.btn_extract.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._update_status("❌  Processing failed.")
        QMessageBox.critical(self, "Processing Failed", err_msg)

    # ---------------------------------------------------------------
    # Audio Playback
    # ---------------------------------------------------------------
    def _toggle_playback(self):
        # FIX: Use the correct PySide6 enum: QMediaPlayer.PlaybackState.Playing
        if self.player.playbackState() == QMediaPlayer.PlaybackState.Playing:
            self.player.pause()
            self.btn_play.setText("▶  Play Audio")
        else:
            self.player.play()
            self.btn_play.setText("⏸  Pause Audio")

    # ---------------------------------------------------------------
    # Save Result
    # ---------------------------------------------------------------
    def _save_result(self):
        if not self.result_wav_path:
            return

        # FIX: Removed deprecated QFileDialog.Options() argument
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Separated WAV", "separated_audio.wav", "Audio Files (*.wav)"
        )
        if save_path:
            try:
                shutil.copyfile(self.result_wav_path, save_path)
                QMessageBox.information(self, "Saved", f"File saved to:\n{save_path}")
            except OSError as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save file:\n{str(e)}")

    def closeEvent(self, event):
        """Stop audio player cleanly when window is closed."""
        self.player.stop()
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(3000)
        event.accept()
