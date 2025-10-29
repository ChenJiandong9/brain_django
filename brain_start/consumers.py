import json
import os
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from .eeg_analyzer import EEGAnalyzer

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局日志文件管理
current_log_file = None
LOG_DIR = "logs"
ANALYSIS_DIR = "analysis_reports"
DEFAULT_API_KEY = "51e09aa5-d2dd-41ab-bf91-51ef798844e7"

def init_log_file():
    """初始化日志文件"""
    global current_log_file
    # 确保日志目录存在
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    current_log_file = os.path.join(LOG_DIR, f"eeg_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")


def create_new_log_file():
    """创建新日志文件"""
    global current_log_file
    # 确保日志目录存在
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    new_file = os.path.join(LOG_DIR, f"eeg_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    current_log_file = new_file
    return new_file


# 初始化日志文件
init_log_file()


class EEGDataConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        pass

 
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            # 根据消息类型处理不同事件
            if 'type' in data:
                if data['type'] == 'eeg_data':
                    await self.handle_eeg_data(data)
                elif data['type'] == 'request_analysis':
                    await self.handle_analysis_request(data)
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def handle_eeg_data(self, data):
        """处理EEG数据"""
        try:
            global current_log_file

            # 日志文件轮换（5MB）
            if not os.path.exists(current_log_file) or os.path.getsize(current_log_file) > 1024 * 1024 * 5:
                create_new_log_file()

            # 写入数据，格式化为与分析器兼容的格式
            eeg_data = data.get('data', {})
            if isinstance(eeg_data, dict):
                formatted_data = f"Delta {eeg_data.get('Delta', 0)} Theta {eeg_data.get('Theta', 0)} Alpha {eeg_data.get('Alpha', 0)} Beta {eeg_data.get('Beta', 0)} Gamma {eeg_data.get('Gamma', 0)}"
            else:
                formatted_data = str(eeg_data)
            
            with open(current_log_file, "a", encoding="utf-8") as f:
                f.write(f"{data['timestamp']} - {formatted_data}\n")
            logger.info(f"写入数据: {data['timestamp']}")
            
            # 发送确认消息
            await self.send(text_data=json.dumps({
                'type': 'data_received',
                'timestamp': data['timestamp']
            }))

        except Exception as e:
            logger.error(f"数据处理失败: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'data_error',
                'error': str(e)
            }))

    async def handle_analysis_request(self, data):
        """处理分析请求"""
        try:
            global current_log_file

            # 验证数据文件
            if not os.path.exists(current_log_file) or os.path.getsize(current_log_file) == 0:
                raise ValueError("无有效数据，请先采集数据")

            # 获取API密钥
            api_key = data.get('api_key', DEFAULT_API_KEY)

            # 执行分析
            analyzer = EEGAnalyzer(current_log_file, api_key)
            report_content, report_path = analyzer.analyze()

            # 分析后轮换日志
            create_new_log_file()

            # 返回结果
            await self.send(text_data=json.dumps({
                'type': 'analysis_result',
                'success': True,
                'content': report_content,
                'path': report_path
            }))

        except Exception as e:
            error_msg = str(e)
            logger.error(f"分析请求失败: {error_msg}")
            await self.send(text_data=json.dumps({
                'type': 'analysis_result',
                'success': False,
                'error': error_msg
            }))