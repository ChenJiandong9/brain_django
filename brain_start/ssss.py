#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
火山方舟API调用Demo
演示如何调用火山方舟大模型API
"""

import json
import requests
import sys
import os

class VolcengineArkDemo:
    """火山方舟API调用演示类"""
    
    def __init__(self, api_key):
        """
        初始化
        
        Args:
            api_key (str): 火山引擎API密钥
        """
        self.api_key = api_key
        # 火山方舟API endpoint
        self.api_endpoint = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        
    def call_ark_api(self, model, prompt, max_tokens=500):
        """
        调用火山方舟API
        
        Args:
            model (str): 模型名称
            prompt (str): 提示词
            max_tokens (int): 最大返回token数
            
        Returns:
            str: API响应结果
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(
                self.api_endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                return f"API调用失败: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"请求异常: {str(e)}"
    
    def demo_chat(self):
        """演示对话功能"""
        print("=== 火山方舟API调用Demo ===")
        print("模型: doubao-1.5-thinking-pro-250415")
        print("输入 'quit' 或 'exit' 退出程序\n")
        
        model = "doubao-seed-1-6-lite-251015"

        
        while True:
            user_input = input("请输入您的问题: ").strip()
            
            if user_input.lower() in ['quit', 'exit']:
                print("再见!")
                break
                
            if not user_input:
                continue
                
            print("正在调用API...")
            response = self.call_ark_api(model, user_input)
            print(f"AI回答: {response}\n")

def main():
    """主函数"""
    # 请替换为你的实际API密钥
    api_key = "51e09aa5-d2dd-41ab-bf91-51ef798844e7"
    
    if api_key == "your-api-key-here":
        print("请先设置你的火山引擎API密钥")
        api_key = input("请输入API密钥: ").strip()
        
    if not api_key:
        print("API密钥不能为空")
        return
    
    # 创建demo实例
    demo = VolcengineArkDemo(api_key)
    
    # 简单测试
    print("=== 简单测试 ===")
    test_prompt = "请用一句话介绍人工智能"
    print(f"测试问题: {test_prompt}")
    
    response = demo.call_ark_api("doubao-seed-1-6-lite-251015", test_prompt)
    print(f"AI回答: {response}\n")
    
    # 交互式对话
    try:
        demo.demo_chat()
    except KeyboardInterrupt:
        print("\n程序已退出")

if __name__ == "__main__":
    main()

#     Doubao-Seed-1.6-lite
# Doubao-Seed-1.6-liteDoubao-Seed-1.6-lite
# ｜
# 251015