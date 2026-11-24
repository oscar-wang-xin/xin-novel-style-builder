#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
章节提取与正文清洗脚本（xin-novel-style-builder Step 2）

用法:
    python extract_chapters.py <小说文件路径> <输出txt路径> [章节数，默认20]

功能:
    1. 自动探测编码（utf-8 / gbk / gb18030 / utf-16）
    2. 剥离站点声明、书名/作者/简介等前置非正文
    3. 识别中文章节标记，提取前 N 章
    4. 清洗空白、页眉页脚式空行，输出纯净正文

输出格式: 每章以 "## 第X章 标题" 独占一行开头，正文段与段之间空一行。
"""
import re
import sys
import os

ENCODINGS = ['utf-8', 'gbk', 'gb18030', 'utf-16', 'big5']

CN_CHARS = '0-9一二三四五六七八九十百千零〇'

# 分卷章节标记（黄易/网络小说常见）：第1卷第1章 / 第01卷第02章 / 第二卷第三章
# 【坑】"第1卷第1章"用旧的正则是匹配不到的：'第\s*[CN]+\s*[章节回节]' 读完"第1"后
# 紧接着是"卷"，不在 [章节回节] 里，整条替代分支直接失败；'卷\s*[CN]+' 又要求"卷"
# 出现在行首。结果《寻秦记》这类分卷书 292 个章标记一个都识别不到。
# 【坑】黄易《大唐双龙传》等用「卷一 第一章」格式——卷前无"第"，直接 "卷X + 空格 + 第Y章"。
# 旧 VOL 正则要求卷前有"第"，同样整条失败，导致整卷被吞成单章。第二组分支补「卷X 第Y章」。
VOL_CHAPTER_PAT = re.compile(
    r'^[ \t　]*(?:第\s*[' + CN_CHARS + r']+\s*卷\s*第?\s*[' + CN_CHARS + r']+\s*'
    r'|卷\s*[' + CN_CHARS + r']+\s*第\s*[' + CN_CHARS + r']+)\s*[章节回节][^\n]{0,60}$',
    re.M
)

# 章节标记：第01章 / 第一章 / Chapter 1 / 第1节 / 卷一
# 【坑】必须限制标题行总长：正文里以"第四回合上韦小宝留了神……"开头的段落会被
# 误判成章节标题（"第四回"+"合上韦小宝……"）。真实章节标题一般是独立短行。
CHAPTER_PAT = re.compile(
    r'^[ \t　]*(?:'
    r'第\s*[' + CN_CHARS + r']+\s*卷\s*第?\s*[' + CN_CHARS + r']+\s*[章节回节]|'
    r'第\s*[' + CN_CHARS + r']+\s*[章节回节]|'
    r'卷\s*[' + CN_CHARS + r']+|'
    r'Chapter\s*[0-9]+'
    r')[^\n]{0,60}$',
    re.M | re.I
)

# 只从章节标记的前缀部分取编号，避免标题里的中文数字（如"江南七怪"）被误读
# 【坑】分卷标记的卷号不能捕获：main() 取"第一个非空分组"，若卷号成组会被当成章号，
# 于是 第2卷第1章 会被解析成章号 2，全书章号全线错位。卷号用非捕获。
NUM_PAT = re.compile(
    r'^\s*(?:'
    r'第\s*[' + CN_CHARS + r']+\s*卷\s*第?\s*([' + CN_CHARS + r']+)\s*[章节回节]|'
    r'第\s*([' + CN_CHARS + r']+)\s*[章节回节]|'
    r'卷\s*([' + CN_CHARS + r']+)|'
    r'Chapter\s*([0-9]+)'
    r')',
    re.I
)

# 【坑】'十' 绝不能放进 CN_NUM，否则 "十一" 会走 cur 分支被算成 1、
# "二十" 被算成 10，导致《鹿鼎记》这类 "第X回" 编号全线错位。
CN_NUM = {'零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9}


def cn2int(s):
    """中文/阿拉伯数字混合编号转整数，覆盖 一 ~ 九千九百九十九 与纯数字。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    # 纯中文数字
    if all(ch in CN_NUM or ch in '十百千' for ch in s):
        units = {'十': 10, '百': 100, '千': 1000}
        total, section, cur = 0, 0, 0
        for ch in s:
            if ch in CN_NUM:
                cur = CN_NUM[ch]
            elif ch in units:
                u = units[ch]
                section += (cur if cur else 1) * u
                cur = 0
        return total + section + cur
    # 兜底：抽取其中的阿拉伯数字
    digits = re.findall(r'[0-9]+', s)
    return int(digits[0]) if digits else 0


def strip_author_notes(text):
    """剔除作者考据自注（金庸作品特有，如《鹿鼎记》章末/章中的"注：……"）。

    【坑】这类注释不是正文，混进样本会：
      1. 拉高"考据/历史叙述"权重，污染词汇与句式统计；
      2. 被 analyze_style.py 当成"章末 120 字"采进钩子统计，把一条注释误判成一种钩子句式。
    处理规则：
      - 段落恰为 "注："（光杆）→ 其后直到下一个章节标记全为注释，整块删；
      - 段落以 "注：" 开头 → 删该段，并继续吞掉后续不含"叙述/对话标记"的段落（注释常跨多段）。
    注意："原注："（诗文内部的原作者自注）属于正文，不能删。
    """
    # 【坑】"注：xxx" 会往下吞掉"不含对话标记"的续段，靠 NARR 判定何时停。
    # 原 NARR 只认 `X道：“...”`（标签与台词同行），但**网文大量台词独立成段且无标签**，
    # 加上 `宁秋水道：` 后跟换行（台词在下一行）也不匹配，命中率会暴跌到 0.4%
    # （《诡舍》实测 11/2468）——一旦正文里出现"注："开头的段，后续整片台词会被吞光。
    # 故补一条"以 X道： 结尾"的分支，覆盖"标签段 + 台词另起段"的网文格式。
    NARR = re.compile(
        r'(道|说|问|答|喝|叫)[:：]?[“"]|笑道|心想[:：]|(道|说|问|答|笑)[:：]\s*$'
    )
    paras = text.split('\n\n')
    out, i = 0, 0
    result = []
    while i < len(paras):
        q = paras[i].lstrip()
        if q == '注：' or q == '注:':
            j = i + 1
            while j < len(paras) and not paras[j].startswith('## '):
                j += 1
            i = j
            continue
        if q.startswith('注：'):
            j = i + 1
            while j < len(paras) and not paras[j].startswith('## ') and not NARR.search(paras[j]):
                j += 1
            out += j - i
            i = j
            continue
        result.append(paras[i])
        i += 1
    if out:
        print('[清洗] 剔除作者考据自注 %d 段' % out)
    # 段尾游离 ASCII 冒号（转码残留，常为被删掉的 ？！ 或 …… 的位置）
    return re.sub(r':(?=\n|$)', '', '\n\n'.join(result))


# 【坑】尾部附录/后记：当提取章数 >= 全书总章数时，最后一章的 end 会取到 len(text)，
# 把"后记 + 附录 + 站点声明"整块吞进来，导致该章字数暴涨数倍，段长/对话占比等统计全线失真。
# 实例：《碧血剑》共二十回，第二十回被吃到 94,598 字（真实正文仅 21,266 字），
# 因为文末附了 476 字"后记" + 约 7.5 万字《袁崇焕评传》。
#
# 【坑2】标记必须分两类处理，不能一律取"最后一个"匹配：
#   - 起始型（后记/附录/跋/外篇/写在后面/关于本书）：它之后还有几千字附录正文，
#     必须取**最靠前**的那一个，只截到它之前。
#   - 终结型（全书完/大结局）：它之后只剩站点声明，取**最靠后**的那一个即可。
# 实例：《雪山飞狐》文末顺序是 "后记"…(约2000字附录)…"（全书完），
#   旧逻辑 last[-1] 取到"（全书完）"（136280），把 134358 之后的整段后记全留在第10章内，
#   导致章末钩子统计把后记末句误采成"章末 120 字"。
TAIL_START_PAT = re.compile(
    r'^[ \t　]*(?:'
    r'后\s*记|附\s*录|外\s*篇|作者后记|关于本书|写在后面|'
    r'出版后记|再版后记|新序|后\s*序|代\s*后\s*记|跋|题\s*跋'
    r')(?:[ \t　]*[:：][ \t　]*\S{0,20})?[ \t　]*$',
    re.M
)
TAIL_END_PAT = re.compile(
    r'^[ \t　]*(?:\(?（?全书完\)?）?|全书完|大\s*结\s*局|全文完|本\s*书\s*完)[ \t　]*$',
    re.M
)


def strip_tail_appendix(text, end):
    """若最后一章末端混入后记/附录，返回截断点；否则返回原 end。

    优先按"起始型"标记（后记/附录/跋…）截断，取最靠前的一个——
    因为它之后往往还有几千字附录正文；没有起始型标记时，才退而取
    "终结型"标记（全书完/大结局）的最靠后一个。
    """
    seg = text[:end]
    for pat, take_last in ((TAIL_START_PAT, False), (TAIL_END_PAT, True)):
        hits = [m for m in pat.finditer(seg) if m.start() >= end * 0.7]
        if not hits:
            continue
        m = hits[-1] if take_last else hits[0]
        return m.start(), m.group().strip()
    return end, None


# 站点水印关键词：只有命中这些词才删，避免误伤正文的括号/方括号内容
# 【坑】`免费` 不能裸写。它在白话文里是超高频日常词——"天下没有免费的午餐"
# "免费的冰激凌""免费公园""免费提供帮助"。《异兽迷城》实测：33 条命中**全部**是
# 正文（对话与叙述里的"免费"），零条真水印，其中 2 条正好落在前 20 章内，
# 一条是第 07 章末句（被当成"章末钩子"抹掉）、一条是【】系统面板（被当成
# 站点广告抹掉）。故必须与下载/阅读/小说等站点语境绑定才定罪。
_FREE = r'免费(?:下载|阅读|小说|电子书|TXT)|免費(?:下載|閱讀|小說|電子書|TXT)|(?:下载|閱讀?)[^。！？]{0,4}免费'
SITE_KEY = re.compile(
    r'書庫|书库|shuku|wuxiashuku|\.com|\.net|' + _FREE + r'|'
    r'下載|下载|ＴＸＴ|TXT|小說下載|小说下载|整理|提供及',
    re.I
)
# 强特征：单独出现即可证明这一行是站点产物。
# 弱特征（裸"整理"）不能单独定罪——《不死帝师》正文"整理遗容"被 SITE_KEY 的
# `整理` 命中，整行当水印删掉（实测误删 2 段正文，第6章从 83 段掉到 80 段）。
# 分工：括号块内（有包裹语境）仍用 SITE_KEY；独立成行的一律用 SITE_STRONG。
SITE_STRONG = re.compile(
    r'書庫|书库|shuku|wuxiashuku|\.com|\.net|' + _FREE + r'|'
    r'下載|下载|ＴＸＴ|TXT|小說下載|小说下载|提供及|整理制作|由.*整理',
    re.I
)
BRACKET_PAT = re.compile(r'[［\[][^］\]　]{0,40}[］\]]|[（(][^）)　]{0,60}[）)]')


def to_halfwidth(s):
    """全角 ASCII → 半角（！-～ 区间）。

    【坑】站点水印常被转成全角规避过滤：《寻秦记》里有 18 处水印是
    ［ｗｕｘｉａｓｈｕｋｕ．ｃｏｍ］，半角关键词 'shuku' 一个都匹配不到，
    整条漏进正文。所以关键词判定前必须先做全角归一化。
    """
    return ''.join(chr(ord(c) - 0xFEE0) if '！' <= c <= '～' else c for c in s)


def strip_inline_watermark(text):
    """剔除网抓 txt 里的站点水印。

    两种形态：
      1. 独立成行：`（武侠书库 wuxiashuku.com 免费武侠小说下载）`
         ——《寻秦记》292 章章末各插一条，正好卡在章末，会被 analyze_style.py
         当成"章末 120 字"采进钩子统计，把广告语误判成一种钩子句式。
      2. 夹在正文中间：`項［武俠書庫TXT］少龍`、`一艘巨型太空（wuxiashuku.com）船`
         ——水印把词拦腰截断，直接删掉即可还原原句。
    只删命中 SITE_KEY 的括号块，正文里的普通括号不受影响。
    """
    n = 0

    def _sub(m):
        nonlocal n
        if SITE_KEY.search(to_halfwidth(m.group())):
            n += 1
            return ''
        return m.group()

    text = BRACKET_PAT.sub(_sub, text)
    # 整行都是水印（括号块被删光后剩下的空行，或裸域名行）
    lines, kept = text.split('\n'), []
    for ln in lines:
        s = ln.strip().strip('　')
        if s and SITE_STRONG.search(to_halfwidth(s)) and len(s) <= 60 and not re.search(r'[道说问答喝叫][：:]?[“"]', s):
            n += 1
            continue
        kept.append(ln)
    if n:
        print('[清洗] 剔除站点水印 %d 处' % n)
    # 缺字占位告警：网抓转码把显示不出的字（多为"口"）统一替换成"囗"，
    # 不提醒会被当成作者用词抄进 SKILL.md（《寻秦记》样本里出现 100 次）
    miss = text.count('囗')
    if miss:
        print('[提醒] 样本含缺字占位符"囗" %d 处，属转码缺陷，勿当作者用词' % miss)
    return '\n'.join(kept)


def strip_webnovel_meta(text):
    """剔除起点/番茄类网文 txt 特有的站点残留与作者按。

    四类，全部是网抓站的产物，不是正文：
      1. 章首的更新时间行：`章节更新时间：2023-05-03 21:12`
         ——每章一条，正好卡在章首，会被 analyze_style.py 当成
         "开篇 120 字"采进开篇习惯统计（《不死帝师》20 章全部中招）。
      2. 章末的作者按：`ps：根据建议，暂时将本书更新时间调整到下午三点……`
         ——含 求月票/推荐票/各位读者/感谢订阅 等作者与读者对话内容，
           会被当成"章末 120 字"采进钩子统计。
      3. 颜文字 / emoji 行：`玲珑宗宗主：(͡°͜ʖ͡°)✧`
         ——颜文字在部分网文里是正文语气的一部分（如”略~”）,
           但整行只剩颜文字的属排版残片，须整行剔除。
      4. 图片占位：`[[IMG:https://p3-novel.byteimg.com/xxx~tplv-noop.image]]`
         或 `![](url)` / `<img src=...>`。番茄、起点类网抓 txt 常在章首
         插一张"作者说/本章说"配图。**BRACKET_PAT 的 `{0,40}` 长度上限
         兜不住几十上百字符的 CDN 长链，会整条漏网**（《我不是戏神》实测：
         第 1 章残留 1 条，被 analyze_style.py 当成一段正文，段数虚增 1 段、
         总字数虚增约 130 字），故在此单独按整行剔除。
    """
    pat_time = re.compile(r'^\s*(章节更新时间|更新时间|更新时间[:：])\s*[:：]?')
    pat_ps = re.compile(r'^\s*(ps|PS|Ps|p\.s\.)[:：]')
    # PS 块最多向下吞多少行（防作者按后紧跟整章正文被吃掉）
    MAX_PS_LINES = 12
    pat_misc = re.compile(r'求月票|推荐票|月票|各位读者|感谢.*订阅|求订阅|催更|加更')
    # 组合颜文字构件与 emoji 区段；单个 ( ͡ ʖ ° ) ✧ 均可能出现
    pat_kaomoji = re.compile(r'[ʖ͡°✧∀-⋿\U0001F000-\U0001FAFF☀-➿]')
    # 图片占位：[[IMG:url]] / [IMG:url] / ![](url) / <img src=...>
    pat_img = re.compile(
        r'^\s*(\[\[?\s*IMG\s*[:：][^\]]*\]\]?|!\[[^\]]*\]\([^)]*\)|<img\s[^>]*>)\s*$',
        re.I
    )
    n = 0
    kept = []
    ps_left = 0
    for ln in text.split('\n'):
        s = ln.strip().strip('　')
        # 【坑】作者按常跨多行（"PS：……" 之后还跟着 "新书每天6000字起步。"
        # "晚安！" 之类），只删 PS 首行会把后续残留当成正文写进样本
        # （《诡舍》实测留下 2 行）。故吞到下一个章节标记为止，最多 12 行兜底。
        if ps_left > 0:
            if CHAPTER_PAT.match(ln):
                ps_left = 0          # 下一章开始，退出 PS 块
            else:
                n += 1
                ps_left -= 1
                continue
        if pat_time.match(s) or pat_img.match(s):
            n += 1
            continue
        if pat_ps.match(s):
            n += 1
            ps_left = MAX_PS_LINES
            continue
        # 【坑】pat_misc 是全行 search，会误伤正文：只因台词里含"各位"就被整行
        # 删掉（《诡舍》"各位吃饱喝足之后，可以到处逛逛……"中招，另 1 行含"加更"
        # 语义的台词也被删）。作者按行通常很短且不带台词引号，故加
        # "短行 + 无台词引号"双重保护，宁可漏删也不要误删正文。
        if (pat_misc.search(s) and len(s) <= 40
                and '“' not in s and '”' not in s):
            n += 1
            continue
        if pat_kaomoji.search(s):
            n += 1
            continue
        kept.append(ln)
    if n:
        print('[清洗] 剔除网文站点残留/作者按/颜文字 %d 行' % n)
    return '\n'.join(kept)


def detect_and_read(path):
    raw = open(path, 'rb').read()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode('utf-8', errors='ignore'), 'utf-8(ignore)'


def strip_header(text):
    """剥离站点声明与书名/作者/简介等非正文前置块。"""
    # 常见站点分隔线
    m = re.search(r'用户上传之内容开始[-—]*', text)
    if m:
        text = text[m.end():]
    m = re.search(r'-{5,}', text)
    if m and m.start() < 5000:
        text = text[m.end():]
    # 删除独立的书名行《xxx》
    text = re.sub(r'^\s*《[^》]{1,30}》\s*$', '', text, flags=re.M)
    # 删除作者/简介行
    text = re.sub(r'^\s*(作者|作\s*者|内容简介|作品简介|故事梗概|ISBN|出版社)[：:].*$', '', text, flags=re.M)
    return text


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    n_ch = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    text, enc = detect_and_read(src)
    print('[编码] %s  字符数 %d' % (enc, len(text)))
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = strip_header(text)
    text = strip_inline_watermark(text)
    text = strip_webnovel_meta(text)

    marks = list(CHAPTER_PAT.finditer(text))
    if not marks:
        print('[错误] 未识别到任何章节标记')
        sys.exit(2)
    print('[章节] 识别到 %d 个章节标记' % len(marks))

    # 【坑】分卷编号会重复（每卷都从第1章起）。若仍按"章号唯一"建索引，
    # setdefault 只保留全书第一个第1章，第2卷之后整卷被丢弃。
    # 判定为分卷体（分卷标记占多数）时，改用"按出现顺序取前 N 个标记"。
    vol_hits = sum(1 for m in marks if VOL_CHAPTER_PAT.match(m.group()))
    vol_style = vol_hits > len(marks) * 0.5
    if vol_style:
        print('[章节] 分卷体（%d/%d 命中"第X卷第Y章"），按出现顺序顺序取前 %d 章'
              % (vol_hits, len(marks), n_ch))
        idx = {i + 1: m for i, m in enumerate(marks)}
        nums = sorted(idx)
        picked = nums[:n_ch]
    else:
        # 建立 章号 -> match 映射；重复章号只保留首次出现（防分卷重排编号）
        idx = {}
        for m in marks:
            nm = NUM_PAT.match(m.group())
            if not nm:
                continue
            raw_num = next((g for g in nm.groups() if g), None)
            if raw_num is None:
                continue
            idx.setdefault(cn2int(raw_num), m)
        nums = sorted(idx)
        picked = [n for n in nums if 1 <= n <= n_ch][:n_ch]
    if not picked:
        print('[错误] 未找到可提取的章节')
        sys.exit(2)

    out = []
    skipped = []
    for i, n in enumerate(picked):
        start = idx[n].end()
        # 关键：结束位置取"下一个被提取章节的起点"或"全文中下一章的起点"，
        # 绝不能用 start + 固定长度，否则最后一章会把后续章节吞进来。
        if i + 1 < len(picked):
            end = idx[picked[i + 1]].start()
        else:
            nxt = [x for x in nums if x > n]
            end = idx[nxt[0]].start() if nxt else len(text)
            # 【坑】只有末章会吞入后记/附录，故仅在此处做尾部非正文截断
            end, cut = strip_tail_appendix(text, end)
            if cut:
                print('[清洗] 末章截断尾部非正文（"%s"之后内容已剔除）' % cut)
        body = text[start:end]
        paras = [re.sub(r'^[\s　]+', '', ln).strip() for ln in body.split('\n')]
        paras = [p for p in paras if p]
        if sum(len(p) for p in paras) < 500:
            skipped.append(n)
            continue
        title = idx[n].group().strip()
        out.append((title, paras))

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    text = strip_author_notes('\n\n'.join(
        '## %s\n\n%s' % (title, '\n\n'.join(paras)) for title, paras in out
    ))
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(text.rstrip() + '\n\n')

    total = sum(sum(len(p) for p in paras) for _, paras in out)
    print('[完成] 输出 %d 章（跳过过短章 %s）' % (len(out), skipped or '无'))
    print('[完成] 总字数 %d -> %s' % (total, dst))
    # 【坑】过长章告警：正常章字数应在中位数附近，超过中位数 2.5 倍基本是
    # 该章吞入了相邻章节、后记、附录或另一本书，必须人工复核尾部。
    sizes = sorted(sum(len(p) for p in paras) for _, paras in out)
    if sizes:
        med = sizes[len(sizes) // 2]
        for title, paras in out:
            w = sum(len(p) for p in paras)
            flag = ''
            if med and w > med * 2.5:
                flag = '  <== [警告] 字数超中位数%.1f倍，请人工复核该章尾部是否混入附录/它书' % (w / med)
            print('   %s  段数%d  字数%d%s' % (title, len(paras), w, flag))


if __name__ == '__main__':
    main()
