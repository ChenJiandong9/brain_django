from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import os
import json
import logging
from datetime import datetime
import pandas as pd

# 添加对 EEGAnalyzer 的导入
from .eeg_analyzer import EEGAnalyzer

logger = logging.getLogger(__name__)

def runoob(request):
    context = {}
    context['hello'] = 'Hello World!'
    return render(request, 'EEG.html', context)
def eeg(request):
    context = {}
    context['hello'] = 'EEG Page!'
    return render(request, 'EEG.html', context)


def serve_report(request, filename):
    """提供报告访问"""
    try:
        report_file = os.path.join("analysis_reports", filename)
        if not os.path.exists(report_file):
            return JsonResponse({'error': '报告不存在'}, status=404)

        with open(report_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return HttpResponse(content, content_type='text/html; charset=utf-8')

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




@csrf_exempt
def import_eeg_data(request):
    """处理导入的EEG数据"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '只支持POST请求'}, status=400)
    
    try:
        # 确保日志目录存在
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 生成日志文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f"imported_eeg_data_{timestamp}.txt")
        
        # 获取API密钥（如果提供了的话）
        api_key = "51e09aa5-d2dd-41ab-bf91-51ef798844e7"
        if request.content_type == 'application/json':
            try:
                json_data = json.loads(request.body)
                api_key = json_data.get('api_key', api_key)
            except:
                pass
        
        # 获取上传的文件
        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            
            # 根据文件扩展名处理
            if uploaded_file.name.endswith(('.csv', '.txt')):
                # CSV/文本文件处理
                try:
                    # 尝试以UTF-8编码读取
                    file_content = uploaded_file.read().decode('utf-8')
                except UnicodeDecodeError:
                    # 如果UTF-8失败，尝试以GBK编码读取
                    uploaded_file.seek(0)  # 重置文件指针
                    file_content = uploaded_file.read().decode('gbk')
                
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                message = f"成功导入文本文件: {uploaded_file.name}"
                
            elif uploaded_file.name.endswith(('.xls', '.xlsx')):
                # Excel文件处理
                try:
                    # 读取Excel文件
                    df = pd.read_excel(uploaded_file)
                    
                    # 转换为文本格式保存
                    with open(log_file, 'w', encoding='utf-8') as f:
                        # 将DataFrame转换为文本格式
                        for index, row in df.iterrows():
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            # 查找包含脑电波频段的列
                            delta_col = None
                            theta_col = None
                            alpha_col = None
                            beta_col = None
                            gamma_col = None
                            
                            # 查找精确匹配的列名
                            for col in df.columns:
                                col_lower = str(col).lower()
                                if 'delta' in col_lower:
                                    delta_col = col
                                elif 'theta' in col_lower:
                                    theta_col = col
                                elif 'alpha' in col_lower:
                                    alpha_col = col
                                elif 'beta' in col_lower:
                                    beta_col = col
                                elif 'gamma' in col_lower:
                                    gamma_col = col
                            
                            # 如果找到了所有需要的列
                            if all([delta_col, theta_col, alpha_col, beta_col, gamma_col]):
                                data_str = f"Delta {row[delta_col]} Theta {row[theta_col]} Alpha {row[alpha_col]} Beta {row[beta_col]} Gamma {row[gamma_col]}"
                                f.write(f"{timestamp} - {data_str}\n")
                            else:
                                # 尝试使用默认列名
                                if all(col in df.columns for col in ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma']):
                                    data_str = f"Delta {row['Delta']} Theta {row['Theta']} Alpha {row['Alpha']} Beta {row['Beta']} Gamma {row['Gamma']}"
                                    f.write(f"{timestamp} - {data_str}\n")
                                else:
                                    # 如果还是找不到合适的列，将整行转换为字符串
                                    f.write(f"{timestamp} - {row.to_string()}\n")
                    
                    message = f"成功导入Excel文件: {uploaded_file.name}"
                except Exception as e:
                    logger.error(f"Excel文件处理失败: {str(e)}")
                    # 如果处理失败，保存原始文件内容
                    uploaded_file.seek(0)
                    file_content = uploaded_file.read().decode('utf-8', errors='ignore')
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(file_content)
                    message = f"导入Excel文件时出现错误，已保存原始内容: {uploaded_file.name}"
            else:
                # 其他文件类型直接保存
                file_content = uploaded_file.read().decode('utf-8', errors='ignore')
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                message = f"成功导入文件: {uploaded_file.name}"
        else:
            # 从请求体获取数据
            try:
                data = json.loads(request.body)
                api_key = data.get('api_key', api_key)
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(data, ensure_ascii=False, indent=2))
                message = "成功导入JSON数据"
            except json.JSONDecodeError:
                # 如果不是JSON数据，直接保存
                with open(log_file, 'wb') as f:
                    f.write(request.body)
                message = "成功导入原始数据"
        
        # 只保存数据，不立即进行分析
        return JsonResponse({
            'status': 'success', 
            'message': message,
            'file_path': log_file
        })
        
    except Exception as e:
        logger.error(f"导入数据失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def analyze_existing_data(request):
    """分析已有的数据文件"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '只支持POST请求'}, status=400)
    
    try:
        data = json.loads(request.body)
        file_path = data.get('file_path')
        api_key = data.get('api_key', '51e09aa5-d2dd-41ab-bf91-51ef798844e7')
        
        if not file_path or not os.path.exists(file_path):
            return JsonResponse({'status': 'error', 'message': '指定的文件不存在'}, status=400)
        
        # 执行分析
        print("开始分析数据...")
        analyzer = EEGAnalyzer(file_path, api_key)
        report_content, report_filename = analyzer.analyze()
        
        return JsonResponse({
            'status': 'success',
            'report_filename': report_filename,
            'message': '分析完成'
        })
        
    except Exception as e:
        logger.error(f"分析数据失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
 
 
@csrf_exempt
def test_api_key(request):
    """测试API密钥有效性"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': '只支持POST请求'}, status=400)
    
    try:
        data = json.loads(request.body)
        api_key = data.get('api_key', '')
        
        if not api_key:
            return JsonResponse({'status': 'error', 'message': 'API密钥不能为空'}, status=400)
        
        # 使用一个简单的测试提示来验证API密钥
        analyzer = EEGAnalyzer("", api_key)
        test_prompt = "请回复'测试成功'这四个字，不要包含其他内容。"
        
        # 尝试调用API
        response = analyzer.call_volcengine_api(api_key, test_prompt, "doubao-seed-1-6-lite-251015")  # 使用较轻量的模型进行测试
        
        # 检查响应是否包含错误
        if "火山引擎API调用失败" in response:
            return JsonResponse({'status': 'error', 'message': 'API密钥无效或连接失败'}, status=400)
        
        return JsonResponse({'status': 'success', 'message': 'API密钥验证成功'})
        
    except Exception as e:
        logger.error(f"API密钥测试失败: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'测试失败: {str(e)}'}, status=500)