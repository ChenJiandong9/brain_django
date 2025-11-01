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
                elif data['type'] == 'imported_data':
                    await self.handle_imported_data(data)
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
                # 处理字典格式数据
                formatted_data = f"Delta {eeg_data.get('Delta', 0)} Theta {eeg_data.get('Theta', 0)} Alpha {eeg_data.get('Alpha', 0)} Beta {eeg_data.get('Beta', 0)} Gamma {eeg_data.get('Gamma', 0)}"
            elif isinstance(eeg_data, str):
                # 处理字符串格式数据（来自蓝牙设备的原始数据）
                # 检查是否为TGAM数据包格式
                if eeg_data.startswith('AA AA'):
                    # 解析TGAM数据包
                    formatted_data = self._parse_tgam_data(eeg_data)
                else:
                    # 直接使用字符串数据
                    formatted_data = eeg_data
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

    def _parse_tgam_data(self, raw_data):
        """
        解析TGAM数据包格式
        根据text1.py中的TGAMDataCollector._parse_packet方法实现
        """
        try:
            # 简化的TGAM数据解析（实际应用中需要更复杂的解析逻辑）
            parts = raw_data.split()
            
            # 查找各个频段的值
            eeg_bands = {
                'Delta': 0,
                'Theta': 0,
                'Alpha': 0,
                'Beta': 0,
                'Gamma': 0
            }
            
            # 解析数据
            for i, part in enumerate(parts):
                if part == 'Delta' and i + 1 < len(parts):
                    eeg_bands['Delta'] = int(parts[i + 1])
                elif part == 'Theta' and i + 1 < len(parts):
                    eeg_bands['Theta'] = int(parts[i + 1])
                elif part == 'Alpha' and i + 1 < len(parts):
                    eeg_bands['Alpha'] = int(parts[i + 1])
                elif part == 'Beta' and i + 1 < len(parts):
                    eeg_bands['Beta'] = int(parts[i + 1])
                elif part == 'Gamma' and i + 1 < len(parts):
                    eeg_bands['Gamma'] = int(parts[i + 1])
            
            # 格式化为标准格式
            return f"Delta {eeg_bands['Delta']} Theta {eeg_bands['Theta']} Alpha {eeg_bands['Alpha']} Beta {eeg_bands['Beta']} Gamma {eeg_bands['Gamma']}"
        except Exception as e:
            logger.error(f"TGAM数据解析失败: {str(e)}")
            return raw_data
 


    async def handle_analysis_request(self, data):
        """处理分析请求"""
        try:
            global current_log_file

            # 验证数据文件
            if not os.path.exists(current_log_file) or os.path.getsize(current_log_file) == 0:
                raise ValueError("无有效数据，请先采集数据")

            # 获取API密钥
            api_key = data.get('api_key', DEFAULT_API_KEY)
            logger.info(f"正在分析数据: {current_log_file}")
            # 执行分析
            analyzer = EEGAnalyzer(current_log_file, api_key)
            report_content, report_path = analyzer.analyze()

            # 分析后轮换日志
            create_new_log_file()

            # 返回结果 
            print(f"分析结果保存在: {report_path}")
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
    # async def handle_imported_data(self, data):
    #     """处理导入的数据文件"""
    #     try:
    #         file_path = data.get('filePath', '')
    #         if not file_path or not os.path.exists(file_path):
    #             raise ValueError("导入的文件不存在")
            
    #         global current_log_file
    #         current_log_file = file_path
            
    #         await self.send(text_data=json.dumps({
    #             'type': 'import_success',
    #             'file_path': file_path
    #         }))
            
    #     except Exception as e:
    #         error_msg = str(e)
    #         logger.error(f"导入数据处理失败: {error_msg}")
    #         await self.send(text_data=json.dumps({
    #             'type': 'error',
    #             'message': error_msg
    #         }))
