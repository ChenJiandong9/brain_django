import os
import pandas as pd
import textwrap
from datetime import datetime

# 使用火山引擎SDK
try:
    from volcenginesdkarkruntime import Ark
except ImportError:
    class Ark:
        def __init__(self, api_key):
            pass
            
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    class MockResponse:
                        class Choice:
                            class Message:
                                content = "<p>这是一个模拟的AI分析结果。要获得真实的分析结果，请安装volcenginesdkarkruntime库并配置正确的API密钥。</p>"
                            message = Message()
                        choices = [Choice()]
                    return MockResponse()

import logging

logger = logging.getLogger(__name__)


class EEGAnalyzer:
    def __init__(self, file_path, api_key):
        self.file_path = file_path
        self.api_key = api_key
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 确保分析报告目录存在
        if not os.path.exists("analysis_reports"):
            os.makedirs("analysis_reports")
            
        self.report_path = os.path.join("analysis_reports", f"report_{self.timestamp}.html")

    def analyze(self):
        """执行完整分析流程"""
        # 加载数据
        df = self._load_data()
        if df.empty:
            raise ValueError("数据加载失败或为空")

        # 生成统计与睡眠分析
        stats = self._generate_stats(df)
        sleep_analysis = self._analyze_sleep(df)

        # 调用火山引擎API获取AI分析（核心调用）
        ai_content = self.call_volcengine_api(
            self.api_key,
            textwrap.dedent(f"""
            作为睡眠专家，请分析以下脑电数据：
            1. 统计数据：{stats}
            2. 睡眠阶段：{sleep_analysis}
            生成专业HTML报告，包含睡眠质量评估和建议。
            标题一和标题二都是白色
            重要内容用<strong>加粗</strong>，问题用<span style="color:red">红色</span>标记。
            生成速度要快，在一分钟之内，必须保证速度
            """)
        )

        # 生成完整报告
        report_content = self._generate_report(df, stats, sleep_analysis, ai_content)
         
        with open(self.report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            print(f"报告已保存到{self.report_path}")

        return report_content, os.path.basename(self.report_path)

    def _load_data(self):
        """加载并解析EEG数据"""
        data = []
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if ' - ' not in line:
                        continue
                    timestamp, raw_data = line.strip().split(' - ', 1)
                    data.append({
                        '时间': timestamp,
                        'Delta': self._extract_band(raw_data, 0),
                        'Theta': self._extract_band(raw_data, 1),
                        'Alpha': self._extract_band(raw_data, 2),
                        'Beta': self._extract_band(raw_data, 3),
                        'Gamma': self._extract_band(raw_data, 4),
                    })
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"数据加载错误: {str(e)}")
            return pd.DataFrame()

    def _extract_band(self, raw_data, index):
        """提取脑电波频段数据"""
        try:
            parts = raw_data.split()
            # 查找频段名称的位置，然后获取其后的数值
            band_names = ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']
            band_name = band_names[index]
            
            for i, part in enumerate(parts):
                if part.startswith(band_name) and i + 1 < len(parts):
                    # 尝试将下一个部分转换为数字
                    value_part = parts[i + 1]
                    # 如果是十六进制格式
                    if value_part.startswith('0x'):
                        return int(value_part, 16)
                    # 如果是十进制格式
                    else:
                        try:
                            return int(value_part)
                        except ValueError:
                            return float(value_part)
            # 如果找不到特定格式，使用原来的方法作为备选
            return int(parts[10 + index], 16) if len(parts) > 10 + index else 0
        except:
            return 0

    def _generate_stats(self, df):
        """生成统计数据HTML"""
        stats = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].describe().loc[['mean', 'std']]
        html = "<table class='stats-table'>"
        html += "<tr><th>频段</th><th>平均值</th><th>标准差</th></tr>"
        for band in stats.columns:
            html += f"<tr><td>{band}</td><td>{stats[band]['mean']:.1f}</td><td>{stats[band]['std']:.1f}</td></tr>"
        html += "</table>"
        return html

    def _analyze_sleep(self, df):
        """分析睡眠阶段"""
        total = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].sum().sum()
        if total == 0:
            return "<p>无有效睡眠数据</p>"

        pct = df[['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']].sum() / total * 100
        return textwrap.dedent(f"""
        <div>
            <p>深睡期(Delta): {pct['Delta']:.1f}%</p>
            <p>浅睡期(Theta): {pct['Theta']:.1f}%</p>
            <p>REM期(Alpha): {pct['Alpha']:.1f}%</p>
        </div>
        """)

    def _generate_report(self, df, stats, sleep_analysis, ai_content):
        """生成完整HTML报告"""
        return textwrap.dedent(f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <title>睡眠分析报告 {self.timestamp}</title>
                <style>
                    .stats-table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                    .stats-table th, .stats-table td {{ border: 1px solid #ddd; padding: 8px; }}
                </style>
            </head>
            <body>
                <h1>睡眠分析报告</h1>
                <h2>数据统计</h2>{stats}
                <h2>睡眠阶段分析</h2>{sleep_analysis}
                <h2>AI评估</h2>{ai_content}
            </body>
        </html>
        """)

    def call_volcengine_api(self, api_key, prompt, model="doubao-seed-1-6-lite-251015"):
        """
        封装火山引擎大模型API调用，按照backlend.py的方式
        """
        try:
            # 使用api_key参数初始化客户端，确保正确传递API密钥
            client = Ark(api_key=api_key)

            # 构造请求
            messages = [{"role": "user", "content": prompt}]

            # 调用API
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                timeout=100
            )

            return response.choices[0].message.content

        except Exception as e:
            error_msg = f"火山引擎API调用失败: {str(e)}"
            logger.error(error_msg)
            return f"<p class='text-red-600'>{error_msg}</p>"