# -*- coding: utf-8 -*-
"""
detect_ai.py —— 把 SKILL.md 的"通用 AI 味标志"代码化，做成确定性检测器。

作用：
1. 对任意一段中文文本打分（0~N，命中一条 +1）。
2. 供批量自测使用：输入一个文本目录，逐篇输出 AI 味得分。
3. 规则全部来自 SKILL.md 的"通用 AI 味标志"，可审计、可调整。

用法：
  python detect_ai.py --file path/to.txt
  python detect_ai.py --dir path/to/dir --out report.csv
  python detect_ai.py --dir path/to/dir --out report.csv --json
"""
import os, re, sys, csv, json, argparse

# ---- 来自 SKILL.md 的规则 ----
JIE_TI = [
    "综上所述", "总而言之", "由此可见", "从这个意义上说",
    "值得我们深思", "值得我们去", "具有现实意义", "深远的意义",
    "随着…的发展", "随着...的发展", "在…的大背景下", "在...的大背景下",
    "众所周知", "不难发现", "让我们共同努力", "让我们一起",
    "具有重要", "发挥着重要作用", "具有不可替代的作用", "这不仅是…更是…",
    "帮助我们认识自我", "明确方向", "具有极大的价值", "巨大的价值",
    "重要的意义", "认识自我", "共同迈向更好的明天", "更加光明和美好的明天",
    "推动着我们", "塑造我们的品格", "服务于个人成长", "实现自我价值",
    "提升自我", "书写属于我们的新篇章", "不断前行", "更好的未来", "拥抱它吧",
]
# 解释性动词：真实文本(尤其百科/说明)正当高频使用(0.2-0.4%/篇)，
# 单独出现不算AI味；但AI会反复堆砌。故设“中间权重×0.5”，不单独定罪。
EXPLAIN_VERBS = ["象征着", "意味着", "体现了", "表达了", "指出了", "代表着",
                 "反映了", "标志着", "揭示了", "诠释了", "凸显了"]
MOHU = [
    "很多", "很多年", "一些", "长期", "日益", "逐渐", "深刻", "深远",
    "极大", "非常", "十分", "很显著", "具有重大",
]
FANHUA_SUBJ = ["许多人", "大家", "人们", "我们每个人", "广大", "越来越多的人"]
HE_XI_NI = ["既要…又要", "有利有弊", "既有利又有弊", "一方面…另一方面"]

# 总结式结尾信号（判断句/词）
# 注："让我们"太宽泛（"让我们小心"是自然口语），只保留AI口号形态
JIE_WEI_CI = ["综上所述", "总的来说", "总之", "最后，我想说",
              "让我们共同努力", "让我们一起", "让我们携手"]

PAT_JIETI = [re.compile(x) for x in JIE_TI]
PAT_MOHU = [re.compile(x) for x in MOHU]
PAT_SUBJ = [re.compile(x) for x in FANHUA_SUBJ]
PAT_HXN = [re.compile(x) for x in HE_XI_NI]
PAT_EXPLAIN = [re.compile(x) for x in EXPLAIN_VERBS]

# ---- 文体感知：学术类文本的惯用词（真实学术写作正当使用，不作AI味定罪）----
ACADEMIC_MARKERS = [
    "关键词", "摘要", "引证", "文献", "本文认为", "综上所述", "研究指出",
    "定量", "样本", "数据", "文献综述", "方法论", "结果表明", "期刊",
    "第.*章", "参考文献", "实验", "调查显示", "学者", "理论",
    "纵观", "本文", "论文", "研究",
]
RE_ACAD = [re.compile(x) for x in ACADEMIC_MARKERS]

# 学术 AI 腔（无论何种文体都算）：空洞总结 + 无据口号
ACAD_AI_TI = [
    "综上所述，本文", "因此，我们应", "总之，从而", "通过以上分析",
    "综上所述，该项研究", "具有重要的理论意义和现实意义",
    "为…提供了重要参考", "为...提供了重要参考",
]

def detect_genre(text: str) -> str:
    """粗判文体：'academic'(学术) / 'other'(散文/小说/议论等)。"""
    score = 0
    for p in RE_ACAD:
        if p.search(text):
            score += 1
    # 学术标志弱：出现2处以上 或 含"关键词/参考文献/摘要/第X章"结构化
    if score >= 2:
        return "academic"
    if re.search(r"(关键词|参考文献|摘要|引言|结论|文献综述)", text):
        return "academic"
    return "other"


def is_verse(text: str) -> bool:
    """判断是否为规整性文体（诗歌/词/典籍条列）。这些文体句段天然等长，
    结构信号(CV)对它们会误伤，应豁免。特征：短行密集、每行短。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    # 算"短行"占比：行数>=8且多数行<=25字 => 分行密集的诗歌/条列
    if len(lines) < 8:
        return False
    short = sum(1 for l in lines if len(l) <= 25)
    if short / len(lines) >= 0.7:
        return True
    return False

# ---- 结构层指标：句长变异系数 (CV) ----
# 人类叙述句长参差(CV≈0.6+)，AI 机械文本句长均匀(CV≈0.17)。
# 实测(110篇真实散文 vs 40篇AI长文)：真实 CV<=0.4 仅1%，AI CV<=0.4 达100%。
def sentence_length_cv(text: str):
    """返回 (CV, 句数)。句子按句号/问号/感叹号/分号切分。"""
    parts = re.split(r"[。！？!?；;]", text)
    lens = [len(p.strip()) for p in parts if len(p.strip()) >= 4]
    if len(lens) < 6:
        return None, len(lens)
    m = sum(lens) / len(lens)
    if m == 0:
        return None, len(lens)
    var = sum((x - m) ** 2 for x in lens) / len(lens)
    return (var ** 0.5) / m, len(lens)


# ---- 结构层指标：段落变异系数 (para_cv) ----
# 人类段落长短参差(para_cv 中位≈0.8)，AI 机械文本段落等长(para_cv≈0.32)。
# 实测(2320篇真实): para_cv<=0.30 仅0.39%、<=0.25 仅0.22%；AI 中位0.32。
# 设 para_cv<=0.25 作强信号(真实0.22%误伤)、0.25-0.40 作弱佐证。
def paragraph_cv(text: str):
    """返回 (para_cv, 段数)。段按换行切。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) >= 5]
    if len(paras) < 5:
        return None, len(paras)
    pl = [len(p) for p in paras]
    m = sum(pl) / len(pl)
    if m == 0:
        return None, len(paras)
    var = sum((x - m) ** 2 for x in pl) / len(pl)
    return (var ** 0.5) / m, len(paras)


def ai_score(text: str) -> dict:
    """对一段文本算 AI 味指标，返回每种信号命中的次数与加权分。

    文体感知：学术类文本中，"众所周知/本文认为/具有重要"等是真实学术写作
    的惯用词（正当使用），不作 AI 味定罪；只有出现"学术AI腔"（如无据的
    "综上所述"+空洞结论）才扣分。散文/小说等非学术文体则从严。
    """
    if not text:
        return {"length": 0, "score": 0, "jie_ti": 0, "mo_hu": 0,
                "fanhua_subj": 0, "he_xi_ni": 0, "jie_wei": 0,
                "jie_ti_hits": [], "mo_hu_hits": [], "genre": "other"}
    genre = detect_genre(text)
    is_acad = (genre == "academic")

    # 强信号计数
    jie_ti = 0
    jh = []
    for p in PAT_JIETI:
        c = len(p.findall(text))
        if c:
            # 学术文体中，"众所周知/具有重要/重要意义"等学术惯用词降权为弱
            if is_acad and p.pattern in ("众所周知", "具有重要", "具有重要意义",
                                          "深远的意义", "一览"):
                jh.append(p.pattern)
                continue  # 不计入强信号
            jie_ti += c
            jh.append(p.pattern)
    hxn = 0
    for p in PAT_HXN:
        hxn += len(p.findall(text))
    jie_wei = 0
    for p in [re.compile(c) for c in JIE_WEI_CI]:
        jie_wei += len(p.findall(text))
    # 学术AI腔（文体无关，一律强信号）
    acad_ai = 0
    for p in [re.compile(c) for c in ACAD_AI_TI]:
        acad_ai += len(p.findall(text))
    # 解释性动词单独计数（中间权重）：真实单次正当，AI反复堆砌才算
    explain = 0
    for p in PAT_EXPLAIN:
        explain += len(p.findall(text))

    # 弱信号计数
    mo_hu = 0
    mh = []
    for p in PAT_MOHU:
        c = len(p.findall(text))
        if c:
            mo_hu += c
            mh.append(p.pattern)
    fanhua = 0
    for p in PAT_SUBJ:
        fanhua += len(p.findall(text))

    # 结构层指标：句长CV + 段落CV。仅对非规整文体启用——
    # 诗歌/典籍等规整文体句段天然等长，结构信号会误伤（真实现代诗4.9%被误伤）。
    struct_hits = 0
    struct_soft = 0
    struct_info = None
    is_verse_txt = is_verse(text)
    if len(text) >= 400 and not is_verse_txt:
        cv, nsen = sentence_length_cv(text)
        if cv is not None:
            if cv <= 0.20:
                struct_hits = 1.0
                struct_info = f"sent_cv={cv:.2f}"
            elif cv <= 0.35:
                struct_soft = 0.3
                struct_info = f"sent_cv={cv:.2f}"
            else:
                struct_info = f"sent_cv={cv:.2f}"
        # 结构层指标2：段落CV。真实para_cv<=0.25仅0.22%，AI中位0.32。
        pcv, npara = paragraph_cv(text)
        if pcv is not None:
            if pcv <= 0.25:
                struct_hits = max(struct_hits, 1.0)
                struct_info = f"para_cv={pcv:.2f}"
            elif pcv <= 0.40:
                struct_soft = max(struct_soft, 0.3)
                struct_info = (struct_info or "") + f";para_cv={pcv:.2f}"

    # 加权分：强信号×2，解释性动词×0.5，弱信号×0.3。按长度归一。
    # 结构强信号是"整篇机械"属性，不随长度稀释，作绝对加分；弱佐证×0.3随归一。
    strong = jie_ti + hxn + jie_wei + acad_ai
    mid = explain
    weak = mo_hu + fanhua
    norm = max(len(text) / 1000.0, 0.2)
    base_score = (strong * 2.0 + mid * 0.5 + weak * 0.3 + struct_soft) / norm
    score = base_score + (4.0 if struct_hits == 1.0 else 0)   # 结构强(整篇机械)绝对+4
    # 强信号门槛：仅靠弱/中间信号(无强信号、无结构强)时绝不判"ai(需改)"。
    # 结构强信号(整篇机械)算强证据，不受此限。防短文本被"非常/一些"误伤。
    if strong == 0 and struct_hits != 1.0 and score >= 3.0:
        score = 2.9

    return {"length": len(text), "score": round(score, 2),
            "strong": strong, "mid": mid, "weak": weak,
            "struct": struct_info, "genre": genre,
            "jie_ti": jie_ti, "mo_hu": mo_hu, "fanhua_subj": fanhua,
            "he_xi_ni": hxn, "jie_wei": jie_wei, "explain": explain,
            "is_verse": is_verse_txt,
            "jie_ti_hits": jh, "mo_hu_hits": mh}

def classify(score: float) -> str:
    # 每千字的加权 AI 味分。阈值来自 380 篇自测调参。
    if score < 1.0:
        return "clean"      # 基本干净
    if score < 3.0:
        return "mild"       # 有AI味
    return "ai"             # 需改

def scan_dir(directory: str) -> list:
    rows = []
    for fn in sorted(os.listdir(directory)):
        if not fn.lower().endswith((".txt", ".md")):
            continue
        path = os.path.join(directory, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            rows.append({"file": fn, "error": str(e)})
            continue
        r = ai_score(text)
        rows.append({"file": fn, "chars": r["length"], "score": r["score"],
                     "class": classify(r["score"]),
                     "jie_ti": r["jie_ti"], "mo_hu": r["mo_hu"],
                     "fanhua_subj": r["fanhua_subj"], "he_xi_ni": r["he_xi_ni"],
                     "jie_wei": r["jie_wei"]})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="单个文件")
    ap.add_argument("--dir", help="目录批量")
    ap.add_argument("--out", help="输出 CSV 路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        r = ai_score(text)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("class:", classify(r["score"]))
        return

    if args.dir:
        rows = scan_dir(args.dir)
        # 统计
        total = len(rows)
        clean = sum(1 for r in rows if r.get("class") == "clean")
        mild = sum(1 for r in rows if r.get("class") == "mild")
        ai = sum(1 for r in rows if r.get("class") == "ai")
        print(f"总篇数: {total}  干净:{clean}  轻度:{mild}  AI味:{ai}")
        if args.out:
            with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["file","chars","score","class",
                                                  "jie_ti","mo_hu","fanhua_subj",
                                                  "he_xi_ni","jie_wei"])
                w.writeheader()
                for r in rows:
                    if "error" not in r:
                        w.writerow(r)
            print("已写:", args.out)
        return

if __name__ == "__main__":
    main()
