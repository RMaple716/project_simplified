"""
自然语言旅游需求提取服务
"""
import re
import unicodedata
import jieba.posseg as pseg
import jieba

class TravelExtractor:
    def __init__(self, cities=None, attractions=None):
        """
        cities: 城市/省份/地区白名单（如 {"西安","湖南","成都"}），用于识别城市。
        attractions: 具体景点/地标白名单（如 {"兵马俑","衡山","迪士尼"}），用于识别景点。
        如果不提供，则完全依赖 jieba 词性标注 + 动词模式推断。
        """
        self.transport_map = {
            "飞机": "飞机", "机票": "飞机", "飞": "飞机",
            "高铁": "高铁", "动车": "高铁",
            "火车": "火车", "列车": "火车",
            "自驾": "自驾", "开车": "自驾",
            "巴士": "巴士", "大巴": "巴士"
        }

        # 白名单（可选，极大提高准确率）
        self.city_set = set(cities) if cities else set()
        self.attraction_set = set(attractions) if attractions else set()

        # 将白名单词加入 jieba 以辅助分词和词性
        for w in self.city_set:
            jieba.add_word(w, tag='ns')      # ns: 地名
        for w in self.attraction_set:
            jieba.add_word(w, tag='nz')      # nz: 其他专名（或用 ns，但 nz 便于区分）

        self.stop_dest = {"一下", "看看", "一个", "这个", "那个", "什么", "怎么", "哪里"}

    def _basic_clean(self, text):
        text = unicodedata.normalize('NFKC', text)
        result = []
        for ch in text:
            code = ord(ch)
            if 0xFF01 <= code <= 0xFF5E:
                ch = chr(code - 0xFEE0)
            elif code == 0x3000:
                ch = ' '
            result.append(ch)
        text = ''.join(result)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _parse_chinese_number(self, cn_str):
        digit = {'零':0, '一':1, '二':2, '两':2, '三':3, '四':4,
                 '五':5, '六':6, '七':7, '八':8, '九':9}
        unit = {'十':10, '百':100, '千':1000, '万':10000, '亿':100000000}
        cn = re.sub(r'[^一二两三四五六七八九十百千万亿零]', '', cn_str)
        total, section, num, last_unit = 0, 0, 0, None
        for i, ch in enumerate(cn):
            if ch in digit:
                num = digit[ch]
                if i == len(cn)-1 and last_unit:
                    if last_unit >= 10000: num *= 1000
                    elif last_unit >= 1000: num *= 100
                    elif last_unit >= 100: num *= 10
            elif ch in unit:
                u = unit[ch]
                if u >= 10000:
                    if num == 0: num = 1
                    section = (section + num) * u
                    total += section
                    section = 0; num = 0
                    last_unit = u
                else:
                    if num == 0: num = 1
                    section += num * u
                    num = 0; last_unit = u
            else: 
                return None
        total += section + num
        return total if total > 0 else None

    def _extract_city_and_attraction(self, text, words_with_pos):
        """
        返回 (city, attraction) 元组。
        策略：
        - 先找出所有"去/到/飞/抵达"引导的短语 → 优先提取城市
        - 再找出"看/玩/游/逛/参观"引导的短语 → 提取景点
        - 使用白名单增强准确性，若无白名单则依赖 jieba 词性
        """
        ns_words = [w.word for w in words_with_pos if w.flag == 'ns']
        nz_words = [w.word for w in words_with_pos if w.flag == 'nz']

        # 动词模式：城市类动词 vs 活动类动词
        city_verb_pat = re.compile(r'(去|到|飞|前往|抵达)\s*([\u4e00-\u9fa5a-zA-Z]+)')
        play_verb_pat = re.compile(r'(看|玩|游|逛|参观|爬|登)\s*([\u4e00-\u9fa5a-zA-Z]+)')

        city_candidates = []
        for v, phrase in city_verb_pat.findall(text):
            phrase = re.sub(r'[，。！？、：；]', '', phrase.strip())
            city_candidates.append(phrase)

        attraction_candidates = []
        for v, phrase in play_verb_pat.findall(text):
            phrase = re.sub(r'[，。！？、：；]', '', phrase.strip())
            attraction_candidates.append(phrase)

        city = None
        attraction = None

        # 提取城市：优先从最后一个城市类动词短语中找白名单城市
        if self.city_set:
            for phrase in reversed(city_candidates):
                hits = [c for c in self.city_set if c in phrase]
                if hits:
                    city = max(hits, key=len)
                    break

        if not city and ns_words:
            # 使用 jieba ns 标签，且该词出现在城市类动词短语中
            for phrase in reversed(city_candidates):
                contained_ns = [ns for ns in ns_words if ns in phrase and ns not in self.attraction_set]
                if contained_ns:
                    city = max(contained_ns, key=len)
                    break

        if not city:
            # 兜底：第一个 ns 词（不能是已知景点）
            for ns in ns_words:
                if ns not in self.attraction_set:
                    city = ns
                    break

        if not city:
            # 无 ns 时，取最后一个城市动词短语（长度合理）
            for phrase in reversed(city_candidates):
                if phrase and phrase not in self.stop_dest and 1 < len(phrase) <= 10:
                    city = phrase
                    break

        # 提取景点：优先从活动类动词短语中找白名单景点
        if self.attraction_set:
            for phrase in reversed(attraction_candidates):
                hits = [a for a in self.attraction_set if a in phrase]
                if hits:
                    attraction = max(hits, key=len)
                    break

        if not attraction and (nz_words or ns_words):
            # 如果某个 ns/nz 出现在活动类短语中，且不是已确定的城市
            for phrase in reversed(attraction_candidates):
                contained = [w for w in nz_words + ns_words if w in phrase and w != city]
                if contained:
                    attraction = max(contained, key=len)
                    break

        if not attraction:
            # 如果活动类短语里啥都没，但整个句子中出现了景点白名单
            if self.attraction_set:
                for a in self.attraction_set:
                    if a in text and a != city:
                        attraction = a
                        break

        if not attraction:
            # 最后尝试：活动类短语本身（长度合理）
            # 但要排除天数表达（如"一天"、"三天"、"2天"等）
            # 以及包含天数的混合短语（如"故宫玩三天"）
            days_pattern = re.compile(r'^[一二两三四五六七八九十\d]+\s*天$')
            mixed_pattern = re.compile(r'(.+?)(?:玩|待|游)\s*[一二两三四五六七八九十\d]+\s*天')  # ✅ 新增：匹配混合短语
            
            for phrase in reversed(attraction_candidates):
                if phrase and phrase not in self.stop_dest and 1 < len(phrase) <= 10 and phrase != city:
                    # ✅ 排除纯天数表达
                    if days_pattern.match(phrase):
                        continue
                    
                    # ✅ 处理混合短语：从"故宫玩三天"中提取"故宫"
                    mixed_match = mixed_pattern.match(phrase)
                    if mixed_match:
                        potential_attraction = mixed_match.group(1).strip()
                        if potential_attraction and len(potential_attraction) >= 2:
                            attraction = potential_attraction
                            break
                        continue
                    
                    # 普通短语，直接使用
                    attraction = phrase
                    break

        return city, attraction

    def extract(self, text):
        text = self._basic_clean(text)
        words_with_pos = list(pseg.cut(text))

        city, attraction = self._extract_city_and_attraction(text, words_with_pos)

        # 预算
        budget = None
        # 支持多种预算表达方式
        budget_patterns = [
            r'预算[是:：]?\s*(\d+)',           # "预算是2000"、"预算:2000"
            r'(\d+)\s*[元块]',                 # "2000元"、"2000块"
            r'(\d+)\s*[k千]',                  # "2k"、"2千"
            r'(\d+)\s*万',                     # "1万"
            r'([一二两三四五六七八九十百千万]+)\s*[元块]',  # "两千块"
            r'预算[是:：]?\s*([一二两三四五六七八九十百千万]+)',  # "预算是两千"
        ]
        
        for pat in budget_patterns:
            budget_match = re.search(pat, text)
            if budget_match:
                num_str = budget_match.group(1)
                # 处理中文数字
                cn_digit_map = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"百":100,"千":1000,"万":10000}
                
                # 判断是否是中文数字
                if any(cn in num_str for cn in cn_digit_map.keys()):
                    # 简单处理：如果是纯中文数字
                    if num_str in cn_digit_map:
                        budget = cn_digit_map[num_str]
                    elif '千' in num_str:
                        # 如"两千"
                        base = num_str.replace('千', '')
                        if base in cn_digit_map:
                            budget = cn_digit_map[base] * 1000
                        else:
                            try:
                                budget = int(base) * 1000
                            except:
                                budget = None
                    elif '万' in num_str:
                        base = num_str.replace('万', '')
                        if base in cn_digit_map:
                            budget = cn_digit_map[base] * 10000
                        else:
                            try:
                                budget = int(base) * 10000
                            except:
                                budget = None
                    else:
                        parsed = self._parse_chinese_number(num_str)
                        budget = parsed
                else:
                    # 阿拉伯数字
                    try:
                        budget = int(num_str)
                        # 检查是否有单位
                        if 'k' in pat.lower() or '千' in pat:
                            budget *= 1000
                        elif '万' in pat:
                            budget *= 10000
                    except ValueError:
                        budget = None
                
                if budget is not None:
                    break

        # 出行方式
        transport = None
        for keyword, value in self.transport_map.items():
            if keyword in text:
                transport = value
                break

        # 出发时间（注意：必须将"大后天"放在"后天"前面，避免部分匹配）
        depart_time = None
        time_patterns = [
            r'(大后天)',                    # ✅ 优先匹配"大后天"
            r'(明天|后天)',                 # 再匹配"明天"和"后天"
            r'(下周[一二三四五六日天])',
            r'(下个月|下个星期|这周末|下周末|周末)',
            r'(\d{1,2}月\d{1,2}[日号])',
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'(\d{1,2}月\d{1,2}日?)'
        ]
        for pat in time_patterns:
            match = re.search(pat, text)
            if match:
                depart_time = match.group(1)
                break

        # 人数（增强：支持"我"、"我和朋友"等语义表达）
        people = None
        
        # 1. 优先匹配明确的数字表达
        people_match = re.search(r'(\d+)\s*(个?人|位)', text)
        if people_match:
            people = int(people_match.group(1))
        else:
            cn_people_match = re.search(r'([一二两三四五六七八九])\s*(个?人|位)', text)
            if cn_people_match:
                digit_map = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
                people = digit_map.get(cn_people_match.group(1))
        
        # 2. 如果没有明确数字，尝试语义识别
        if people is None:
            # ✅ "我和朋友/同学/同事" → 2人
            if re.search(r'我\s*和\s*(朋友|同学|同事|伙伴|对象|男朋|女朋|爱人|配偶)', text):
                people = 2
            # ✅ "我一个人"、"我自己"、"我想" → 1人
            elif re.search(r'我\s*(一个)?人', text) or re.search(r'我\s*自己', text) or re.search(r'^\s*我想', text):
                people = 1
            # ✅ "我们" → 默认2人（可根据上下文调整）
            elif '我们' in text and not re.search(r'我们\s*\d+', text):
                people = 2

        # 出行天数（新增）
        travel_days = None
        # 匹配"玩X天"、"X天"、"待X天"等表达
        # 注意：必须先匹配带动词的，再匹配不带动词的，避免误匹配
        days_patterns = [
            r'玩\s*([一二两三四五六七八九十\d]+)\s*天',  # ✅ "玩一天"、"玩3天"
            r'待\s*([一二两三四五六七八九十\d]+)\s*天',  # ✅ "待两天"
            r'游\s*([一二两三四五六七八九十\d]+)\s*天',  # ✅ "游三天"
            r'([一二两三四五六七八九十])\s*天',          # ✅ "一天"、"三天"（仅中文数字，避免误匹配）
        ]
        for pat in days_patterns:
            days_match = re.search(pat, text)
            if days_match:
                day_str = days_match.group(1)
                # 处理中文数字和阿拉伯数字
                cn_digit_map = {"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
                if day_str in cn_digit_map:
                    travel_days = cn_digit_map[day_str]
                else:
                    try:
                        travel_days = int(day_str)
                    except ValueError:
                        travel_days = None
                break

        return {
            "city": city,
            "attraction": attraction,
            "budget": budget,
            "transport": transport,
            "depart_time": depart_time,
            "people": people,
            "travel_days": travel_days  # ✅ 新增返回
        }
