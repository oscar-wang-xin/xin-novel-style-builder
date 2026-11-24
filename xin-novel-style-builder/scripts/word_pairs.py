#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
古今用词对照词频统计脚本（xin-novel-style-builder Step 3 必跑项）

用法:
    python word_pairs.py <清洗txt路径> [额外对照文件路径]

为什么单独一个脚本：
    SKILL.md 里明确要求"古今/雅俗用词必须逐本实测，绝不套用上一本的结论"。
    实测反例——《倚天》《射雕》"甚么 vs 什么"是 659:7 级压倒性偏古，
    而《天龙八部》是 535:586 近乎 1:1 混用。照抄前一本的结论会写出错误规范。
    但 analyze_style.py 不跑这项，每次构建都要手写几十组对照词，既慢又容易漏。
    本脚本把它固化成一条命令，输出可直接贴进 SKILL.md 的三类表格。

输出三类：
    A. 硬规则（古体压倒 >10:1）      -> 只用古体，用现代体即出戏
    B. 现代体压倒                     -> 用现代体，别硬拽文言
    C. 中性项（0.1 <= 比值 <= 10）    -> 两者皆可，无需回避也无需强行统一

注意：
    部分词对会互相重叠（如"如果"同时出现在 若是/如果 与 倘若/如果 两对里），
    工具词（如何/怎么、如此/这样...）混用属正常，不必强行统一。
"""
import re
import sys

# (古体标签, 古体正则, 现代体标签, 现代体正则)
# 用正则而非 str.count，是为了绕开子串误计——
# 实测踩过的坑：`么` 直接 count 会得到 1468，里面混进了 甚么841 / 怎么222 / 这么172，
# 会误判成"么 压倒 吗"。所以 么 必须加负向后顾断言，排除 甚/什/怎/这/那/多。
# 同理，单字虚词 便/即/均/皆 的对手 就/都 在白话里本就是高频词，比值无意义，
# 只作参考、不进硬规则。
PAIRS = [
    # 语气助词
    ('罢', r'罢', '吧', r'吧'),
    ('么', r'(?<![甚什怎这那多])么', '吗', r'吗'),
    ('恁地', r'恁地', '这么', r'这么'),
    ('端的', r'端的', '究竟', r'究竟'),
    # 疑问代词
    ('甚么', r'甚么', '什么', r'什么'),
    ('如何', r'如何', '怎么', r'怎么'),
    ('怎地', r'怎地', '这么', r'这么'),
    ('何处', r'何处', '哪里', r'哪里'),
    ('何不', r'何不', '为什么不', r'为什么不'),
    ('岂', r'岂', '难道', r'难道'),
    ('莫非', r'莫非', '难道', r'难道'),
    # 假设连词
    ('若是', r'若是', '如果', r'如果'),
    ('倘若', r'倘若', '如果', r'如果'),
    ('纵然', r'纵然', '即使', r'即使'),
    # 时间副词
    ('登时', r'登时', '立刻', r'立刻'),
    ('便即', r'便即', '马上', r'马上'),
    ('随即', r'随即', '马上', r'马上'),
    ('霎时', r'霎时', '瞬间', r'瞬间'),
    ('当下', r'当下', '这时', r'这时'),
    ('待得', r'待得', '等到', r'等到'),
    ('过得', r'过得', '过了', r'过了'),
    ('已然', r'已然', '已经', r'已经'),
    ('方才', r'方才', '刚才', r'刚才'),
    ('未曾', r'未曾', '没有', r'没有'),
    ('陡然', r'陡然', '突然', r'突然'),
    ('兀自', r'兀自', '仍然', r'仍然'),
    ('一晃', r'一晃', '转眼', r'转眼'),
    ('良久', r'良久', '很久', r'很久'),
    # 情态副词
    ('须得', r'须得', '必须', r'必须'),
    ('甚是', r'甚是', '非常', r'非常'),
    ('略一', r'略一', '稍微', r'稍微'),
    ('一齐', r'一齐', '一起', r'一起'),
    ('这等', r'这等', '这种', r'这种'),
    ('如此', r'如此', '这样', r'这样'),
    ('咱们', r'咱们', '我们', r'我们'),
    ('何况', r'何况', '况且', r'况且'),
    # 心理/动作动词
    ('知晓', r'知晓', '知道', r'知道'),
    ('寻思', r'寻思', '思考', r'思考'),
    ('心下', r'心下', '心里', r'心里'),
    ('瞧', r'瞧', '看', r'看'),
    ('说话', r'说话', '讲话', r'讲话'),
    ('喝道', r'喝道', '喊道', r'喊道'),
    ('勿', r'勿', '别', r'别'),
    ('休得', r'休得', '别', r'别'),
    ('且慢', r'且慢', '等一下', r'等一下'),
    ('不该', r'不该', '不应该', r'不应该'),
    ('不由得', r'不由得', '忍不住', r'忍不住'),
]

# 仅供参考、不进硬规则：单字虚词的对手词在白话里本就是超高频，
# 比值受题材影响远大于受文风影响（例：《侠客行》便 1536 : 就 588，看着偏古，
# 但"就"在对话里本就常见，不能据此禁用"就"）。
REFERENCE_ONLY = [
    ('均', r'均', '都', r'都'),
    ('皆', r'皆', '都', r'都'),
    ('便', r'便', '就', r'就'),
    ('即', r'即', '就', r'就'),
]


# 【坑】内置 PAIRS 全是简体，遇到繁体样本（黄易香港版、《寻秦记》这类）会全部零命中，
# 更糟的是会拿"繁体古体 vs 简体现代体"做对比——"如此 48 : 这样 0"这种 ∞ 比值纯属
# 字符集不同造成的假象，写进 SKILL.md 就是一条彻头彻尾的错误规范。
# 实测：《寻秦记》繁体样本下，"未曾:没有"被判 A 类硬规则（1:0），而正确的繁体对比
# "未曾:沒有"是 1:162 的 B 类。同一对词得出相反结论。
# 解法：自动检测样本繁简，繁体则把内置词对整体转繁后再统计。
S2T_MAP = {
    '罢': '罷', '么': '麼', '吗': '嗎', '这': '這', '难': '難', '处': '處',
    '里': '裡', '为': '為', '纵': '縱', '时': '時', '马': '馬', '随': '隨',
    '间': '間', '过': '過', '经': '經', '刚': '剛', '没': '沒', '们': '們',
    '种': '種', '齐': '齊', '晓': '曉', '寻': '尋', '讲': '講', '话': '話',
    '别': '別', '该': '該', '转': '轉', '样': '樣', '说': '說', '应': '應',
    '来': '來', '会': '會', '觉': '覺', '学': '學', '实': '實', '头': '頭',
}
# 只取"繁简同形度最低"的一批字做判别，避免长文本里偶然混排干扰
TRAD_MARKERS = '們麼這為難經間馬種齊裡說時樣該別沒過隨'
SIMP_MARKERS = '们么这为难经间马种齐里说时样该别没过随'


def is_traditional(text):
    sample = text[:200000]
    t = sum(sample.count(c) for c in TRAD_MARKERS)
    s = sum(sample.count(c) for c in SIMP_MARKERS)
    return t > s * 2


def to_trad(s):
    """字符级转繁。只映射 CJK，正则元字符（ASCII）不受影响，可安全用于 pattern。"""
    return ''.join(S2T_MAP.get(c, c) for c in s)


def load_text(path):
    text = open(path, encoding='utf-8').read()
    # 剥掉章节标题行，避免标题里的词被计入
    return re.sub(r'^## .*$', '', text, flags=re.M)


def classify(a_count, b_count):
    """A=古体压倒, B=现代体压倒, C=中性混用, None=均未出现"""
    if a_count == 0 and b_count == 0:
        return None
    if b_count == 0:
        return 'A'
    if a_count == 0:
        return 'B'
    ratio = a_count / b_count
    if ratio > 10:
        return 'A'
    if ratio < 0.1:
        return 'B'
    return 'C'


def count(text, pattern):
    """pattern 可以是正则；非正则的普通词直接 count 更快"""
    if re.search(r'[\\\[\]()?*+|{}^$]', pattern):
        return len(re.findall(pattern, text))
    return text.count(pattern)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    text = load_text(sys.argv[1])

    # 允许额外补充对照词：每行 "古体 现代体" 或 "古体,现代体"
    pairs = list(PAIRS)
    if len(sys.argv) > 2:
        for line in open(sys.argv[2], encoding='utf-8'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = re.split(r'[\s,，/|]+', line)
            if len(parts) >= 2:
                pairs.append((parts[0], re.escape(parts[0]), parts[1], re.escape(parts[1])))

    if is_traditional(text):
        print('[检测] 样本为繁体，内置对照词已自动转繁后统计（否则"繁体古体 vs 简体现代体"'
              '会得出假 ∞ 比值）')
        pairs = [(to_trad(la), to_trad(pa), to_trad(lb), to_trad(pb)) for la, pa, lb, pb in pairs]
    # 转繁后内置词对可能与补充词表重复，去重避免同一对词被打进 A/B 两类
    seen, uniq = set(), []
    for item in pairs:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    pairs = uniq

    buckets = {'A': [], 'B': [], 'C': []}
    for la, pa, lb, pb in pairs:
        ca, cb = count(text, pa), count(text, pb)
        kind = classify(ca, cb)
        if kind:
            buckets[kind].append((la, ca, lb, cb))

    def dump(title, items, note):
        print('\n' + '=' * 10 + ' ' + title + ' ' + '=' * 10)
        print(note)
        if not items:
            print('  （无）')
            return
        for a, ca, b, cb in sorted(items, key=lambda x: -(x[1] + x[3])):
            ratio = (ca / cb) if cb else float('inf')
            rtxt = '∞' if ratio == float('inf') else f'{ratio:.1f}:1'
            print(f'  {a:5s} {ca:6d}  :  {b:6s} {cb:6d}     {rtxt}')

    dump('A. 硬规则（古体压倒 >10:1，只用古体）', buckets['A'],
         '  -> 写进 SKILL.md「词汇修辞规范」，明确"只用X，禁用Y"')
    dump('B. 现代体压倒（用现代体，别硬拽文言）', buckets['B'],
         '  -> 写进 SKILL.md，提醒别为了古风硬用文言词')
    dump('C. 中性项（0.1~10 倍，两者皆可）', buckets['C'],
         '  -> 写进 SKILL.md，标注"无需回避，也无需强行统一"')

    print('\n' + '=' * 10 + ' D. 仅供参考（不进硬规则） ' + '=' * 10)
    print('  单字虚词，对手词在白话里本就超高频，比值受题材影响大于受文风影响')
    for a, pa, b, pb in REFERENCE_ONLY:
        ca, cb = count(text, pa), count(text, pb)
        print(f'  {a:5s} {ca:6d}  :  {b:6s} {cb:6d}')

    print('\n' + '=' * 10 + ' 现代词替换表（由 A 类生成） ' + '=' * 10)
    if buckets['A']:
        items = sorted(buckets['A'], key=lambda x: -(x[1] + x[3]))
        print('  ' + '｜'.join(f'{b}→{a}' for a, ca, b, cb in items))
    else:
        print('  （无）')

    print('\n[提示] 以上均为本书实测值，禁止套用其它小说的古今用词结论。')


if __name__ == '__main__':
    main()
