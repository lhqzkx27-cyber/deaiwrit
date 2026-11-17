# -*- coding: utf-8 -*-
"""run_detect.py —— deaiwrit skill 的检测入口（供任何 agent 调用）。
用法:
  python run_detect.py --text "<中文文本>"         单段文本打分
  python run_detect.py --file path.txt             单个文件打分
  python run_detect.py --dir path --out report.csv 批量目录打分
输出：打分 + 分级(clean/mild/ai) + 命中信号清单，适合被 agent 读取判断。
"""
import os, sys, argparse, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import detect_ai as d


def fmt_one(r):
    return {
        "length": r["length"],
        "score": r["score"],
        "class": d.classify(r["score"]),
        "strong_hits": r["jie_ti_hits"],
        "weak_hits": r["mo_hu_hits"],
        "explain_verbs": r["explain"],
        "struct": r["struct"],
        "genre": r["genre"],
        "is_verse": r["is_verse"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--dir")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.text:
        r = d.ai_score(args.text)
        out = fmt_one(r)
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json
              else f"{out['class']}  score={out['score']}  hits={out['strong_hits']+out['weak_hits']}")
        return

    if args.file:
        with open(args.file, encoding="utf-8", errors="ignore") as f:
            t = f.read()
        r = d.ai_score(t)
        out = fmt_one(r)
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json
              else f"{out['class']}  score={out['score']}  len={out['length']}")
        return

    if args.dir:
        rows = d.scan_dir(args.dir)
        if args.out:
            import csv
            with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["file","chars","score","class",
                                                  "jie_ti","mo_hu","fanhua_subj",
                                                  "he_xi_ni","jie_wei"])
                w.writeheader()
                for r in rows:
                    if "error" not in r:
                        w.writerow(r)
            print("written:", args.out)
        else:
            for r in rows:
                print(r)
        return


if __name__ == "__main__":
    main()
