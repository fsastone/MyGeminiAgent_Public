# services/gemini_ai.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def initialize_gemini(tools_list):
    """
    初始化 Gemini 模型並綁定工具。
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 未設定！")
    
    genai.configure(api_key=api_key)
    # 使用目前的 Flash 模型
    model = genai.GenerativeModel('gemini-2.5-flash', tools=tools_list)
    return model