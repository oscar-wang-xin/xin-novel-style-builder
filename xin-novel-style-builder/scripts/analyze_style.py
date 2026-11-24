#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
十维文风量化统计脚本（xin-novel-style-builder Step 3）

用法:
    python analyze_style.py <extract_chapters.py 产出的清洗txt> [章数，默认全部]

输出的每一项都对应十维萃取框架里的一个维度，用于给"具象化描述"提供数据支撑，
避免写出"文笔简洁、节奏明快"这类空洞结论。

覆盖维度: 2 句式 / 3 对话 / 4 节奏 / 5 词汇修辞 / 7 钩子 / 8 环境 / 10 开篇
（维度 1/6/9 需人工判读，脚本提供辅助计数）
"""
import re
import sys
import collections


def load(path):
    text = open(path, encoding='utf-8').read()
    parts = re.split(r'^## ', text, flags=re.M)[1:]
    chaps = []
    for p in parts:
        lines = p.strip().split('\n')
        title = lines[0].strip()
        paras = [x for x in '\n\n'.join(l for l in lines[1:] if l.strip()).split('\n\n') if x.strip()]
        chaps.append({'title': title, 'paras': paras, 'text': '\n\n'.join(paras)})
    return chaps


def hr(t):
    print('\n' + '=' * 12 + ' ' + t + ' ' + '=' * 12)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    chaps = load(sys.argv[1])
    if len(sys.argv) > 2:
        chaps = chaps[:int(sys.argv[2])]
    full = ''.join(c['text'] for c in chaps)
    allp = [p for c in chaps for p in c['paras']]
    n = len(chaps)

    hr('样本规模')
    print('章数 %d  段数 %d  总字数 %d  平均每章 %.0f 字' %
          (n, len(allp), len(full), len(full) / n))

    # ---------- 维度2 句式 ----------
    hr('维度2 句式特征')
    L = sorted(len(p) for p in allp)
    print('平均段长 %.1f 字  中位数 %d  最长 %d' % (sum(L) / len(L), L[len(L) // 2], L[-1]))
    buckets = [('<=20', lambda x: x <= 20), ('21-50', lambda x: x <= 50),
               ('51-100', lambda x: x <= 100), ('101-200', lambda x: x <= 200),
               ('201-400', lambda x: x <= 400), ('>400', lambda x: True)]
    acc = 0
    for name, f in buckets:
        cnt = sum(1 for x in L if f(x) and (x > acc))
        print('  %-8s %5d 段  %5.1f%%' % (name, cnt, cnt * 100.0 / len(L)))
        acc = {'<=20': 20, '21-50': 50, '51-100': 100, '101-200': 200, '201-400': 400}.get(name, 10 ** 9)
    sents = [s for s in re.split(r'[。！？！？；]', full) if len(s.strip()) > 1]
    print('平均句长 %.1f 字（以 。！？； 切分，共 %d 句）' % (sum(len(s) for s in sents) / len(sents), len(sents)))
    # 【坑】必须按"标点单位"遍历，不能逐字符遍历：'……' 与 '——' 都是双字符，
    # 逐字符会把它们拆成两个单字符各打印一遍（`…` 1245 打印两次、`—` 82 打印两次）。
    # 读输出的人极易把 1245 当成省略号真实次数（《诡舍》实为 613 处），
    # 或看到 `—` 有值而"零出现标点"又报 `——`，误判成版本缺陷。
    punct_units = ['……', '——', '，', '。', '、', '；', '：', '？', '！',
                   '“', '”', '‘', '’', '（', '）', '《', '》', '—', '…', '～']
    for ch in punct_units:
        c = full.count(ch)
        # 单字符计数要扣掉被双字符标点消耗的部分（'——' 含 2 个 '—'）
        if ch == '—':
            c -= 2 * full.count('——')
        elif ch == '…':
            c -= 2 * full.count('……')
        if c > 0:
            print('  标点 %s  %6d 次  %5.1f /千字' % (ch, c, c * 1000.0 / len(full)))
    zero = []
    for tk in ['？', '！', '……', '—', '～']:
        if full.count(tk) == 0 and tk not in zero:
            zero.append(tk)
    if zero:
        print('  [注意] 零出现标点：%s —— 多为 txt 版本归一化，勿误判为作者风格' % ' '.join(zero))
    tail = collections.Counter(p[-1] for p in allp)
    print('  段落末字符 TOP5：' + '  '.join('%s:%d' % kv for kv in tail.most_common(5)))

    # ---------- 维度3 对话 ----------
    hr('维度3 对话体系')
    dq = re.findall(r'[\u201c"]([^\u201c\u201d"]{1,300})[\u201d"]', full)
    dl = sorted(len(x) for x in dq)
    print('台词 %d 句  对话占比 %.1f%%  平均台词 %.1f 字  中位数 %d 字' %
          (len(dq), sum(dl) * 100.0 / len(full), sum(dl) / len(dl), dl[len(dl) // 2]))
    withq = [p for p in allp if '\u201c' in p]
    print('含引号段落 %d / %d = %.1f%%' % (len(withq), len(allp), len(withq) * 100.0 / len(allp)))
    # 段落构成：判断"一句一段"还是"一段多回合"，这是最容易被误判的硬指标
    pure = [p for p in allp if p.startswith('\u201c') and p.rstrip().endswith('\u201d')]
    tag = re.compile(r'[\u4e00-\u9fff]{1,6}道[：:]')
    multi = [p for p in allp if len(tag.findall(p)) >= 2]
    one = [p for p in allp if len(tag.findall(p)) == 1]
    zero = [p for p in allp if not tag.findall(p)]
    print('段落构成：纯叙事段 %d(%.1f%%) / 含1处发言 %d(%.1f%%) / 含2处以上发言 %d(%.1f%%) / 纯对话独立成段 %d(%.1f%%)'
          % (len(zero), len(zero) * 100.0 / len(allp),
             len(one), len(one) * 100.0 / len(allp),
             len(multi), len(multi) * 100.0 / len(allp),
             len(pure), len(pure) * 100.0 / len(allp)))
    if len(pure) * 100.0 / len(allp) < 3:
        print('  [重要] 纯对话独立成段 <3% ：本样本是"一段内多人来回"结构，'
              '写 SKILL.md 时务必禁止网文式"一句一段"')
    print('  多发言标签段示例：')
    for p in multi[:2]:
        print('    · %s' % p[:150])
    for w in ['道：', '说道', '笑道', '喝道', '叫道', '问道', '冷冷的道', '沉吟道', '奇道', '怒道']:
        c = full.count(w)
        if c:
            print('  %s %d' % (w, c))

    # ---------- 维度1 视角（辅助） ----------
    hr('维度1 视角辅助计数')
    for w in ['心想', '心道', '暗想', '寻思', '暗自', '心中', '心下', '却不知', '殊不知', '他不知道']:
        c = full.count(w)
        if c:
            print('  %s %d 次  %.1f 次/章' % (w, c, c * 1.0 / n))
    for w in ['只见', '只听', '忽听', '忽闻', '但见']:
        c = full.count(w)
        if c:
            print('  %s %d 次  %.1f 次/章' % (w, c, c * 1.0 / n))

    # ---------- 维度4 节奏 ----------
    hr('维度4 叙事节奏')
    for w in ['当下', '忽然', '忽地', '猛地', '陡然', '原来', '哪知', '岂知', '登时', '霎时', '转瞬',
              '过得', '次日', '这日', '这一日', '片刻', '待得', '跟着', '随即', '便即',
              '在路非止一日', '一晃', '不一日', '如此一月', '数年']:
        c = full.count(w)
        if c:
            print('  %s %d 次  %.1f 次/章' % (w, c, c * 1.0 / n))

    # ---------- 维度5 词汇修辞 ----------
    hr('维度5 词汇与修辞')
    for w in ['犹如', '宛如', '好似', '如同', '便如', '直如', '宛若', '恰似', '一般', '似的']:
        c = full.count(w)
        if c:
            print('  比喻标记 %s %d' % (w, c))
    print('  拟声：' + ' / '.join('%s:%d' % (w, full.count(w)) for w in
                              ['的一声', '哈哈', '嘻嘻', '嘿嘿', '呵呵', '格格'] if full.count(w)))

    def ngram(top=60):
        s = re.sub(r'[^\u4e00-\u9fff]', '|', full)
        g = collections.Counter()
        for seg in s.split('|'):
            for k in (2, 3, 4):
                for i in range(len(seg) - k + 1):
                    g[seg[i:i + k]] += 1
        stop = set('的了是在不他她我你他们这那有就也都和与之而为其以于所很便又却只一个来去到说道着要会能可好没甚么怎样')
        out = [(c, w) for w, c in g.items() if c >= 30 and not any(ch in stop for ch in w)]
        out.sort(reverse=True)
        return out[:top]

    print('  高频词组 TOP60：' + '  '.join('%s:%d' % (w, c) for c, w in ngram()))

    # ---------- 维度8 环境 ----------
    hr('维度8 环境描写')
    sc = set('江山树林风雪月云天水湖海竹花草日星影声霜雨露岩石沙崖船舟灯火光雾坡谷溪泉岸桥寺塔屋院墙窗门桌')
    env = [p for p in allp if '\u201c' not in p and sum(1 for ch in p if ch in sc) >= 8]
    print('疑似纯景物段 %d / %d = %.1f%%  字数占比 %.1f%%' %
          (len(env), len(allp), len(env) * 100.0 / len(allp),
           sum(len(p) for p in env) * 100.0 / sum(len(p) for p in allp)))

    # ---------- 维度7 / 10 钩子与开篇 ----------
    hr('维度7 章末钩子 / 维度10 开篇习惯')
    for c in chaps:
        print('\n--- %s ---' % c['title'])
        print('  [开篇120] %s' % c['text'][:120].replace('\n\n', ' / '))
        print('  [章末120] %s' % c['text'][-120:].replace('\n\n', ' / '))

    # ---------- 维度9 禁忌辅助 ----------
    hr('维度9 行文禁忌（现代/网文词汇应为 0 或极低）')
    for w in ['系统', '宿主', '任务', '面板', '升级', '境界', '丹田', '元婴', '筑基', '觉醒',
              '他不知道', '读者', '要知后事', '列位看官', '且听下回', '不由自主', '这一刻',
              '内心深处', '仿佛整个世界']:
        c = full.count(w)
        print('  %s %d' % (w, c))


if __name__ == '__main__':
    main()
