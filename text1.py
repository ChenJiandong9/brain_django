import sys
import os
import logging
import time
import asyncio
import textwrap
import pandas as pd
from datetime import datetime
from bleak import BleakScanner, BleakClient
from volcenginesdkarkruntime import Ark

from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QTextEdit, QStatusBar, QLabel,
    QFileDialog, QInputDialog, QLineEdit, QMessageBox
)
import qasync

# ================== 系统配置 ==================
# 创建日志目录
os.makedirs("logs", exist_ok=True)
log_file = os.path.join("logs", f"eeg_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# 默认API密钥
DEFAULT_API_KEY = "7a9d2091-b88e-4910-ac1b-b9301de2259f"


# ================== 蓝牙协议处理器 ==================
class TGAMDataCollector(QObject):
    data_received = Signal(dict)
    status_updated = Signal(str)
    file_created = Signal(str)
    connection_changed = Signal(bool)
    recording_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.client = None
        self.buffer = bytearray()
        self.raw_file = None
        self.csv_file = None
        self.is_recording = False
        self.is_connected = False
        self.last_data_time = time.time()
        self.current_csv_path = ""

        # EEG频段定义
        self.EEG_BANDS = [
            'Delta', 'Theta',
            'Low Alpha', 'High Alpha',
            'Low Beta', 'High Beta',
            'Low Gamma', 'Middle Gamma'
        ]

    async def connect_device(self):
        """连接蓝牙设备"""
        try:
            self.status_updated.emit("正在扫描设备...")

            # 扫描设备并打印调试信息
            devices = await BleakScanner.discover()
            logger.info(f"发现 {len(devices)} 个蓝牙设备:")
            for device in devices:
                logger.info(f" - {device.name} ({device.address})")
                if device.name and "JDY-18" in device.name:
                    self.status_updated.emit(f"找到兼容设备: {device.name}")
                    target_device = device
                    break
            else:
                self.status_updated.emit("未找到兼容设备")
                return False

            self.client = BleakClient(target_device)
            await self.client.connect(timeout=20)  # 增加超时时间
            await self.client.start_notify("0000FFE1-0000-1000-8000-00805F9B34FB", self._data_handler)
            self.is_connected = True
            self.connection_changed.emit(True)
            self.status_updated.emit("设备已连接")
            return True
        except Exception as e:
            self.status_updated.emit(f"连接失败: {str(e)}")
            logger.exception("连接失败详情")
            return False

    def _data_handler(self, sender, data):
        """数据处理回调"""
        try:
            self.buffer.extend(data)
            self._process_buffer()
            self.last_data_time = time.time()
        except Exception as e:
            logger.error(f"数据处理错误: {str(e)}")

    def _process_buffer(self):
        """处理缓冲区数据"""
        try:
            while len(self.buffer) >= 4:
                # 查找大包同步头 (AA AA 20)
                sync_pos = -1
                for i in range(len(self.buffer) - 2):
                    if self.buffer[i] == 0xAA and self.buffer[i + 1] == 0xAA and self.buffer[i + 2] == 0x20:
                        sync_pos = i
                        break

                if sync_pos == -1:
                    # 没有找到同步头，清空缓冲区
                    if len(self.buffer) > 100:
                        self.buffer.clear()
                    return

                if sync_pos > 0:
                    # 删除同步头前的无效数据
                    del self.buffer[:sync_pos]
                    continue

                if len(self.buffer) < 32:  # 等待完整数据包
                    return

                packet = bytes(self.buffer[:32])
                del self.buffer[:32]

                parsed = self._parse_packet(packet)
                if parsed:
                    self.data_received.emit(parsed)
                    if self.csv_file:
                        self._write_to_csv(parsed)
        except Exception as e:
            logger.error(f"处理数据包出错: {str(e)}")
            self.buffer.clear()

    def _parse_packet(self, packet):
        """解析TGAM数据包（取消校验和检查）"""
        try:
            # 检查同步头和长度
            if len(packet) < 32 or packet[0] != 0xAA or packet[1] != 0xAA or packet[2] != 0x20:
                return None

            # 不再进行校验和检查
            # 直接解析信号质量 (0x02)
            signal_quality = packet[4]

            # 检查EEG功率开始标记 (0x83)
            if packet[5] != 0x83:
                logger.warning("缺少EEG功率开始标记")
                return None

            # 解析EEG功率谱 (24字节 = 8频段×3字节)
            eeg_power = {}
            index = 6
            for band in self.EEG_BANDS:
                # 每个频段3个字节 (高位->低位)
                value = (packet[index] << 16) | (packet[index + 1] << 8) | packet[index + 2]
                eeg_power[band] = value
                index += 3

            # 解析专注度 (0x04) 和放松度 (0x05)
            attention = 0
            meditation = 0
            while index < 30:  # 最后2字节是其他数据
                code = packet[index]
                if code == 0x04:
                    attention = packet[index + 1]
                    index += 2
                elif code == 0x05:
                    meditation = packet[index + 1]
                    index += 2
                else:
                    index += 1

            return {
                "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "信号质量": signal_quality,
                "专注度": attention,
                "放松度": meditation,
                **eeg_power
            }
        except Exception as e:
            logger.error(f"解析数据包异常: {str(e)}")
            return None

    def _write_to_csv(self, data):
        """写入CSV文件"""
        try:
            if self.csv_file.tell() == 0:  # 新文件写入表头
                header = [
                    "时间", "信号质量", "专注度", "放松度",
                    *self.EEG_BANDS
                ]
                self.csv_file.write(",".join(header) + "\n")

            # 按顺序写入数据
            row = [
                data["时间"],
                str(data["信号质量"]),
                str(data["专注度"]),
                str(data["放松度"]),
                *[str(data[band]) for band in self.EEG_BANDS]
            ]
            self.csv_file.write(",".join(row) + "\n")
        except Exception as e:
            logger.error(f"写入CSV失败: {str(e)}")

    def start_recording(self, base_path):
        """开始记录数据"""
        try:
            csv_path = f"{base_path}.csv"
            self.csv_file = open(csv_path, "w", encoding="utf-8")
            logger.info(f"创建数据文件: {csv_path}")
            self.current_csv_path = csv_path  # 保存当前文件路径

            self.is_recording = True
            self.recording_changed.emit(True)
            self.file_created.emit(csv_path)
            self.status_updated.emit("开始记录数据...")
            return True
        except Exception as e:
            self.status_updated.emit(f"创建文件失败: {str(e)}")
            return False

    def stop_recording(self):
        """停止记录"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        self.is_recording = False
        self.recording_changed.emit(False)
        self.buffer.clear()
        self.status_updated.emit("数据记录已停止")

    async def disconnect_device(self):
        """断开设备连接"""
        if self.client and self.is_connected:
            try:
                await self.client.disconnect()
                self.status_updated.emit("设备已断开")
            except Exception as e:
                self.status_updated.emit(f"断开连接时出错: {str(e)}")
            finally:
                self.client = None
                self.is_connected = False
                self.connection_changed.emit(False)


# ================== 数据分析器 ==================
class EEGAnalyzer(QThread):
    analysis_complete = Signal(str, str)

    def __init__(self, csv_path, api_key):
        super().__init__()
        self.csv_path = csv_path
        self.api_key = api_key
        self.report_path = os.path.splitext(self.csv_path)[0] + "_report.md"
        logger.info(f"分析器初始化，CSV路径: {csv_path}")

    def run(self):
        try:
            logger.info("开始分析数据...")
            df = self._load_and_preprocess_data()
            logger.info(f"成功加载数据，形状: {df.shape}")

            # 合并相关频段
            df['Alpha'] = df['Low Alpha'] + df['High Alpha']
            df['Beta'] = df['Low Beta'] + df['High Beta']
            df['Gamma'] = df['Low Gamma'] + df['Middle Gamma']

            report_content = self._generate_report(df)

            with open(self.report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            logger.info(f"报告已保存: {self.report_path}")

            self.analysis_complete.emit(report_content, self.report_path)

        except Exception as e:
            error_msg = f"分析失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.analysis_complete.emit(error_msg, "")

    def _load_and_preprocess_data(self):
        """增强版数据加载方法"""
        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'utf-8-sig', 'ISO-8859-1']
        df = None

        for encoding in encodings:
            try:
                df = pd.read_csv(self.csv_path, encoding=encoding)
                logger.info(f"使用编码 {encoding} 成功读取文件")

                # 检查必要列
                required_cols = ['时间', '信号质量', 'Delta', 'Theta',
                                 'Low Alpha', 'High Alpha', 'Low Beta',
                                 'High Beta', 'Low Gamma', 'Middle Gamma']

                missing_cols = [col for col in required_cols if col not in df.columns]

                if missing_cols:
                    logger.warning(f"缺失列: {', '.join(missing_cols)}")
                    # 尝试自动填充缺失列
                    for col in missing_cols:
                        if col == '信号质量':
                            df[col] = 200  # 默认良好信号
                        else:
                            df[col] = 0

                # 数据清洗
                df = df.dropna()
                if df.empty:
                    raise ValueError("数据为空，请检查文件内容")

                return df

            except Exception as e:
                logger.warning(f"编码 {encoding} 读取失败: {str(e)}")
                continue

        raise ValueError(f"无法读取CSV文件，尝试的编码: {encodings}")

    def _generate_report(self, df):
        """生成带格式的分析报告"""
        # 1. 基础统计
        stats = self._format_stats(df)

        # 2. 睡眠阶段分析
        sleep_analysis = self._analyze_sleep_stages(df)

        # 3. AI分析
        ai_content = self._get_ai_analysis(df, stats, sleep_analysis)

        # 组装最终报告
        report_content = textwrap.dedent(f"""
        <html>
        <head>
        <style>
            .section-title {{
                font-size: 18px;
                font-weight: bold;
                margin-top: 20px;
                margin-bottom: 10px;
                padding: 8px;
                border-radius: 5px;
            }}

            .data-overview {{
                background-color: #e6f7ff;
                border-left: 4px solid #1890ff;
            }}

            .sleep-analysis {{
                background-color: #f6ffed;
                border-left: 4px solid #52c41a;
            }}

            .ai-assessment {{
                background-color: #fff7e6;
                border-left: 4px solid #fa8c16;
            }}

            .critical {{
                color: #f5222d;
                font-weight: bold;
            }}

            .important {{
                color: #1890ff;
                font-weight: bold;
            }}

            .summary-table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
            }}

            .summary-table th, .summary-table td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}

            .summary-table th {{
                background-color: #f2f2f2;
            }}
        </style>
        </head>
        <body>

        <h1 style="color:#1890ff; text-align:center;">脑电睡眠分析报告</h1>

        <div class="section-title data-overview">数据概览</div>
        <table class="summary-table">
            <tr>
                <th>记录时长</th>
                <td>{len(df)} 个采样点</td>
                <th>开始时间</th>
                <td>{df['时间'].iloc[0]}</td>
            </tr>
            <tr>
                <th>结束时间</th>
                <td>{df['时间'].iloc[-1]}</td>
                <th>平均信号质量</th>
                <td>{df['信号质量'].mean():.1f}/200</td>
            </tr>
        </table>

        {stats}

        <div class="section-title sleep-analysis">睡眠阶段分析</div>
        {sleep_analysis}

        <div class="section-title ai-assessment">AI健康评估</div>
        {ai_content}

        <p style="text-align:right; font-style:italic; margin-top:30px;">
            报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
        </body>
        </html>
        """)

        return report_content

    def _format_stats(self, df):
        """格式化统计信息为HTML表格"""
        # 提取关键统计信息
        stats_df = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].describe().loc[['mean', 'std', 'min', 'max']]

        # 创建HTML表格
        html = "<table class='summary-table'>\n"
        html += "<tr><th>频段</th><th>平均值</th><th>标准差</th><th>最小值</th><th>最大值</th></tr>\n"

        for band in stats_df.columns:
            row = stats_df[band]
            html += f"<tr>"
            html += f"<td>{band}</td>"
            html += f"<td>{row['mean']:.1f}</td>"
            html += f"<td>{row['std']:.1f}</td>"
            html += f"<td>{row['min']:.1f}</td>"
            html += f"<td>{row['max']:.1f}</td>"
            html += "</tr>\n"

        html += "</table>"
        return html

    def _analyze_sleep_stages(self, df):
        """专业睡眠阶段分析"""
        # 计算各波段占比
        total_power = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].sum().sum()
        percentages = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].sum() / total_power * 100

        # 睡眠阶段判断
        sleep_stages = []
        if percentages.Delta > 40:
            sleep_stages.append("<span class='important'>深睡期(Delta波主导)</span>")
        if percentages.Theta > 30:
            sleep_stages.append("<span class='important'>浅睡期(Theta波主导)</span>")
        if percentages.Alpha > 20:
            sleep_stages.append("<span class='important'>入睡期/REM(Alpha波活跃)</span>")
        if percentages.Beta > 15:
            sleep_stages.append("<span class='critical'>清醒期(Beta波活跃)</span>")

        # 睡眠质量评估
        sleep_score = min(100, int(
            0.4 * percentages.Delta +
            0.3 * percentages.Theta +
            0.2 * (100 - percentages.Beta) +
            0.1 * (100 - percentages.Gamma)
        ))

        quality_class = ""
        if sleep_score >= 80:
            quality = "优秀"
            quality_class = "important"
        elif sleep_score >= 60:
            quality = "良好"
            quality_class = "important"
        elif sleep_score >= 40:
            quality = "一般"
            quality_class = "critical"
        else:
            quality = "较差"
            quality_class = "critical"

        analysis = textwrap.dedent(f"""
        <table class="summary-table">
            <tr>
                <th>睡眠阶段</th>
                <th>占比</th>
                <th>评估</th>
            </tr>
            <tr>
                <td>深睡期(Delta)</td>
                <td>{percentages.Delta:.1f}%</td>
                <td>{'<span class="critical">过低</span>' if percentages.Delta < 30 else '<span class="important">正常</span>' if percentages.Delta < 50 else '<span class="important">充足</span>'}</td>
            </tr>
            <tr>
                <td>浅睡期(Theta)</td>
                <td>{percentages.Theta:.1f}%</td>
                <td>{'<span class="critical">过低</span>' if percentages.Theta < 20 else '<span class="important">正常</span>' if percentages.Theta < 40 else '<span class="important">充足</span>'}</td>
            </tr>
            <tr>
                <td>入睡期/REM(Alpha)</td>
                <td>{percentages.Alpha:.1f}%</td>
                <td>{'<span class="critical">过低</span>' if percentages.Alpha < 10 else '<span class="important">正常</span>' if percentages.Alpha < 30 else '<span class="important">充足</span>'}</td>
            </tr>
            <tr>
                <td>清醒期(Beta)</td>
                <td>{percentages.Beta:.1f}%</td>
                <td>{'<span class="important">正常</span>' if percentages.Beta < 20 else '<span class="critical">过高</span>'}</td>
            </tr>
            <tr>
                <td>活跃期(Gamma)</td>
                <td>{percentages.Gamma:.1f}%</td>
                <td>{'<span class="important">正常</span>' if percentages.Gamma < 10 else '<span class="critical">过高</span>'}</td>
            </tr>
        </table>

        <h3>检测到的睡眠阶段</h3>
        <p>{", ".join(sleep_stages) if sleep_stages else "无法确定明确睡眠阶段"}</p>

        <h3>睡眠质量评分</h3>
        <p class="{quality_class}" style="font-size: 24px; padding: 10px; text-align: center;">
            {sleep_score}/100 ({quality})
        </p>

        <h3>睡眠质量建议</h3>
        <ul>
            <li>{"<span class='critical'>深睡不足</span>，建议增加睡眠时间并减少睡前刺激" if percentages.Delta < 30 else ""}</li>
            <li>{"<span class='critical'>清醒期过长</span>，建议改善睡眠环境" if percentages.Beta > 20 else ""}</li>
            <li>{"<span class='important'>睡眠质量良好</span>，继续保持健康作息" if sleep_score >= 60 else ""}</li>
        </ul>
        """)

        return analysis

    def _get_ai_analysis(self, df, stats, sleep_analysis):
        """获取AI分析内容"""
        if not self.api_key:
            return "<p class='critical'>API密钥未配置，无法获取AI分析结果</p>"

        try:
            client = Ark(api_key=self.api_key)

            prompt = textwrap.dedent(f"""
            你是一个专业的睡眠脑电分析师。请根据以下数据提供专业分析：

            1. 基础统计:
            {stats}

            2. 睡眠阶段分析:
            {sleep_analysis}

            请用HTML格式回答，包含以下部分：
            - 睡眠结构评估（各阶段占比是否正常）
            - 睡眠质量分析（基于脑电特征）
            - 潜在问题发现（如睡眠碎片化、深睡不足等） 
            - 科学建议（生活习惯、就医建议等）
            - 判断依据（解释分析逻辑）

            使用专业术语但保持易懂，重要数据和关键问题用<strong>加粗</strong>强调，
            特别重要或危险的问题用<span style="color:red">红色</span>标记。
            """)

            response = client.chat.completions.create(
                model="doubao-1.5-thinking-pro-250415",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3  # 降低随机性
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"AI分析失败: {str(e)}")
            return f"<p class='critical'>AI分析失败: {str(e)}</p>"


# ================== 主界面 ==================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("基于EEG与人工智能的睡眠健康评估系统 V1.0")
        self.setGeometry(100, 100, 1024, 768)
        self.collector = TGAMDataCollector()
        self.analyzer = None
        self.api_key = DEFAULT_API_KEY  # 使用默认密钥
        self._setup_ui()
        self._connect_signals()

        # 添加状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.setStyleSheet("""
            QStatusBar {
                background-color: #f5f5f5;
                border-top: 1px solid #ddd;
                padding: 2px;
            }
        """)
        self.statusBar.showMessage(f"日志文件: {log_file} | 使用默认API密钥")

    def _setup_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 获取字体数据库
        font_db = QFontDatabase()

        # ===== 标题栏 =====
        title_label = QLabel("基于EEG与人工智能的睡眠健康评估系统 V1.0")

        title_font = QFont()
        font_families = ["Microsoft YaHei", "SimHei", "Arial"]
        for font in font_families:
            if font in font_db.families():
                title_font.setFamily(font)
                break
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                padding: 10px;
                background-color: #e6f7ff;
                border-radius: 5px;
            }
        """)
        layout.addWidget(title_label)

        # ===== 控制面板 =====
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 创建样式统一的按钮
        self.btn_connect = self._create_button("连接设备", "#1890ff")
        self.btn_record = self._create_button("开始记录", "#52c41a")
        self.btn_analyze = self._create_button("分析数据", "#722ed1")

        self.btn_record.setEnabled(False)
        self.btn_analyze.setEnabled(False)

        control_layout.addWidget(self.btn_connect)
        control_layout.addWidget(self.btn_record)
        control_layout.addWidget(self.btn_analyze)
        control_layout.addStretch()

        layout.addWidget(control_panel)

        # ===== 数据展示区 =====
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d9d9d9;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #f0f0f0;
                padding: 8px 12px;
                border: 1px solid #d9d9d9;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #1890ff;
            }
        """)

        # 实时数据标签页
        self.raw_view = QTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setFont(QFont("Consolas", 10))
        self.raw_view.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: none;
                padding: 5px;
            }
        """)

        # 分析报告标签页
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)

        report_font = QFont()
        for font in font_families:
            if font in font_db.families():
                report_font.setFamily(font)
                break
        report_font.setPointSize(11)
        self.report_view.setFont(report_font)
        self.report_view.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: none;
                padding: 10px;
            }
        """)

        # 系统日志标签页
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: none;
                padding: 5px;
            }
        """)

        self.tabs.addTab(self.raw_view, "实时数据")
        self.tabs.addTab(self.report_view, "分析报告")
        self.tabs.addTab(self.log_view, "系统日志")

        layout.addWidget(self.tabs, 1)

        # 重定向日志到视图
        class LogHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget

            def emit(self, record):
                msg = self.format(record)
                self.text_widget.append(msg)

        log_handler = LogHandler(self.log_view)
        log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(log_handler)

    def _create_button(self, text, color):
        """创建样式统一的按钮"""
        button = QPushButton(text)
        button.setFont(QFont("Microsoft YaHei", 10))
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {color}, stop:1 #003a8c
                );
            }}
            QPushButton:pressed {{
                background-color: #003a8c;
            }}
            QPushButton:disabled {{
                background-color: #d9d9d9;
                color: #8c8c8c;
            }}
        """)
        return button

    def update_status(self, status):
        """更新状态显示"""
        self.statusBar.showMessage(status)

    def _connect_signals(self):
        """连接信号槽"""
        self.btn_connect.clicked.connect(lambda: asyncio.create_task(self.toggle_connection()))
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_analyze.clicked.connect(self.analyze_data)
        self.collector.data_received.connect(self.update_raw_view)
        self.collector.file_created.connect(self.enable_analysis)
        self.collector.status_updated.connect(self.update_status)
        self.collector.connection_changed.connect(self.update_connection_status)
        self.collector.recording_changed.connect(self.update_recording_status)

    def update_connection_status(self, connected):
        """更新连接状态"""
        if connected:
            self.btn_connect.setText("断开连接")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #f5222d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
            """)
            self.btn_record.setEnabled(True)
        else:
            self.btn_connect.setText("连接设备")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #1890ff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
            """)
            self.btn_record.setEnabled(False)
            if self.collector.is_recording:
                self.collector.stop_recording()
                self.btn_record.setText("开始记录")

    def update_recording_status(self, recording):
        """更新记录状态"""
        if recording:
            self.btn_record.setText("停止记录")
            self.btn_record.setStyleSheet("""
                QPushButton {
                    background-color: #f5222d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
            """)
        else:
            self.btn_record.setText("开始记录")
            self.btn_record.setStyleSheet("""
                QPushButton {
                    background-color: #52c41a;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
            """)

    async def toggle_connection(self):
        """切换连接状态"""
        if self.collector.is_connected:
            await self.collector.disconnect_device()
        else:
            await self.collector.connect_device()

    def toggle_recording(self):
        """切换记录状态"""
        if not self.collector.is_recording:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "保存数据文件",
                os.path.join(os.getcwd(), f"eeg_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                "CSV文件 (*.csv)"
            )
            if path:
                if not path.lower().endswith('.csv'):
                    path += '.csv'
                base_path = os.path.splitext(path)[0]
                if self.collector.start_recording(base_path):
                    self.raw_view.clear()
        else:
            self.collector.stop_recording()

    def analyze_data(self):
        """启动分析"""
        # 如果用户想自定义API密钥
        if QMessageBox.question(
                self,
                "API密钥",
                f"当前使用默认API密钥: {self.api_key[:8]}...\n\n是否要使用自定义密钥？",
                QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:

            new_key, ok = QInputDialog.getText(
                self,
                "自定义API密钥",
                "请输入火山引擎API密钥:",
                QLineEdit.Normal,
                self.api_key
            )
            if ok and new_key:
                self.api_key = new_key
                self.statusBar.showMessage(f"已更新API密钥: {new_key[:8]}...")

        if not self.collector.is_recording:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择CSV文件",
                os.getcwd(),
                "CSV文件 (*.csv)"
            )
        else:
            path = self.collector.current_csv_path

        if path:
            self.start_analysis(path)

    def start_analysis(self, path):
        """开始分析指定路径的文件"""
        self.report_view.clear()
        self.report_view.setHtml("<div style='text-align:center; padding:50px;'><h2>正在分析数据，请稍候...</h2></div>")
        self.tabs.setCurrentIndex(1)  # 切换到报告标签页

        self.analyzer = EEGAnalyzer(path, self.api_key)
        self.analyzer.analysis_complete.connect(self.show_report)
        self.analyzer.start()

    def show_report(self, report_content, report_path):
        """显示分析报告"""
        if report_path:
            self.report_view.setHtml(report_content)
            self.statusBar.showMessage(f"报告已生成: {report_path}")
        else:
            self.report_view.setHtml(f"<div class='critical'><h2>报告生成失败</h2><p>{report_content}</p></div>")
            self.statusBar.showMessage("报告生成失败")

    def enable_analysis(self, path):
        """启用分析功能"""
        self.btn_analyze.setEnabled(True)
        self.collector.current_csv_path = path

    def update_raw_view(self, data):
        """更新实时数据视图"""
        text = f"[{data['时间']}] Delta: {data['Delta']} Theta: {data['Theta']} 质量: {data['信号质量']}"
        self.raw_view.append(text)

    def closeEvent(self, event):
        """关闭应用程序前的清理"""
        if self.collector.is_recording:
            self.collector.stop_recording()

        if self.analyzer and self.analyzer.isRunning():
            self.analyzer.quit()
            self.analyzer.wait(2000)

        event.accept()


# ================== 启动程序 ==================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置应用字体
    app_font = QFont("Microsoft YaHei", 10)
    app.setFont(app_font)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_forever()