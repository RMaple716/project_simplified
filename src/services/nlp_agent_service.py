"""
NLP智能提取服务 - 使用DeepSeek大模型从自然语言中提取结构化旅游需求信息

该服务替代原有的纯正则匹配方案，使用大模型理解用户复杂多样的自然语言表达，
提取出准确的字段名称和值，直接用于前端表单填充。
"""
import json
from typing import Dict, Any, Optional
from src.services.deepseek_client import DeepSeekClient


class NLPAgentService:
    """NLP智能提取服务"""

    def __init__(self):
        self.client = DeepSeekClient()

    async def extract_travel_info(self, text: str) -> Dict[str, Any]:
        """
        使用大模型从自然语言中提取旅游需求信息

        Args:
            text: 用户输入的自然语言描述

        Returns:
            提取的结构化信息字典，包含以下字段:
            - city: 目的地城市
            - attraction: 景点
            - budget: 预算（数字）
            - transport: 交通方式
            - depart_time: 出发时间（自然语言描述）
            - people: 人数（数字）
            - travel_days: 出行天数（数字）
            - preferences: 偏好列表
            - travel_type: 出行类型
        """
        system_prompt = """你是一个专业的旅游需求信息提取助手。你的任务是分析用户的自然语言输入，提取出结构化的旅游需求信息。

请仔细理解用户的描述，提取以下字段（如果没有相关信息，字段值设为 null）:

1. city: 目的地城市名称（如"北京"、"上海"、"西安"等）
2. attraction: 要去的景点名称（如"兵马俑"、"故宫"、"西湖"等）
3. budget: 总预算（纯数字，单位元，如 2500）
4. transport: 交通方式（如"飞机"、"高铁"、"自驾"、"火车"等）
5. depart_time: 出发时间描述（保留用户可以理解的自然语言，如"下周五"、"明天"、"3月15日"等）
6. people: 出行人数（纯数字）
7. travel_days: 出行天数（纯数字）
8. preferences: 偏好列表（数组，如 ["历史古迹", "美食探索", "自然风光"]）
9. travel_type: 出行类型（枚举值: "leisure"休闲游、"family"家庭游、"adventure"探险游、"business"商务游、"culture"文化游）

重要规则:
- 认真理解用户的每一个需求描述，不要遗漏信息
- 如果用户描述模糊，根据常识合理推断
- 金额单位统一为人民币元
- 人数要准确提取，如"两个人"→2，"一家三口"→3
- 天数要准确提取，如"三天"→3，"一周"→7
- 输出必须是合法的JSON格式，不要包含多余的解释文字

示例:
输入: "下周五去西安看兵马俑，两个人，预算两千五"
输出: {{"city": "西安", "attraction": "兵马俑", "budget": 2500, "transport": null, "depart_time": "下周五", "people": 2, "travel_days": null, "preferences": [], "travel_type": null}}

输入: "我想去北京玩，故宫和长城，一家四口，预算1万，玩五天"
输出: {{"city": "北京", "attraction": "故宫", "budget": 10000, "transport": null, "depart_time": null, "people": 4, "travel_days": 5, "preferences": ["历史古迹"], "travel_type": "culture"}}

输入: "明天坐高铁去上海玩三天，预算三千，一个人去迪士尼"
输出: {{"city": "上海", "attraction": "迪士尼", "budget": 3000, "transport": "高铁", "depart_time": "明天", "people": 1, "travel_days": 3, "preferences": [], "travel_type": "leisure"}}

输入: "暑假带爸妈去成都，预算五千，玩四天，喜欢美食和自然风光"
输出: {{"city": "成都", "attraction": null, "budget": 5000, "transport": null, "depart_time": "暑假", "people": 3, "travel_days": 4, "preferences": ["美食探索", "自然风光"], "travel_type": "family"}}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请提取以下旅游需求的详细信息：\n\n{text}"}
        ]

        content = ""
        try:
            response = await self.client.chat_completion(
                messages=messages,
                model="deepseek-chat",
                temperature=0.1,  # 低温度以提高提取的准确性和一致性
            )

            content = response["choices"][0]["message"]["content"]

            # 清理可能存在的 Markdown 代码块标记
            content = content.strip()
            if content.startswith("```"):
                # 移除代码块标记
                lines = content.split("\n")
                content_lines = []
                for line in lines:
                    if line.strip().startswith("```"):
                        continue
                    content_lines.append(line)
                content = "\n".join(content_lines)

            result = json.loads(content.strip())

            # 确保所有字段都存在
            default_result = {
                "city": None,
                "attraction": None,
                "budget": None,
                "transport": None,
                "depart_time": None,
                "people": None,
                "travel_days": None,
                "preferences": [],
                "travel_type": None,
            }
            default_result.update(result)

            # 类型修正
            if default_result["budget"] is not None:
                try:
                    default_result["budget"] = int(float(default_result["budget"]))
                except (ValueError, TypeError):
                    default_result["budget"] = None

            if default_result["people"] is not None:
                try:
                    default_result["people"] = int(float(default_result["people"]))
                except (ValueError, TypeError):
                    default_result["people"] = None

            if default_result["travel_days"] is not None:
                try:
                    default_result["travel_days"] = int(float(default_result["travel_days"]))
                except (ValueError, TypeError):
                    default_result["travel_days"] = None

            if not isinstance(default_result["preferences"], list):
                default_result["preferences"] = []

            # 保留 departs_time 字段名兼容
            if "departs_time" in result and default_result["depart_time"] is None:
                default_result["depart_time"] = result["departs_time"]

            return default_result

        except json.JSONDecodeError as e:
            raise ValueError(f"大模型返回的JSON格式不正确: {e}\n原始内容: {content}")
        except KeyError as e:
            raise ValueError(f"大模型响应结构异常: {e}")
        except Exception as e:
            raise ValueError(f"智能提取失败: {str(e)}")


# 单例模式
nlp_agent_service = NLPAgentService()
