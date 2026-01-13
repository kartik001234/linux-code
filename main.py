import sys import os import subprocess import threading from PyQt6.QtWidgets import ( QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTreeWidget, QTreeWidgetItem, QFileDialog, QComboBox, QProgressBar, QMessageBox ) from PyQt6.QtCore import Qt

ADB = "adb" ANDROID_ROOT = "/sdcard/"

class ADBWindowsGUI(QWidget): def init(self): super().init() self.setWindowTitle("ADB File Manager") self.resize(900, 500)

self.current_device = None
    self.current_path = ANDROID_ROOT
    self.clipboard = None
    self.clipboard_mode = None

    self.init_ui()
    self.load_devices()
    self.refresh_files()

def init_ui(self):
    layout = QVBoxLayout()
    self.setLayout(layout)

    # Top: Device selection and path
    top_layout = QHBoxLayout()
    layout.addLayout(top_layout)

    top_layout.addWidget(QLabel("Device:"))
    self.device_combo = QComboBox()
    top_layout.addWidget(self.device_combo)
    refresh_btn = QPushButton("Refresh")
    refresh_btn.clicked.connect(self.load_devices)
    top_layout.addWidget(refresh_btn)
    up_btn = QPushButton("⬆ Up")
    up_btn.clicked.connect(self.go_up)
    top_layout.addWidget(up_btn)
    self.path_label = QLabel(self.current_path)
    top_layout.addWidget(self.path_label)

    # Main: File tree
    self.tree = QTreeWidget()
    self.tree.setHeaderHidden(True)
    self.tree.itemDoubleClicked.connect(self.open_item)
    layout.addWidget(self.tree)

    # Right: Action buttons
    action_layout = QHBoxLayout()
    layout.addLayout(action_layout)

    copy_btn = QPushButton("Copy")
    copy_btn.clicked.connect(self.copy)
    action_layout.addWidget(copy_btn)

    cut_btn = QPushButton("Cut")
    cut_btn.clicked.connect(self.cut)
    action_layout.addWidget(cut_btn)

    paste_btn = QPushButton("Paste")
    paste_btn.clicked.connect(self.paste)
    action_layout.addWidget(paste_btn)

    delete_btn = QPushButton("Delete")
    delete_btn.clicked.connect(self.delete)
    action_layout.addWidget(delete_btn)

    push_btn = QPushButton("Send from PC")
    push_btn.clicked.connect(self.push_from_pc)
    action_layout.addWidget(push_btn)

    pull_btn = QPushButton("Get to PC")
    pull_btn.clicked.connect(self.pull_to_pc)
    action_layout.addWidget(pull_btn)

    # Progress bar
    self.progress = QProgressBar()
    layout.addWidget(self.progress)

# ---------------- Device ----------------
def load_devices(self):
    try:
        out = subprocess.check_output([ADB, "devices"], text=True)
        devices = [l.split()[0] for l in out.splitlines() if "\tdevice" in l]
        self.device_combo.clear()
        self.device_combo.addItems(devices)
        if devices:
            self.current_device = devices[0]
        else:
            QMessageBox.warning(self, "No Device", "No Android device detected")
    except Exception as e:
        QMessageBox.critical(self, "ADB Error", str(e))

# ---------------- File Operations ----------------
def adb_shell(self, *args):
    return subprocess.check_output([ADB, "-s", self.current_device, "shell", *args], text=True)

def refresh_files(self):
    self.tree.clear()
    try:
        out = self.adb_shell("ls", self.current_path)
        for name in out.splitlines():
            QTreeWidgetItem(self.tree, [name])
        self.path_label.setText(self.current_path)
    except:
        pass

def open_item(self, item, column):
    name = item.text(0)
    new_path = self.current_path + name + "/"
    try:
        self.adb_shell("ls", new_path)
        self.current_path = new_path
        self.refresh_files()
    except:
        QMessageBox.information(self, "File", f"Selected: {name}")

def go_up(self):
    if self.current_path != ANDROID_ROOT:
        self.current_path = "/".join(self.current_path.rstrip("/").split("/")[:-1]) + "/"
        self.refresh_files()

def selected_item(self):
    sel = self.tree.selectedItems()
    return None if not sel else self.current_path + sel[0].text(0)

def copy(self):
    self.clipboard = self.selected_item()
    self.clipboard_mode = "copy"

def cut(self):
    self.clipboard = self.selected_item()
    self.clipboard_mode = "cut"

def paste(self):
    if not self.clipboard:
        return
    name = os.path.basename(self.clipboard)
    dest = self.current_path + name
    if self.clipboard_mode == "copy":
        subprocess.run([ADB, "-s", self.current_device, "shell", "cp", "-r", self.clipboard, dest])
    else:
        subprocess.run([ADB, "-s", self.current_device, "shell", "mv", self.clipboard, dest])
    self.refresh_files()

def delete(self):
    path = self.selected_item()
    if not path:
        return
    if QMessageBox.question(self, "Delete", "Are you sure?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
        subprocess.run([ADB, "-s", self.current_device, "shell", "rm", "-rf", path])
        self.refresh_files()

# ---------------- Transfer ----------------
def push_from_pc(self):
    file = QFileDialog.getOpenFileName(self, "Select file to send")[0]
    if not file:
        return
    threading.Thread(target=self._transfer, args=("push", file, self.current_path)).start()

def pull_to_pc(self):
    src = self.selected_item()
    if not src:
        return
    dest = QFileDialog.getExistingDirectory(self, "Select destination folder")
    if not dest:
        return
    threading.Thread(target=self._transfer, args=("pull", src, dest)).start()

def _transfer(self, mode, src, dest):
    self.progress.setRange(0,0)  # indeterminate
    subprocess.run([ADB, "-s", self.current_device, mode, src, dest])
    self.progress.setRange(0,1)
    self.progress.setValue(1)
    self.refresh_files()
    QMessageBox.information(self, "Done", "Transfer Complete")

if name == "main": app = QApplication(sys.argv) window = ADBWindowsGUI() window.show() sys.exit(app.exec())
