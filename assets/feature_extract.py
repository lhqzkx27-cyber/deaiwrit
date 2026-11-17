# -*- coding: utf-8 -*-
"""feature_extract.py —— 综合特征提取器（纯量测，不含检测判决）。
提取多维特征，供"真实vs AI分布"量测使用。
"""
import re

def sentences(text):
    parts = re.split(r"[。！？!?；;]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 2]

def paragraphs(text):
    # 段落按空行/换行切
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) >= 5]
    return paras

def extract(text):
    r = {}
    r["len"] = len(text)

    # 1. 句长结构
    sn = [len(s) for s in sentences(text)]
    if len(sn) >= 6:
        m = sum(sn) / len(sn)
        var = sum((x - m) ** 2 for x in sn) / len(sn)
        r["sent_cv"] = (var ** 0.5) / m if m else 0
        r["sent_mean"] = m
        r["short_ratio"] = sum(1 for x in sn if x <= 10) / len(sn)   # 极短句占比
        r["long_ratio"] = sum(1 for x in sn if x >= 50) / len(sn)    # 极长句占比
    else:
        r["sent_cv"] = None; r["sent_mean"] = None
        r["short_ratio"] = None; r["long_ratio"] = None

    # 2. 段落结构
    pl = [len(p) for p in paragraphs(text)]
    if len(pl) >= 4:
        m = sum(pl) / len(pl)
        var = sum((x - m) ** 2 for x in pl) / len(pl)
        r["para_count"] = len(pl)
        r["para_cv"] = (var ** 0.5) / m if m else 0
        r["para_mean"] = m
    else:
        r["para_count"] = len(pl); r["para_cv"] = None; r["para_mean"] = None

    # 3. 标点密度（每千字标点数）
    punct = len(re.findall(r"[，。；、：？！“”‘’（）…—]", text))
    r["punct_density"] = punct / max(len(text) / 1000.0, 0.01)

    return r
