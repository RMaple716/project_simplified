"""
批量修复脚本：
1. 城市坐标字典增加省份映射
2. build_daily_slot_plan 改为循环复用
3. 空天补全逻辑
"""
import re

def fix_integration_py():
    with open('src/routes/integration.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # ===== 修改1: 城市坐标字典 =====
    old_dict_marker = '"沈阳": {"lat": 41.8057, "lng": 123.4315},\n    }'
    new_provinces = '''"沈阳": {"lat": 41.8057, "lng": 123.4315},
        # 省份/地区 → 代表性城市坐标
        "广西": {"lat": 25.2736, "lng": 110.2900},
        "广西壮族自治区": {"lat": 25.2736, "lng": 110.2900},
        "广东": {"lat": 23.1291, "lng": 113.2644},
        "福建": {"lat": 24.4798, "lng": 118.0894},
        "浙江": {"lat": 30.2741, "lng": 120.1551},
        "江苏": {"lat": 32.0603, "lng": 118.7969},
        "四川": {"lat": 30.5728, "lng": 104.0668},
        "云南": {"lat": 25.0389, "lng": 102.7183},
        "陕西": {"lat": 34.3416, "lng": 108.9398},
        "湖南": {"lat": 28.2282, "lng": 112.9388},
        "湖北": {"lat": 30.5928, "lng": 114.3055},
        "山东": {"lat": 36.0671, "lng": 120.3826},
        "海南": {"lat": 18.2528, "lng": 109.5120},
        "黑龙江": {"lat": 45.8038, "lng": 126.5350},
        "辽宁": {"lat": 38.9140, "lng": 121.6147},
        "河南": {"lat": 34.7466, "lng": 113.6254},
        "河北": {"lat": 38.0428, "lng": 114.5149},
        "山西": {"lat": 37.8706, "lng": 112.5489},
        "江西": {"lat": 28.6829, "lng": 115.8582},
        "安徽": {"lat": 31.8206, "lng": 117.2272},
        "贵州": {"lat": 26.6470, "lng": 106.6302},
        "甘肃": {"lat": 36.0611, "lng": 103.8343},
        "内蒙古": {"lat": 40.8174, "lng": 111.7652},
        "新疆": {"lat": 43.7928, "lng": 87.6284},
        "西藏": {"lat": 29.6500, "lng": 91.1000},
        "宁夏": {"lat": 38.4713, "lng": 106.2630},
        "青海": {"lat": 36.6208, "lng": 101.7794},
        "台湾": {"lat": 25.0330, "lng": 121.5645},
        "香港": {"lat": 22.3193, "lng": 114.1694},
        "澳门": {"lat": 22.1987, "lng": 113.5439},
    }'''

    if old_dict_marker in content:
        content = content.replace(old_dict_marker, new_provinces)
        print('✅ 修改1: 城市坐标字典已更新')
    else:
        print('❌ 修改1: 未找到原字典末尾标记')
        # 尝试查找"沈阳"行
        idx = content.find('"沈阳": {"lat": 41.8057, "lng": 123.4315}')
        if idx >= 0:
            print(f'   找到"沈阳"行在位置 {idx}')
            # 确保后面是"    }"
            end_brace = content.find('    }', idx)
            if end_brace > 0 and end_brace - idx < 200:
                old_section = content[idx:end_brace+6]
                print(f'   原内容片段: ...{old_section[:50]}...')
                content = content.replace(old_section, new_provinces)
                print('✅ 修改1: 通过"沈阳"行替换成功')
            else:
                print(f'   end_brace={end_brace}, idx={idx}')
        else:
            print(f'   也没有找到"沈阳"行')

    # ===== 修改2: build_daily_slot_plan =====
    old_func = '''    # 将每个时段的景点轮询分配到每天（每天每个时段最多1个，景点不够的天该时段留空）
    # 例如：6个 morning 景点分到10天 → 第1-6天每天1个，第7-10天没有 morning 景点
    def build_daily_slot_plan(slot_attractions: list, total_days: int) -> list:
        """将景点列表依次分配到每天，返回长度为 total_days 的列表，每项是景点或None"""
        result = [None] * total_days
        for i, attr in enumerate(slot_attractions):
            if i < total_days:
                result[i] = attr
        return result'''

    new_func = '''    # 将每个时段的景点循环分配到每天（每天每个时段最多1个，景点不够时循环复用）
    # 例如：只有2个 morning 景点但行程5天 → 第1天=A,第2天=B,第3天=A,第4天=B,第5天=A
    def build_daily_slot_plan(slot_attractions: list, total_days: int) -> list:
        """将景点列表循环分配到每天（景点不足时重复使用），确保每天都有景点安排"""
        result = [None] * total_days
        if not slot_attractions:
            return result
        for i in range(total_days):
            result[i] = slot_attractions[i % len(slot_attractions)]
        return result'''

    if old_func in content:
        content = content.replace(old_func, new_func)
        print('✅ 修改2: build_daily_slot_plan 已改为循环分配')
    else:
        print('❌ 修改2: 未找到原函数，尝试模糊匹配...')
        # 查找 def build_daily_slot_plan
        idx = content.find('def build_daily_slot_plan')
        if idx >= 0:
            print(f'   找到定义在位置 {idx}')
            # 找到函数结束位置（下一个 def 或下一个非缩进行）
            end_idx = content.find('\ndef ', idx + 5)
            if end_idx < 0:
                end_idx = content.find('\n\n', idx)
            if end_idx < 0:
                end_idx = idx + 800
            old_func_block = content[idx:end_idx]
            print(f'   原函数体: {old_func_block[:100]}...')
            content = content.replace(old_func_block, '''    def build_daily_slot_plan(slot_attractions: list, total_days: int) -> list:
        """将景点列表循环分配到每天（景点不足时重复使用），确保每天都有景点安排"""
        result = [None] * total_days
        if not slot_attractions:
            return result
        for i in range(total_days):
            result[i] = slot_attractions[i % len(slot_attractions)]
        return result''')
            print('✅ 修改2: 通过模糊匹配替换成功')

    # ===== 修改3: 空天补全逻辑 =====
    # 查找 "has_activities = len(day_attractions) > 0" 后面的 notes 逻辑
    # 然后在 day_plan = { 之前插入补全逻辑
    marker = '            notes += "，自由活动日，可自由探索城市或休息"   '
    if marker in content:
        insertion = '''            notes += "，自由活动日，可自由探索城市或休息"
        # 如果没有景点但需要住宿，至少保留住宿信息
        if day == 1 and hotels_data and not day_hotel:
            day_hotel = hotels_data[0].copy()
            day_hotel["check_in_date"] = date_str
            daily_cost += day_hotel.get("price_per_night", 0)
        # 如果没有景点也没有交通，提供默认交通建议
        if not day_transport and not has_activities:
            day_transport = {
                "transport_id": f"trans_free_{day}",
                "from": "酒店",
                "to": "市区",
                "type": "步行",
                "duration": 15,
                "duration_text": "15分钟",
                "distance": 1000,
                "distance_text": "1.0公里",
                "price": 0,
                "departure_time": "10:00"
            }'''
        content = content.replace(marker, insertion)
        print('✅ 修改3: 空天补全逻辑已添加')
    else:
        print('❌ 修改3: 未找到目标标记，尝试其他方式...')
        # 查找 "自由活动日" 相关代码
        idx = content.find('自由活动日，可自由探索城市或休息')
        if idx >= 0:
            # 找到这行末尾的换行符
            end_line = content.find('\n', idx)
            line_before = content[:end_line+1]
            insertion = '''\n        # 如果没有景点但需要住宿，至少保留住宿信息
        if day == 1 and hotels_data and not day_hotel:
            day_hotel = hotels_data[0].copy()
            day_hotel["check_in_date"] = date_str
            daily_cost += day_hotel.get("price_per_night", 0)
        # 如果没有景点也没有交通，提供默认交通建议
        if not day_transport and not has_activities:
            day_transport = {
                "transport_id": f"trans_free_{day}",
                "from": "酒店",
                "to": "市区",
                "type": "步行",
                "duration": 15,
                "duration_text": "15分钟",
                "distance": 1000,
                "distance_text": "1.0公里",
                "price": 0,
                "departure_time": "10:00"
            }'''
            content = content[:end_line+1] + insertion + content[end_line+1:]
            print('✅ 修改3: 通过模糊匹配插入成功')
        else:
            print('❌ 修改3: 也未找到"自由活动日"文本')

    # 写入
    with open('src/routes/integration.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('✅ 文件已保存')


if __name__ == '__main__':
    fix_integration_py()
