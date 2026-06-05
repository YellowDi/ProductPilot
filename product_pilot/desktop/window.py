"""Minimal PySide6 desktop window."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from product_pilot.app import (
    DraftSpikePageNotReadyError,
    DraftSpikeRequest,
    DraftSpikeRunResult,
    ProductPilotAppError,
    ProductValidationResult,
    validate_product_file,
    run_draft_spike,
)
from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserLaunchConfig,
    PersistentBrowserSession,
)


class DraftSpikeWorker(QObject):
    log = Signal(str)
    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, config: BrowserLaunchConfig, request: DraftSpikeRequest) -> None:
        super().__init__()
        self._config = config
        self._request = request

    @Slot()
    def run(self) -> None:
        self.log.emit("开始执行草稿流程")
        try:
            result = run_draft_spike(self._config, self._request)
        except Exception as exc:
            self.failed.emit(exc)
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ProductPilot")
        self.resize(1040, 720)

        self._validation_result: ProductValidationResult | None = None
        self._browser_session: PersistentBrowserSession | None = None
        self._draft_thread: QThread | None = None
        self._draft_worker: DraftSpikeWorker | None = None

        self.product_path_edit = QLineEdit()
        self.profile_dir_edit = QLineEdit("profiles/chrome")
        self.artifacts_dir_edit = QLineEdit("artifacts/browser")
        self.backend_url_edit = QLineEdit("https://mms.pinduoduo.com/")
        self.publish_url_edit = QLineEdit("https://mms.pinduoduo.com/goods/category")
        self.channel_edit = QLineEdit("chrome")
        self.timeout_edit = QLineEdit("30000")
        self.slow_mo_edit = QLineEdit("0")
        self.headless_check = QCheckBox("无头模式")
        self.no_save_check = QCheckBox("只填表不保存")

        self.validate_button = QPushButton("校验资料")
        self.open_login_button = QPushButton("打开后台登录")
        self.check_login_button = QPushButton("检查登录状态")
        self.close_login_button = QPushButton("关闭登录浏览器")
        self.run_draft_button = QPushButton("运行草稿流程")

        self.product_table = QTableWidget(0, 6)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self._build_ui()
        self._connect_signals()
        self._set_browser_open(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout()

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("商品资料"))
        file_row.addWidget(self.product_path_edit, 1)
        browse_file_button = QPushButton("选择")
        browse_file_button.clicked.connect(self._browse_product_file)
        file_row.addWidget(browse_file_button)
        file_row.addWidget(self.validate_button)
        root.addLayout(file_row)

        config_group = QGroupBox("运行配置")
        config_layout = QGridLayout()
        config_layout.addWidget(QLabel("后台 URL"), 0, 0)
        config_layout.addWidget(self.backend_url_edit, 0, 1, 1, 3)
        config_layout.addWidget(QLabel("发布 URL"), 1, 0)
        config_layout.addWidget(self.publish_url_edit, 1, 1, 1, 3)
        config_layout.addWidget(QLabel("Profile"), 2, 0)
        config_layout.addWidget(self.profile_dir_edit, 2, 1)
        profile_button = QPushButton("选择")
        profile_button.clicked.connect(lambda: self._browse_directory(self.profile_dir_edit))
        config_layout.addWidget(profile_button, 2, 2)
        config_layout.addWidget(QLabel("Artifacts"), 3, 0)
        config_layout.addWidget(self.artifacts_dir_edit, 3, 1)
        artifacts_button = QPushButton("选择")
        artifacts_button.clicked.connect(lambda: self._browse_directory(self.artifacts_dir_edit))
        config_layout.addWidget(artifacts_button, 3, 2)
        config_layout.addWidget(QLabel("Channel"), 2, 3)
        config_layout.addWidget(self.channel_edit, 2, 4)
        config_layout.addWidget(QLabel("Timeout ms"), 3, 3)
        config_layout.addWidget(self.timeout_edit, 3, 4)
        config_layout.addWidget(QLabel("Slow-mo ms"), 4, 3)
        config_layout.addWidget(self.slow_mo_edit, 4, 4)
        config_layout.addWidget(self.headless_check, 4, 1)
        config_group.setLayout(config_layout)
        root.addWidget(config_group)

        action_row = QHBoxLayout()
        action_row.addWidget(self.open_login_button)
        action_row.addWidget(self.check_login_button)
        action_row.addWidget(self.close_login_button)
        action_row.addStretch(1)
        action_row.addWidget(self.no_save_check)
        action_row.addWidget(self.run_draft_button)
        root.addLayout(action_row)

        self.product_table.setHorizontalHeaderLabels(["商品编号", "标题", "类目", "SKU", "图片", "状态"])
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        root.addWidget(self.product_table, 2)

        root.addWidget(QLabel("日志"))
        root.addWidget(self.log_view, 2)

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.validate_button.clicked.connect(self._validate_products)
        self.open_login_button.clicked.connect(self._open_login_browser)
        self.check_login_button.clicked.connect(self._check_login_state)
        self.close_login_button.clicked.connect(self._close_login_browser)
        self.run_draft_button.clicked.connect(self._start_draft_spike)

    def _browse_product_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择商品资料",
            str(Path.cwd()),
            "Product files (*.xlsx *.json);;All files (*)",
        )
        if path:
            self.product_path_edit.setText(path)

    def _browse_directory(self, target: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择目录", target.text() or str(Path.cwd()))
        if directory:
            target.setText(directory)

    def _validate_products(self) -> ProductValidationResult | None:
        path = self._product_file_path()
        if path is None:
            return None

        result = validate_product_file(path)
        self._validation_result = result
        self._render_products(result)

        if result.load_error:
            self._append_log(result.load_error)
            QMessageBox.warning(self, "校验失败", result.load_error)
            return result
        if result.errors:
            self._append_log("资料校验失败")
            for error in result.errors:
                self._append_log(f"- {error}")
            QMessageBox.warning(self, "校验失败", "\n".join(result.errors[:8]))
            return result

        self._append_log(f"资料校验通过：{len(result.products)} 个商品")
        return result

    def _render_products(self, result: ProductValidationResult) -> None:
        self.product_table.setRowCount(len(result.products))
        status = "有效" if result.ok else "有错误"
        for row, product in enumerate(result.products):
            values = [
                product.product_id or str(row + 1),
                product.title,
                product.category,
                str(len(product.skus)),
                str(len(product.images)),
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {3, 4, 5}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.product_table.setItem(row, column, item)

    def _open_login_browser(self) -> None:
        if self._browser_session is not None:
            self._append_log("登录浏览器已打开")
            return

        config = self._browser_config(self.backend_url_edit.text().strip())
        if config is None:
            return

        try:
            self._browser_session = PersistentBrowserSession(config).__enter__()
            self._browser_session.open_backend()
        except BrowserAutomationError as exc:
            self._close_login_browser()
            self._append_log(str(exc))
            QMessageBox.warning(self, "浏览器启动失败", str(exc))
            return

        self._set_browser_open(True)
        self._append_log("后台浏览器已打开，可在 Chrome 中完成登录或风控验证")

    def _check_login_state(self) -> None:
        if self._browser_session is None:
            self._append_log("请先打开后台登录浏览器")
            return

        try:
            result = self._browser_session.check_login()
        except BrowserAutomationError as exc:
            self._append_log(str(exc))
            QMessageBox.warning(self, "登录检查失败", str(exc))
            return

        self._append_log(f"登录状态：{result.login.state.value}")
        self._append_log(f"原因：{result.login.reason}")
        self._append_log(f"页面：{result.login.snapshot.url}")
        self._append_log(f"截图：{result.screenshot_path.resolve()}")

    def _close_login_browser(self) -> None:
        if self._browser_session is not None:
            self._browser_session.close()
            self._browser_session = None
        self._set_browser_open(False)

    def _start_draft_spike(self) -> None:
        if self._draft_thread is not None:
            self._append_log("草稿流程正在运行")
            return
        if self._browser_session is not None:
            self._append_log("请先关闭登录浏览器，再运行草稿流程")
            QMessageBox.warning(self, "浏览器已打开", "请先关闭登录浏览器，再运行草稿流程。")
            return

        result = self._validation_result
        path = self._product_file_path()
        if path is None:
            return
        if result is None or result.path.resolve() != path.resolve():
            result = self._validate_products()
        if result is None:
            return
        if not result.ok:
            self._append_log("资料未通过校验，已停止草稿流程")
            return
        if len(result.products) != 1:
            self._append_log("桌面 MVP 当前只支持单商品草稿流程")
            QMessageBox.warning(self, "暂不支持批量", "当前桌面 MVP 只支持单商品草稿流程。")
            return

        config = self._browser_config(self.publish_url_edit.text().strip())
        if config is None:
            return

        request = DraftSpikeRequest(
            product_path=path,
            no_save=self.no_save_check.isChecked(),
        )
        self._draft_thread = QThread(self)
        self._draft_worker = DraftSpikeWorker(config, request)
        self._draft_worker.moveToThread(self._draft_thread)
        self._draft_thread.started.connect(self._draft_worker.run)
        self._draft_worker.log.connect(self._append_log)
        self._draft_worker.succeeded.connect(self._handle_draft_success)
        self._draft_worker.failed.connect(self._handle_draft_failure)
        self._draft_worker.finished.connect(self._draft_thread.quit)
        self._draft_worker.finished.connect(self._draft_worker.deleteLater)
        self._draft_thread.finished.connect(self._draft_thread.deleteLater)
        self._draft_thread.finished.connect(self._draft_finished)

        self._set_draft_running(True)
        self._draft_thread.start()

    def _handle_draft_success(self, result: object) -> None:
        assert isinstance(result, DraftSpikeRunResult)
        self._append_log(f"草稿保存：{result.saved}")
        self._append_log(f"页面：{result.url}")
        for note in result.notes:
            self._append_log(f"- {note.splitlines()[0]}")
        self._append_log(f"截图：{result.screenshot_path.resolve()}")
        self._append_log(f"JSON：{result.output_path.resolve()}")

    def _handle_draft_failure(self, exc: object) -> None:
        if isinstance(exc, DraftSpikePageNotReadyError):
            self._append_log(f"发布页状态：{exc.state.value}")
            self._append_log(f"原因：{exc.reason}")
            self._append_log(f"页面：{exc.url}")
            self._append_log(f"截图：{exc.screenshot_path.resolve()}")
            QMessageBox.warning(self, "发布页未就绪", exc.reason)
            return
        if isinstance(exc, ProductPilotAppError):
            self._append_log(str(exc))
            if exc.screenshot_path is not None:
                self._append_log(f"截图：{exc.screenshot_path.resolve()}")
            QMessageBox.warning(self, "草稿流程失败", str(exc))
            return
        if isinstance(exc, BrowserAutomationError):
            self._append_log(str(exc))
            QMessageBox.warning(self, "浏览器自动化失败", str(exc))
            return

        self._append_log(f"草稿流程失败：{exc}")
        QMessageBox.warning(self, "草稿流程失败", str(exc))

    def _draft_finished(self) -> None:
        self._draft_thread = None
        self._draft_worker = None
        self._set_draft_running(False)
        self._append_log("草稿流程结束")

    def _browser_config(self, url: str) -> BrowserLaunchConfig | None:
        if not url:
            QMessageBox.warning(self, "配置错误", "URL 不能为空。")
            return None
        try:
            timeout_ms = int(self.timeout_edit.text())
            slow_mo_ms = int(self.slow_mo_edit.text())
        except ValueError:
            QMessageBox.warning(self, "配置错误", "Timeout 和 Slow-mo 必须是整数。")
            return None

        config = BrowserLaunchConfig(
            backend_url=url,
            user_data_dir=Path(self.profile_dir_edit.text()).expanduser(),
            artifacts_dir=Path(self.artifacts_dir_edit.text()).expanduser(),
            channel=self.channel_edit.text().strip(),
            headless=self.headless_check.isChecked(),
            timeout_ms=timeout_ms,
            slow_mo_ms=slow_mo_ms,
        )
        errors = config.validate()
        if errors:
            QMessageBox.warning(self, "配置错误", "\n".join(errors))
            return None
        return config

    def _product_file_path(self) -> Path | None:
        value = self.product_path_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "缺少资料", "请选择商品资料文件。")
            return None
        return Path(value).expanduser()

    def _set_browser_open(self, opened: bool) -> None:
        self.open_login_button.setEnabled(not opened)
        self.check_login_button.setEnabled(opened)
        self.close_login_button.setEnabled(opened)

    def _set_draft_running(self, running: bool) -> None:
        self.run_draft_button.setEnabled(not running)
        self.validate_button.setEnabled(not running)
        self.no_save_check.setEnabled(not running)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._draft_thread is not None:
            QMessageBox.warning(self, "任务运行中", "草稿流程运行中，完成后再关闭窗口。")
            event.ignore()
            return
        self._close_login_browser()
        event.accept()
