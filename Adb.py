import sys
import os
import subprocess
import re
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem,
    QListWidget, QListWidgetItem, QPushButton, QProgressBar, QLabel, QMessageBox, QInputDialog,
    QFileDialog, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont

class TransferWorker(QThread):
    progress = pyqtSignal(int, str)  # progress_percent, status_text
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, adb_path, device_id, operation, src, dst):
        super().__init__()
        self.adb_path = adb_path
        self.device_id = device_id
        self.operation = operation  # 'push' or 'pull'
        self.src = src
        self.dst = dst
        self.total_size = 0

    def run(self):
        try:
            # Determine total size
            if self.operation == 'push':
                self.total_size = os.path.getsize(self.src)
            elif self.operation == 'pull':
                cmd = [self.adb_path, '-s', self.device_id, 'shell', 'stat', '-c%s', self.src]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.total_size = int(result.stdout.strip())
                else:
                    self.finished.emit(False, f"Failed to get file size: {result.stderr}")
                    return

            # Execute transfer with -p
            cmd = [self.adb_path, '-s', self.device_id, self.operation, '-p', self.src, self.dst]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

            transferred = 0
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                # Parse progress: adb push/pull -p outputs lines like "  50%  512MB/s  10s" or similar
                # Actually, it outputs progress in a format like "  1234 / 5678" or percentage.
                # For simplicity, assume it outputs percentage and transferred size.
                # In reality, adb push/pull -p outputs to stderr, but let's capture stdout.
                # This is a simplification; real parsing might need adjustment.
                match = re.search(r'(\d+)%', line)
                if match:
                    percent = int(match.group(1))
                    # Estimate transferred based on percent, but better to parse actual bytes if possible.
                    # For now, use percent for progress bar.
                    transferred_mb = (percent / 100) * (self.total_size / (1024*1024))
                    total_mb = self.total_size / (1024*1024)
                    status = f"{transferred_mb:.2f} MB / {total_mb:.2f} MB"
                    self.progress.emit(percent, status)

            process.wait()
            if process.returncode == 0:
                self.finished.emit(True, "Transfer completed successfully.")
            else:
                self.finished.emit(False, f"Transfer failed with exit code {process.returncode}")
        except Exception as e:
            self.finished.emit(False, str(e))

class AdbFileExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.adb_path = self.get_adb_path()
        self.device_id = None
        self.current_path = '/sdcard'
        self.transfer_worker = None
        self.init_ui()
        self.check_device()
        self.refresh_file_list()

    def get_adb_path(self):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, 'adb.exe')
        else:
            # For development, assume adb.exe is in the same directory
            return os.path.join(os.path.dirname(__file__), 'adb.exe')

    def init_ui(self):
        self.setWindowTitle("ADB File Explorer")
        self.setGeometry(100, 100, 800, 600)

        # Dark theme
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: #ffffff; }
            QTreeWidget, QListWidget { background-color: #3c3c3c; color: #ffffff; border: 1px solid #555; }
            QPushButton { background-color: #555; color: #ffffff; border: 1px solid #777; padding: 5px; }
            QPushButton:disabled { background-color: #333; color: #666; }
            QProgressBar { background-color: #555; color: #ffffff; }
            QLabel { color: #ffffff; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Device status
        self.status_label = QLabel("Device: Not connected")
        layout.addWidget(self.status_label)

        # Splitter for tree and file list
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Tree widget for directories
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("Directories")
        self.tree_widget.itemDoubleClicked.connect(self.on_tree_double_click)
        splitter.addWidget(self.tree_widget)

        # File list
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.file_list.itemDoubleClicked.connect(self.on_file_double_click)
        splitter.addWidget(self.file_list)

        # Buttons
        button_layout = QHBoxLayout()
        self.up_button = QPushButton("Up")
        self.up_button.clicked.connect(self.go_up)
        button_layout.addWidget(self.up_button)

        self.create_folder_button = QPushButton("Create Folder")
        self.create_folder_button.clicked.connect(self.create_folder)
        button_layout.addWidget(self.create_folder_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_items)
        button_layout.addWidget(self.delete_button)

        self.push_button = QPushButton("Push to Phone")
        self.push_button.clicked.connect(self.push_files)
        button_layout.addWidget(self.push_button)

        self.pull_button = QPushButton("Pull from Phone")
        self.pull_button.clicked.connect(self.pull_files)
        button_layout.addWidget(self.pull_button)

        layout.addLayout(button_layout)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready")
        layout.addWidget(self.progress_label)

        # Timer to refresh device status
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_device)
        self.timer.start(5000)  # Check every 5 seconds

    def check_device(self):
        if not os.path.exists(self.adb_path):
            self.status_label.setText("ADB not found")
            return
        try:
            result = subprocess.run([self.adb_path, 'devices'], capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')[1:]  # Skip "List of devices attached"
            devices = [line.split('\t')[0] for line in lines if line.strip() and 'device' in line]
            if devices:
                self.device_id = devices[0]  # Take the first device
                self.status_label.setText(f"Device: {self.device_id}")
            else:
                self.device_id = None
                self.status_label.setText("Device: Not connected")
        except Exception as e:
            self.status_label.setText(f"Error checking device: {str(e)}")

    def refresh_file_list(self):
        if not self.device_id:
            return
        self.file_list.clear()
        self.tree_widget.clear()

        # Populate tree root
        root_item = QTreeWidgetItem(self.tree_widget, ['/sdcard'])
        root_item.setData(0, Qt.ItemDataRole.UserRole, '/sdcard')
        self.populate_tree_item(root_item)

        # List files in current path
        cmd = [self.adb_path, '-s', self.device_id, 'shell', 'ls', '-p', self.current_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                items = result.stdout.strip().split('\n')
                for item in items:
                    if item:
                        is_dir = item.endswith('/')
                        name = item.rstrip('/')
                        list_item = QListWidgetItem()
                        icon = self.get_icon(name, is_dir)
                        list_item.setIcon(icon)
                        list_item.setText(name)
                        list_item.setData(Qt.ItemDataRole.UserRole, is_dir)
                        self.file_list.addItem(list_item)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to list files: {str(e)}")

    def populate_tree_item(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        cmd = [self.adb_path, '-s', self.device_id, 'shell', 'ls', '-p', path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                items = result.stdout.strip().split('\n')
                for sub_item in items:
                    if sub_item and sub_item.endswith('/'):
                        name = sub_item.rstrip('/')
                        child = QTreeWidgetItem(item, [name])
                        child.setData(0, Qt.ItemDataRole.UserRole, os.path.join(path, name).replace('\\', '/'))
        except:
            pass

    def on_tree_double_click(self, item, column):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        self.current_path = path
        self.refresh_file_list()

    def on_file_double_click(self, item):
        name = item.text()
        is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            self.current_path = os.path.join(self.current_path, name).replace('\\', '/')
            self.refresh_file_list()

    def go_up(self):
        if self.current_path != '/sdcard':
            self.current_path = os.path.dirname(self.current_path)
            self.refresh_file_list()

    def get_icon(self, name, is_dir):
        if is_dir:
            return QIcon()  # Use emoji or default folder icon; for simplicity, use text
        ext = os.path.splitext(name)[1].lower()
        if ext in ['.jpg', '.png', '.gif']:
            return QIcon()  # 🖼️
        elif ext in ['.mp4', '.avi']:
            return QIcon()  # 🎥
        elif ext in ['.zip', '.rar']:
            return QIcon()  # 📦
        elif ext == '.apk':
            return QIcon()  # 📱
        else:
            return QIcon()  # 📄
        # Note: To use emojis, set text with emoji, but for QIcon, need images. For simplicity, use text.

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "Create Folder", "Folder name:")
        if ok and name:
            path = os.path.join(self.current_path, name).replace('\\', '/')
            cmd = [self.adb_path, '-s', self.device_id, 'shell', 'mkdir', '-p', path]
            try:
                result = subprocess.run(cmd)
                if result.returncode == 0:
                    self.refresh_file_list()
                else:
                    QMessageBox.warning(self, "Error", "Failed to create folder")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def delete_items(self):
        selected = self.file_list.selectedItems()
        if not selected:
            return
        reply = QMessageBox.question(self, "Confirm Delete", "Delete selected items recursively?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected:
                name = item.text()
                path = os.path.join(self.current_path, name).replace('\\', '/')
                cmd = [self.adb_path, '-s', self.device_id, 'shell', 'rm', '-rf', path]
                try:
                    subprocess.run(cmd)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to delete {name}: {str(e)}")
            self.refresh_file_list()

    def push_files(self):
        if self.transfer_worker and self.transfer_worker.isRunning():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Select files to push")
        if not files:
            return
        dst = self.current_path
        for src in files:
            # Check overwrite
            basename = os.path.basename(src)
            dst_path = os.path.join(dst, basename).replace('\\', '/')
            cmd = [self.adb_path, '-s', self.device_id, 'shell', 'test', '-e', dst_path]
            result = subprocess.run(cmd)
            if result.returncode == 0:
                reply = QMessageBox.question(self, "Overwrite", f"File {basename} exists. Overwrite?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    continue
            self.start_transfer('push', src, dst_path)

    def pull_files(self):
        if self.transfer_worker and self.transfer_worker.isRunning():
            return
        selected = self.file_list.selectedItems()
        if not selected:
            return
        dst_dir = QFileDialog.getExistingDirectory(self, "Select destination directory")
        if not dst_dir:
            return
        for item in selected:
            name = item.text()
            src = os.path.join(self.current_path, name).replace('\\', '/')
            dst = os.path.join(dst_dir, name)
            # Check overwrite
            if os.path.exists(dst):
                reply = QMessageBox.question(self, "Overwrite", f"File {name} exists. Overwrite?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.No:
                    continue
            self.start_transfer('pull', src, dst)

    def start_transfer(self, operation, src, dst):
        self.push_button.setEnabled(False)
        self.pull_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting transfer...")
        self.transfer_worker = TransferWorker(self.adb_path, self.device_id, operation, src, dst)
        self.transfer_worker.progress.connect(self.update_progress)
        self.transfer_worker.finished.connect(self.on_transfer_finished)
        self.transfer_worker.start()

    def update_progress(self, percent, status):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(status)

    def on_transfer_finished(self, success, message):
        self.push_button.setEnabled(True)
        self.pull_button.setEnabled(True)
        self.progress_bar.setValue(100 if success else 0)
        self.progress_label.setText(message)
        if success:
            self.refresh_file_list()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdbFileExplorer()
    window.show()
    sys.exit(app.exec())
