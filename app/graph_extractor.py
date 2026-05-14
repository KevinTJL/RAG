# app/graph_extractor.py
import json
import re
from app.ollama_client import OllamaClient

EXTRACT_PROMPT = """你是一个专业的知识图谱抽取专家。
请从以下文本段落中提取出核心的实体及其关系（三元组），并严格以JSON数组的格式输出，绝不要包含任何其他解释文字。
JSON格式要求如下：[{{"h": "头实体/主语", "r": "关系/谓语", "t": "尾实体/宾语"}}]
如果文本中没有明显的关系事实，请输出空数组 []。

示例：
文本：主成分分析（PCA）是一种常用的数据降维技术，属于无监督学习。
输出：[{{"h": "主成分分析(PCA)", "r": "是一种", "t": "数据降维技术"}}, {{"h": "主成分分析(PCA)", "r": "属于", "t": "无监督学习"}}]

文本内容：
{text}
"""

def extract_triplets(text: str) -> list[dict]:
    client = OllamaClient()
    user_msg = EXTRACT_PROMPT.format(text=text)
    
    try:
        response = client.chat(
            messages=[{"role": "user", "content": user_msg}]
        )
        
        # 因为3B模型有时比较啰嗦，我们需要用正则表达式强行扣出被框住的 JSON 数据
        match = re.search(r"```json(.*?)```", response, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
        else:
            json_str = response.strip()
            
        start_idx = json_str.find("[")
        end_idx = json_str.rfind("]") + 1
        
        if start_idx != -1 and end_idx != -1:
            clean_json = json_str[start_idx:end_idx]
            triplets = json.loads(clean_json)
            return triplets
        return []
    except Exception as e:
        # 如遇模型输出乱码或超时则跳过错误不中断程序
        return []