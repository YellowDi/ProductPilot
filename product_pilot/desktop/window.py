"""Minimal PySide6 desktop window."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Event

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
    run_draft_spike_in_session,
)
from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserLaunchConfig,
    PersistentBrowserSession,
)
from product_pilot.importers.zzb import (
    ZzbImportError,
    ZzbImportRequest,
    import_zzb_export,
    suggest_zzb_output_path,
)
from product_pilot.domain.shop import ShopAccount, parse_shop_accounts


def _default_workspace_dir() -> Path:
    return Path.home() / "ProductPilot"


def _safe_path_part(value: str) -> str:
    safe = "".join(char if char not in '<>:"/\\|?*' else "_" for char in value.strip())
    return safe or "shop"


class DropPathLineEdit(QLineEdit):
    def __init__(
        self,
        *,
        allow_dirs: bool = False,
        suffixes: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._allow_dirs = allow_dirs
        self._suffixes = tuple(suffix.lower() for suffix in suffixes)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: object) -> None:
        if self._dropped_path(event) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event: object) -> None:
        path = self._dropped_path(event)
        if path is None:
            event.ignore()
            return
        self.setText(str(path))
        event.acceptProposedAction()

    def _dropped_path(self, event: object) -> Path | None:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                if self._allow_dirs:
                    return path
                continue
            if self._suffixes and path.suffix.lower() not in self._suffixes:
                continue
            return path
        return None


class DraftSpikeWorker(QObject):
    log = Signal(str)
    manual_action_required = Signal(str)
    succeeded = Signal(object)
    failed = Signal(object)
    finished = Signal()

    def __init__(self, config: BrowserLaunchConfig, request: DraftSpikeRequest) -> None:
        super().__init__()
        self._config = config
        self._request = request
        self._manual_action_done = Event()

    @Slot()
    def run(self) -> None:
        self.log.emit("开始执行草稿流程")
        try:
            result = run_draft_spike(
                self._config,
                self._request,
                manual_check_callback=self._wait_for_manual_action,
            )
        except Exception as exc:
            self.failed.emit(exc)
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()

    def continue_after_manual_action(self) -> None:
        self._manual_action_done.set()

    def _wait_for_manual_action(self, message: str) -> None:
        self._manual_action_done.clear()
        self.manual_action_required.emit(message)
        self._manual_action_done.wait()


@dataclass(frozen=True)
class ShopRunConfig:
    account: ShopAccount
    publish_config: BrowserLaunchConfig
    idle_url: str


class ShopBatchWorker(QObject):
    log = Signal(str)
    manual_action_required = Signal(str, str)
    item_started = Signal(str, int)
    item_succeeded = Signal(str, int, object)
    item_failed = Signal(str, int, object)
    shop_failed = Signal(str, object)
    work_finished = Signal(str)
    finished = Signal(str)

    def __init__(self, shop_config: ShopRunConfig, requests: tuple[DraftSpikeRequest, ...]) -> None:
        super().__init__()
        self._shop_config = shop_config
        self._requests = requests
        self._manual_action_done = Event()
        self._close_requested = Event()

    @property
    def shop_name(self) -> str:
        return self._shop_config.account.name

    @Slot()
    def run(self) -> None:
        session: PersistentBrowserSession | None = None
        shop_name = self.shop_name
        try:
            session = PersistentBrowserSession(self._shop_config.publish_config).__enter__()
            self.log.emit(f"[{shop_name}] 浏览器已打开")
        except Exception as exc:
            self.shop_failed.emit(shop_name, exc)
            self.finished.emit(shop_name)
            return

        try:
            should_wait_for_close = True
            failed = False
            for index, request in enumerate(self._requests):
                self.item_started.emit(shop_name, index)
                self.log.emit(f"[{shop_name}] 开始执行商品 {index + 1}/{len(self._requests)}")
                try:
                    result = run_draft_spike_in_session(
                        session,
                        request,
                        manual_check_callback=self._wait_for_manual_action,
                    )
                except Exception as exc:
                    self.item_failed.emit(shop_name, index, exc)
                    failed = True
                    break
                self.item_succeeded.emit(shop_name, index, result)

            if not failed:
                try:
                    session.open_url(self._shop_config.idle_url)
                    self.log.emit(f"[{shop_name}] 已回到商家后台首页待命")
                except Exception as exc:
                    self.log.emit(f"[{shop_name}] 回到后台首页失败：{exc}")

            self.work_finished.emit(shop_name)
            self._close_requested.wait()
            should_wait_for_close = False
        finally:
            if should_wait_for_close:
                self.work_finished.emit(shop_name)
            session.close()
            self.finished.emit(shop_name)

    def continue_after_manual_action(self) -> None:
        self._manual_action_done.set()

    def close_session(self) -> None:
        self._close_requested.set()
        self._manual_action_done.set()

    def _wait_for_manual_action(self, message: str) -> None:
        self._manual_action_done.clear()
        self.manual_action_required.emit(self.shop_name, message)
        self._manual_action_done.wait()


@dataclass
class BatchProductItem:
    path: Path
    product_id: str
    title: str
    category: str
    sku_count: int
    image_count: int
    status: str = "待处理"
    message: str = ""
    shop_statuses: dict[str, str] = field(default_factory=dict)
    shop_messages: dict[str, str] = field(default_factory=dict)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ProductPilot")
        self.resize(1040, 720)

        self._validation_result: ProductValidationResult | None = None
        self._batch_items: list[BatchProductItem] = []
        self._browser_session: PersistentBrowserSession | None = None
        self._draft_thread: QThread | None = None
        self._draft_worker: QObject | None = None
        self._shop_threads: list[QThread] = []
        self._shop_workers: list[ShopBatchWorker] = []
        self._shop_work_finished: set[str] = set()
        self._closing_shop_browsers = False

        self.zzb_excel_edit = DropPathLineEdit(suffixes=(".xlsx", ".xlsm"))
        self.zzb_media_edit = DropPathLineEdit(allow_dirs=True, suffixes=(".zip",))
        self.zzb_title_edit = QLineEdit()
        self.zzb_category_edit = QLineEdit()
        self.zzb_product_code_edit = QLineEdit()
        self.zzb_stock_edit = QLineEdit()
        self.zzb_stock_edit.setPlaceholderText("如 198")
        self.zzb_group_price_edit = QLineEdit()
        self.zzb_group_price_edit.setPlaceholderText("如 146.64")
        self.zzb_single_price_edit = QLineEdit()
        self.zzb_single_price_edit.setPlaceholderText("必须高于拼单价")
        workspace_dir = _default_workspace_dir()
        self.zzb_output_dir_edit = QLineEdit(str(workspace_dir / "imports"))
        self.zzb_sku_text_edit = QPlainTextEdit()
        self.zzb_sku_text_edit.setPlaceholderText("粘贴至尊宝复制 SKU 文字")
        self.zzb_sku_text_edit.setMaximumHeight(120)
        self.import_zzb_button = QPushButton("导入并生成商品资料")
        self.clear_zzb_button = QPushButton("清空导入信息")

        self.product_path_edit = QLineEdit()
        self.profile_dir_edit = QLineEdit(str(workspace_dir / "profiles" / "chrome"))
        self.artifacts_dir_edit = QLineEdit(str(workspace_dir / "artifacts" / "browser"))
        self.backend_url_edit = QLineEdit("https://mms.pinduoduo.com/")
        self.publish_url_edit = QLineEdit("https://mms.pinduoduo.com/goods/category")
        self.shop_accounts_edit = QPlainTextEdit()
        self.shop_accounts_edit.setPlaceholderText("每行一个店铺：店铺名|Profile目录。留空则使用上方 Profile。")
        self.shop_accounts_edit.setMaximumHeight(80)
        self.channel_edit = QLineEdit("chrome")
        self.timeout_edit = QLineEdit("30000")
        self.slow_mo_edit = QLineEdit("0")
        self.headless_check = QCheckBox("无头模式")
        self.no_save_check = QCheckBox("只填表不保存")

        self.validate_button = QPushButton("校验资料")
        self.add_to_batch_button = QPushButton("加入批次")
        self.open_login_button = QPushButton("打开后台登录")
        self.check_login_button = QPushButton("检查登录状态")
        self.close_login_button = QPushButton("关闭登录浏览器")
        self.clear_batch_button = QPushButton("清空批次")
        self.run_draft_button = QPushButton("运行当前草稿流程")
        self.run_batch_button = QPushButton("批量创建草稿")
        self.close_shop_browsers_button = QPushButton("关闭店铺浏览器")

        self.product_table = QTableWidget(0, 7)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self._build_ui()
        self._connect_signals()
        self._set_browser_open(False)
        self.close_shop_browsers_button.setEnabled(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout()

        zzb_group = QGroupBox("至尊宝导入")
        zzb_layout = QGridLayout()
        zzb_layout.addWidget(QLabel("导出表格"), 0, 0)
        zzb_layout.addWidget(self.zzb_excel_edit, 0, 1, 1, 3)
        zzb_excel_button = QPushButton("选择")
        zzb_excel_button.clicked.connect(self._browse_zzb_excel)
        zzb_layout.addWidget(zzb_excel_button, 0, 4)
        zzb_layout.addWidget(QLabel("媒体资源"), 1, 0)
        zzb_layout.addWidget(self.zzb_media_edit, 1, 1, 1, 3)
        zzb_zip_button = QPushButton("选择 zip")
        zzb_zip_button.clicked.connect(self._browse_zzb_media_zip)
        zzb_layout.addWidget(zzb_zip_button, 1, 4)
        zzb_dir_button = QPushButton("选择文件夹")
        zzb_dir_button.clicked.connect(self._browse_zzb_media_dir)
        zzb_layout.addWidget(zzb_dir_button, 1, 5)
        zzb_layout.addWidget(QLabel("商品标题"), 2, 0)
        zzb_layout.addWidget(self.zzb_title_edit, 2, 1, 1, 5)
        zzb_layout.addWidget(QLabel("类目路径"), 3, 0)
        zzb_layout.addWidget(self.zzb_category_edit, 3, 1, 1, 5)
        zzb_layout.addWidget(QLabel("库存"), 4, 0)
        zzb_layout.addWidget(self.zzb_stock_edit, 4, 1)
        zzb_layout.addWidget(QLabel("拼单价"), 4, 2)
        zzb_layout.addWidget(self.zzb_group_price_edit, 4, 3)
        zzb_layout.addWidget(QLabel("单买价"), 4, 4)
        zzb_layout.addWidget(self.zzb_single_price_edit, 4, 5)
        zzb_layout.addWidget(QLabel("SKU文字"), 5, 0)
        zzb_layout.addWidget(self.zzb_sku_text_edit, 5, 1, 1, 5)
        zzb_layout.addWidget(QLabel("商品编码"), 6, 0)
        zzb_layout.addWidget(self.zzb_product_code_edit, 6, 1)
        zzb_layout.addWidget(QLabel("输出目录"), 6, 2)
        zzb_layout.addWidget(self.zzb_output_dir_edit, 6, 3)
        zzb_output_button = QPushButton("选择")
        zzb_output_button.clicked.connect(lambda: self._browse_directory(self.zzb_output_dir_edit))
        zzb_layout.addWidget(zzb_output_button, 6, 4)
        zzb_button_row = QHBoxLayout()
        zzb_button_row.addWidget(self.clear_zzb_button)
        zzb_button_row.addWidget(self.import_zzb_button)
        zzb_layout.addLayout(zzb_button_row, 6, 5)
        zzb_group.setLayout(zzb_layout)
        root.addWidget(zzb_group)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("商品资料"))
        file_row.addWidget(self.product_path_edit, 1)
        browse_file_button = QPushButton("选择")
        browse_file_button.clicked.connect(self._browse_product_file)
        file_row.addWidget(browse_file_button)
        file_row.addWidget(self.validate_button)
        file_row.addWidget(self.add_to_batch_button)
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
        config_layout.addWidget(QLabel("店铺配置"), 5, 0)
        config_layout.addWidget(self.shop_accounts_edit, 5, 1, 1, 4)
        config_group.setLayout(config_layout)
        root.addWidget(config_group)

        action_row = QHBoxLayout()
        action_row.addWidget(self.open_login_button)
        action_row.addWidget(self.check_login_button)
        action_row.addWidget(self.close_login_button)
        action_row.addStretch(1)
        action_row.addWidget(self.clear_batch_button)
        action_row.addWidget(self.no_save_check)
        action_row.addWidget(self.run_draft_button)
        action_row.addWidget(self.run_batch_button)
        action_row.addWidget(self.close_shop_browsers_button)
        root.addLayout(action_row)

        self.product_table.setHorizontalHeaderLabels(["商品编号", "标题", "类目", "SKU", "图片", "状态", "资料"])
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.product_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        root.addWidget(self.product_table, 2)

        root.addWidget(QLabel("日志"))
        root.addWidget(self.log_view, 2)

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.import_zzb_button.clicked.connect(self._import_zzb_product)
        self.clear_zzb_button.clicked.connect(self._clear_zzb_inputs)
        self.validate_button.clicked.connect(self._validate_products)
        self.add_to_batch_button.clicked.connect(self._add_current_product_to_batch)
        self.open_login_button.clicked.connect(self._open_login_browser)
        self.check_login_button.clicked.connect(self._check_login_state)
        self.close_login_button.clicked.connect(self._close_login_browser)
        self.clear_batch_button.clicked.connect(self._clear_batch)
        self.run_draft_button.clicked.connect(self._start_draft_spike)
        self.run_batch_button.clicked.connect(self._start_batch_drafts)
        self.close_shop_browsers_button.clicked.connect(self._close_shop_browsers)

    def _browse_product_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择商品资料",
            str(Path.cwd()),
            "Product files (*.xlsx *.json);;All files (*)",
        )
        if path:
            self.product_path_edit.setText(path)

    def _browse_zzb_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择至尊宝导出表格",
            str(Path.cwd()),
            "Excel files (*.xlsx *.xlsm);;All files (*)",
        )
        if path:
            self.zzb_excel_edit.setText(path)

    def _browse_zzb_media_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择至尊宝媒体 zip",
            str(Path.cwd()),
            "Zip files (*.zip);;All files (*)",
        )
        if path:
            self.zzb_media_edit.setText(path)

    def _browse_zzb_media_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择至尊宝媒体目录", str(Path.cwd()))
        if directory:
            self.zzb_media_edit.setText(directory)

    def _browse_directory(self, target: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择目录", target.text() or str(Path.cwd()))
        if directory:
            target.setText(directory)

    def _clear_zzb_inputs(self) -> None:
        self.zzb_excel_edit.clear()
        self.zzb_media_edit.clear()
        self.zzb_title_edit.clear()
        self.zzb_product_code_edit.clear()
        self.zzb_stock_edit.clear()
        self.zzb_group_price_edit.clear()
        self.zzb_single_price_edit.clear()
        self.zzb_sku_text_edit.clear()
        self._append_log("至尊宝导入信息已清空")

    def _import_zzb_product(self) -> None:
        excel_path = Path(self.zzb_excel_edit.text().strip()).expanduser()
        assets_path = Path(self.zzb_media_edit.text().strip()).expanduser()
        sku_text = self.zzb_sku_text_edit.toPlainText()
        title = self.zzb_title_edit.text().strip()
        category = self.zzb_category_edit.text().strip()
        if not str(excel_path) or str(excel_path) == ".":
            QMessageBox.warning(self, "导入失败", "请选择至尊宝导出表格。")
            return
        if not str(assets_path) or str(assets_path) == ".":
            QMessageBox.warning(self, "导入失败", "请选择至尊宝媒体 zip 或文件夹。")
            return
        if not sku_text.strip():
            QMessageBox.warning(self, "导入失败", "请粘贴至尊宝 SKU 文字。")
            return
        if not title:
            QMessageBox.warning(self, "导入失败", "请填写商品标题。")
            return
        if not category:
            QMessageBox.warning(self, "导入失败", "请填写类目路径。")
            return
        price_config = self._zzb_price_config()
        if price_config is None:
            return
        stock, group_price, single_price = price_config

        output_dir = Path(self.zzb_output_dir_edit.text().strip() or "imports").expanduser()
        output_path = suggest_zzb_output_path(output_dir, excel_path, assets_path)
        try:
            result = import_zzb_export(
                ZzbImportRequest(
                    excel_path=excel_path,
                    sku_text=sku_text,
                    assets_path=assets_path,
                    title=title,
                    category=category,
                    product_code=self.zzb_product_code_edit.text().strip(),
                    stock=stock,
                    group_price=group_price,
                    single_price=single_price,
                    output_path=output_path,
                )
            )
        except ZzbImportError as exc:
            self._append_log(str(exc))
            QMessageBox.warning(self, "导入失败", str(exc))
            return

        self.product_path_edit.setText(str(result.output_path.resolve()))
        self._append_log(f"至尊宝导入完成：{result.output_path.resolve()}")
        self._append_log(f"SKU：{len(result.product.skus)}，图片：{len(result.product.images)}")
        for note in result.notes:
            self._append_log(note)
        self._add_product_file_to_batch(result.output_path)

    def _zzb_price_config(self) -> tuple[int, Decimal, Decimal] | None:
        try:
            stock = int(self.zzb_stock_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "导入失败", "库存必须是整数。")
            return None
        try:
            group_price = Decimal(self.zzb_group_price_edit.text().strip())
            single_price = Decimal(self.zzb_single_price_edit.text().strip())
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "导入失败", "拼单价和单买价必须是有效数字。")
            return None
        if stock < 0:
            QMessageBox.warning(self, "导入失败", "库存不能小于 0。")
            return None
        if group_price <= 0 or single_price <= 0:
            QMessageBox.warning(self, "导入失败", "拼单价和单买价必须大于 0。")
            return None
        if single_price <= group_price:
            QMessageBox.warning(self, "导入失败", "单买价必须大于拼单价。")
            return None
        return stock, group_price, single_price

    def _validate_products(self) -> ProductValidationResult | None:
        path = self._product_file_path()
        if path is None:
            return None

        result = validate_product_file(path)
        self._validation_result = result
        if not self._batch_items:
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
                str(result.path),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {3, 4, 5}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.product_table.setItem(row, column, item)

    def _add_current_product_to_batch(self) -> None:
        path = self._product_file_path()
        if path is None:
            return
        self._add_product_file_to_batch(path)

    def _add_product_file_to_batch(self, path: Path) -> bool:
        result = validate_product_file(path)
        self._validation_result = result
        if result.load_error:
            self._append_log(result.load_error)
            QMessageBox.warning(self, "加入批次失败", result.load_error)
            return False
        if result.errors:
            self._append_log("资料校验失败")
            for error in result.errors:
                self._append_log(f"- {error}")
            QMessageBox.warning(self, "加入批次失败", "\n".join(result.errors[:8]))
            return False
        if len(result.products) != 1:
            message = f"批次暂只接受单商品资料文件，当前文件包含 {len(result.products)} 个商品。"
            self._append_log(message)
            QMessageBox.warning(self, "加入批次失败", message)
            return False

        resolved_path = result.path.resolve()
        for item in self._batch_items:
            if item.path.resolve() == resolved_path:
                self._append_log(f"商品已在批次中：{resolved_path}")
                self.product_path_edit.setText(str(resolved_path))
                self._render_batch()
                return True

        product = result.products[0]
        self._batch_items.append(
            BatchProductItem(
                path=resolved_path,
                product_id=product.product_id or str(len(self._batch_items) + 1),
                title=product.title,
                category=product.category,
                sku_count=len(product.skus),
                image_count=len(product.images),
            )
        )
        self.product_path_edit.setText(str(resolved_path))
        self._append_log(f"已加入批次：{product.title}")
        self._render_batch()
        return True

    def _render_batch(self) -> None:
        self.product_table.setRowCount(len(self._batch_items))
        for row, item in enumerate(self._batch_items):
            status = self._format_batch_item_status(item)
            values = [
                item.product_id,
                item.title,
                item.category,
                str(item.sku_count),
                str(item.image_count),
                status,
                str(item.path),
            ]
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                if column in {3, 4, 5}:
                    table_item.setTextAlignment(Qt.AlignCenter)
                self.product_table.setItem(row, column, table_item)

    def _format_batch_item_status(self, item: BatchProductItem) -> str:
        if not item.shop_statuses:
            return item.status if not item.message else f"{item.status}: {item.message}"

        values: list[str] = []
        for shop_name, status in item.shop_statuses.items():
            message = item.shop_messages.get(shop_name, "")
            values.append(f"{shop_name}:{status}" if not message else f"{shop_name}:{status}({message})")
        return "；".join(values)

    def _clear_batch(self) -> None:
        if self._draft_thread is not None or self._shop_threads:
            self._append_log("任务运行中，不能清空批次")
            return
        self._batch_items.clear()
        self.product_table.setRowCount(0)
        self._append_log("批次已清空")

    def _open_login_browser(self) -> None:
        if self._shop_threads:
            self._append_log("店铺浏览器已打开，不能再打开登录浏览器")
            return
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
        if self._draft_thread is not None or self._shop_threads:
            self._append_log("草稿流程正在运行")
            return
        if self._browser_session is not None:
            self._append_log("运行前关闭登录浏览器会话")
            self._close_login_browser()

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
        self._draft_worker.manual_action_required.connect(self._handle_manual_action_required)
        self._draft_worker.succeeded.connect(self._handle_draft_success)
        self._draft_worker.failed.connect(self._handle_draft_failure)
        self._draft_worker.finished.connect(self._draft_thread.quit)
        self._draft_worker.finished.connect(self._draft_worker.deleteLater)
        self._draft_thread.finished.connect(self._draft_thread.deleteLater)
        self._draft_thread.finished.connect(self._draft_finished)

        self._set_draft_running(True)
        self._draft_thread.start()

    def _start_batch_drafts(self) -> None:
        if self._draft_thread is not None or self._shop_threads:
            self._append_log("草稿流程正在运行")
            return
        if self._browser_session is not None:
            self._append_log("运行前关闭登录浏览器会话")
            self._close_login_browser()
        if not self._batch_items:
            self._append_log("批次为空")
            QMessageBox.warning(self, "批次为空", "请先导入或加入商品资料。")
            return

        shop_configs = self._shop_run_configs()
        if not shop_configs:
            return

        runnable_items = [
            (index, item)
            for index, item in enumerate(self._batch_items)
            if item.status in {"待处理", "失败", "保存未确认"}
        ]
        if not runnable_items:
            self._append_log("批次中没有待处理商品")
            QMessageBox.information(self, "无需运行", "批次中没有待处理商品。")
            return

        shop_names = [shop_config.account.name for shop_config in shop_configs]
        for _, item in runnable_items:
            item.shop_statuses = {shop_name: "待处理" for shop_name in shop_names}
            item.shop_messages = {}
            item.status = "多店铺运行中"
            item.message = ""
        self._render_batch()

        requests = tuple(
            DraftSpikeRequest(
                product_path=item.path,
                no_save=self.no_save_check.isChecked(),
            )
            for _, item in runnable_items
        )

        self._set_draft_running(True)
        self.close_shop_browsers_button.setEnabled(False)
        self._closing_shop_browsers = False
        self._shop_work_finished.clear()
        self._append_log(f"开始多店铺批量创建草稿：{len(shop_configs)} 个店铺，{len(requests)} 个商品")

        runnable_indexes = tuple(index for index, _ in runnable_items)
        for shop_config in shop_configs:
            thread = QThread(self)
            worker = ShopBatchWorker(shop_config, requests)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.log.connect(self._append_log)
            worker.manual_action_required.connect(self._handle_shop_manual_action_required)
            worker.item_started.connect(
                lambda shop_name, worker_index, indexes=runnable_indexes: self._handle_shop_item_started(
                    shop_name,
                    indexes[worker_index],
                )
            )
            worker.item_succeeded.connect(
                lambda shop_name, worker_index, result, indexes=runnable_indexes: self._handle_shop_item_success(
                    shop_name,
                    indexes[worker_index],
                    result,
                )
            )
            worker.item_failed.connect(
                lambda shop_name, worker_index, exc, indexes=runnable_indexes: self._handle_shop_item_failure(
                    shop_name,
                    indexes[worker_index],
                    exc,
                )
            )
            worker.shop_failed.connect(self._handle_shop_failure)
            worker.work_finished.connect(self._handle_shop_work_finished)
            worker.finished.connect(lambda _shop_name, thread=thread: thread.quit())
            worker.finished.connect(lambda _shop_name, worker=worker: worker.deleteLater())
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(
                lambda thread=thread, worker=worker: self._handle_shop_thread_finished(thread, worker)
            )
            self._shop_threads.append(thread)
            self._shop_workers.append(worker)
            thread.start()

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

    def _handle_manual_action_required(self, message: str) -> None:
        self._append_log("等待人工处理人机验证")
        QMessageBox.information(
            self,
            "需要人工处理",
            f"{message}\n\n完成后点击“确定”继续执行。",
        )
        worker = self._draft_worker
        if worker is not None and hasattr(worker, "continue_after_manual_action"):
            worker.continue_after_manual_action()

    def _handle_shop_manual_action_required(self, shop_name: str, message: str) -> None:
        self._append_log(f"[{shop_name}] 等待人工处理登录或人机验证")
        QMessageBox.information(
            self,
            "需要人工处理",
            f"店铺：{shop_name}\n\n{message}\n\n完成后点击“确定”继续执行该店铺。",
        )
        for worker in self._shop_workers:
            if worker.shop_name == shop_name:
                worker.continue_after_manual_action()
                return

    def _handle_shop_item_started(self, shop_name: str, batch_index: int) -> None:
        item = self._batch_items[batch_index]
        item.shop_statuses[shop_name] = "运行中"
        item.shop_messages.pop(shop_name, None)
        self.product_path_edit.setText(str(item.path))
        self._render_batch()

    def _handle_shop_item_success(self, shop_name: str, batch_index: int, result: object) -> None:
        assert isinstance(result, DraftSpikeRunResult)
        item = self._batch_items[batch_index]
        if result.no_save:
            item.shop_statuses[shop_name] = "已填表"
        elif result.saved:
            item.shop_statuses[shop_name] = "草稿已保存"
        else:
            item.shop_statuses[shop_name] = "保存未确认"
        item.shop_messages.pop(shop_name, None)
        self._append_log(f"[{shop_name}] 商品完成：{item.title}，状态：{item.shop_statuses[shop_name]}")
        self._append_log(f"[{shop_name}] 截图：{result.screenshot_path.resolve()}")
        self._render_batch()

    def _handle_shop_item_failure(self, shop_name: str, batch_index: int, exc: object) -> None:
        item = self._batch_items[batch_index]
        item.shop_statuses[shop_name] = "失败"
        item.shop_messages[shop_name] = str(exc).splitlines()[0]
        self._render_batch()
        self._append_log(f"[{shop_name}] 商品失败：{item.title}")
        self._handle_draft_failure(exc)

    def _handle_shop_failure(self, shop_name: str, exc: object) -> None:
        self._shop_work_finished.add(shop_name)
        for item in self._batch_items:
            if item.shop_statuses.get(shop_name) in {"待处理", "运行中"}:
                item.shop_statuses[shop_name] = "失败"
                item.shop_messages[shop_name] = str(exc).splitlines()[0]
        self._render_batch()
        self._append_log(f"[{shop_name}] 店铺任务失败：{exc}")
        self._handle_draft_failure(exc)

    def _handle_shop_work_finished(self, shop_name: str) -> None:
        self._shop_work_finished.add(shop_name)
        for item in self._batch_items:
            if item.shop_statuses.get(shop_name) in {"待处理", "运行中"}:
                item.shop_statuses[shop_name] = "未执行"
        self._render_batch()
        self._append_log(f"[{shop_name}] 商品任务结束，浏览器保持打开")
        self._maybe_enable_close_shop_browsers()

    def _maybe_enable_close_shop_browsers(self) -> None:
        if (
            self._shop_workers
            and len(self._shop_work_finished) >= len(self._shop_workers)
            and not self._closing_shop_browsers
            and not self.close_shop_browsers_button.isEnabled()
        ):
            self.close_shop_browsers_button.setEnabled(True)
            self._append_log("所有店铺商品任务已结束。浏览器已保持打开，关闭前不能启动下一批次。")

    def _close_shop_browsers(self) -> None:
        if not self._shop_workers:
            self._append_log("没有待关闭的店铺浏览器")
            return
        self._closing_shop_browsers = True
        self.close_shop_browsers_button.setEnabled(False)
        self._append_log("正在关闭店铺浏览器")
        for worker in tuple(self._shop_workers):
            worker.close_session()

    def _handle_shop_thread_finished(self, thread: QThread, worker: ShopBatchWorker) -> None:
        if thread in self._shop_threads:
            self._shop_threads.remove(thread)
        if worker in self._shop_workers:
            self._shop_workers.remove(worker)
        if not self._shop_threads:
            self._shop_work_finished.clear()
            self._closing_shop_browsers = False
            self._set_draft_running(False)
            self.close_shop_browsers_button.setEnabled(False)
            self._append_log("店铺浏览器已关闭")
        else:
            self._maybe_enable_close_shop_browsers()

    def _draft_finished(self) -> None:
        self._draft_thread = None
        self._draft_worker = None
        self._set_draft_running(False)
        self._append_log("草稿流程结束")

    def _shop_run_configs(self) -> list[ShopRunConfig]:
        publish_url = self.publish_url_edit.text().strip()
        idle_url = self.backend_url_edit.text().strip()
        if not publish_url or not idle_url:
            QMessageBox.warning(self, "配置错误", "后台 URL 和发布 URL 不能为空。")
            return []
        if not idle_url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "配置错误", "后台 URL 必须是 http 或 https URL。")
            return []

        accounts, errors = parse_shop_accounts(self.shop_accounts_edit.toPlainText())
        if errors:
            QMessageBox.warning(self, "店铺配置错误", "\n".join(errors[:8]))
            return []
        if not accounts:
            accounts = [
                ShopAccount(
                    name="默认店铺",
                    profile_dir=Path(self.profile_dir_edit.text()).expanduser(),
                )
            ]

        try:
            timeout_ms = int(self.timeout_edit.text())
            slow_mo_ms = int(self.slow_mo_edit.text())
        except ValueError:
            QMessageBox.warning(self, "配置错误", "Timeout 和 Slow-mo 必须是整数。")
            return []

        artifacts_base = Path(self.artifacts_dir_edit.text()).expanduser()
        shop_configs: list[ShopRunConfig] = []
        config_errors: list[str] = []
        for account in accounts:
            account_errors = account.validate()
            if account_errors:
                config_errors.extend(f"{account.name}: {error}" for error in account_errors)
                continue

            config = BrowserLaunchConfig(
                backend_url=publish_url,
                user_data_dir=account.profile_dir,
                artifacts_dir=artifacts_base / _safe_path_part(account.name),
                channel=self.channel_edit.text().strip(),
                headless=self.headless_check.isChecked(),
                timeout_ms=timeout_ms,
                slow_mo_ms=slow_mo_ms,
            )
            errors = config.validate()
            if errors:
                config_errors.extend(f"{account.name}: {error}" for error in errors)
                continue
            shop_configs.append(ShopRunConfig(account=account, publish_config=config, idle_url=idle_url))

        if config_errors:
            QMessageBox.warning(self, "店铺配置错误", "\n".join(config_errors[:8]))
            return []
        return shop_configs

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
        self.run_batch_button.setEnabled(not running)
        self.validate_button.setEnabled(not running)
        self.add_to_batch_button.setEnabled(not running)
        self.clear_batch_button.setEnabled(not running)
        self.import_zzb_button.setEnabled(not running)
        self.clear_zzb_button.setEnabled(not running)
        self.no_save_check.setEnabled(not running)
        self.shop_accounts_edit.setEnabled(not running)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._draft_thread is not None or self._shop_threads:
            QMessageBox.warning(self, "任务运行中", "请先完成任务并关闭店铺浏览器后再关闭窗口。")
            event.ignore()
            return
        self._close_login_browser()
        event.accept()
