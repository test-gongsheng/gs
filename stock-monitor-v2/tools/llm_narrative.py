#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_narrative.py — 深度报告"大模型大脑"

在模板化深度报告末尾注入/刷新一节《AI实时研判（LLM深度分析）》，
由大模型基于报告原文 + 当日事件关联池(curated_impacts.json) 现场撰写：
消息面与事件驱动（含产业链间接推理）、利多与压制、综合研判、未来观察点。

用法：
    python3 tools/llm_narrative.py            # 今日全部已有深度报告
    python3 tools/llm_narrative.py 601133 301308  # 指定股票

设计原则：
- API失败/超时：跳过该股票，保留模板报告（降级不炸流水线）
- 幂等：已存在的本节会被替换，不会叠加
- 禁编造：所有数字必须来自输入材料，提示词里硬性约束
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

_CACHE = {}

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DATA = ROOT / "data"
CURATED = ROOT / "data" / "curated_impacts.json"
OPENCLAW_CFG = Path("/root/.openclaw/openclaw.json")

SECTION_HEAD = "## 十二、AI实时研判（LLM深度分析）"
DISCLAIMER_MARK = "**免责声明：**"


def load_llm_cfg():
    """从 openclaw.json 读 kimi-coding provider 配置；失败回退环境变量。"""
    try:
        cfg = json.load(open(OPENCLAW_CFG))
        prov = cfg["models"]["providers"]["kimi-coding"]
        return {
            "base": prov["baseUrl"].rstrip("/"),
            "key": prov["apiKey"],
            "headers": dict(prov.get("headers", {})),
            "model": prov["models"][0]["id"],
        }
    except Exception:
        import os
        key = os.environ.get("KIMI_API_KEY")
        if not key:
            raise RuntimeError("无可用LLM配置（openclaw.json与环境变量均缺失）")
        return {
            "base": "https://agent-gw.kimi.com/coding",
            "key": key,
            "headers": {},
            "model": "k2d8-preview",
        }


def chat(cfg, prompt, max_tokens=None, timeout=300, retries=1, think=False, budget=8000):
    if max_tokens is None:
        max_tokens = (budget + 8000) if think else 8000
    thinking = ({"type": "enabled", "budget_tokens": budget}
                if think else {"type": "disabled"})
    body = {
        "model": cfg["model"],
        "max_tokens": max_tokens,
        "thinking": thinking,
        "messages": [{"role": "user", "content": prompt}],
    }
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                cfg["base"] + "/v1/messages",
                data=json.dumps(body).encode(),
                headers={
                    "content-type": "application/json",
                    "x-api-key": cfg["key"],
                    "anthropic-version": "2023-06-01",
                    **cfg["headers"],
                },
                method="POST",
            )
            eff_timeout = max(timeout, 900) if think else timeout
            with urllib.request.urlopen(req, timeout=eff_timeout) as r:
                d = json.load(r)
            usage = d.get('usage') or {}
            if usage:
                _CACHE['last_usage'] = usage
            return "".join(
                b.get("text", "") for b in d.get("content", []) if b.get("type") == "text"
            )
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(3)
    raise RuntimeError(f"LLM调用失败: {last}")


def latest_report(code):
    files = sorted(REPORTS.glob(f"deep_analysis_{code}_*.md"))
    return files[-1] if files else None


def load_impacts(code):
    """从 curated_impacts.json 取与该股相关的事件。"""
    if not CURATED.exists():
        return []
    try:
        data = json.load(open(CURATED))
    except Exception:
        return []
    out = []
    for imp in data.get("impacts", []):
        for st in imp.get("stocks", []):
            if st.get("code") == code:
                out.append({
                    "theme": imp.get("theme", ""),
                    "news_title": imp.get("news_title", ""),
                    "news_time": imp.get("news_time", ""),
                    "source": imp.get("source", ""),
                    "summary": imp.get("summary", ""),
                    "direction": imp.get("direction", ""),
                    "logic": st.get("logic", ""),
                    "confidence": st.get("confidence", ""),
                })
    return out


PROMPT_TMPL = """你是卖方研报级A股分析师。基于以下材料，为{code} {name}撰写深度报告的收尾章节。

【报告原文】
{report}

【今日事件关联池（已做过产业链映射）】
{impacts}

请只输出Markdown章节，章节标题必须是「{head}」，包含四个小节：
### 1. 消息面与事件驱动（近3日）
### 2. 利多与压制
### 3. 综合研判与持仓视角（衔接报告中的中轴价格与浮动仓策略）
### 4. 未来3日观察点

硬性规则：
- 只能使用材料中出现的数字与事实，禁止编造任何数据；材料没有的不要写
- 事件条目注明来源与时间；间接关联（如行业新闻→该股订单/毛利）必须给出推理链
- 双面论证：利多与压制都要写透。压制小节必须结构化：逐条编号（①②③...），每条含具体数字/事实+来源，禁止含糊带过
- 进展链：同一事件在近3日多日/多源出现（如首曝→跟进→验证命中），用「日期+事件→日期+进展」的时间线呈现，禁止平铺
- 弱相关、判断不了的不写
- 全文不少于2000字、不超过2600字，展开写透，语言精炼，不要AI腔套话"""


def extract_name(report_text, code):
    m = re.search(r"^#\s*(.+?)\b" + re.escape(code), report_text, re.M)
    if m:
        return m.group(1).strip(" #·-")[:12] or code
    return code


def strip_old_section(text):
    """删除旧的AI研判节（幂等）。"""
    start = text.find(SECTION_HEAD)
    if start == -1:
        return text
    end = text.find(DISCLAIMER_MARK, start)
    if end == -1:
        return text[:start].rstrip() + "\n"
    # 回看 DISCLAIMER 前的分隔线/空行
    prefix = text[:start].rstrip() + "\n\n"
    suffix = text[end:]
    return prefix + suffix


def inject(text, section_md):
    text = strip_old_section(text)
    section_md = section_md.strip()
    if not section_md.startswith(SECTION_HEAD):
        section_md = SECTION_HEAD + "\n\n" + section_md
    idx = text.find(DISCLAIMER_MARK)
    if idx == -1:
        return text.rstrip() + "\n\n" + section_md + "\n"
    # 在免责声明之前插入；若其前有 --- 分隔线，插到分隔线之前
    before = text[:idx]
    m = re.search(r"(\n---\s*\n)\s*$", before)
    if m:
        cut = before[: m.start()].rstrip()
        return cut + "\n\n" + section_md + "\n\n---\n\n" + text[idx:]
    return before.rstrip() + "\n\n" + section_md + "\n\n" + text[idx:]


def enhance_one(code, cfg, think=False, budget=12000):
    f = latest_report(code)
    if not f:
        return None, "无报告文件"
    report = f.read_text(encoding="utf-8")
    name = extract_name(report, code)
    impacts = load_impacts(code)
    impacts_txt = json.dumps(impacts, ensure_ascii=False, indent=1) if impacts else "（今日无关联事件）"
    prompt = PROMPT_TMPL.format(code=code, name=name, report=report[:12000],
                                impacts=impacts_txt, head=SECTION_HEAD)
    t0 = time.time()
    section = chat(cfg, prompt, think=think, budget=budget)
    if not section.strip():
        return None, "LLM返回空"
    new_text = inject(report, section)
    if new_text != report:
        f.write_text(new_text, encoding="utf-8")
    # 用量回显+落盘累计（data/已gitignore）
    usage = _CACHE.get('last_usage') or {}
    if usage:
        try:
            import datetime as _dt
            ufile = DATA / f"llm_usage_{_dt.date.today()}.json"
            udata = json.loads(ufile.read_text(encoding='utf-8')) if ufile.exists() else {'calls': 0, 'input': 0, 'output': 0}
            udata['calls'] += 1
            udata['input'] += usage.get('input_tokens', 0)
            udata['output'] += usage.get('output_tokens', 0)
            ufile.write_text(json.dumps(udata, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass
    ustr = f" | in {usage.get('input_tokens','?')}/out {usage.get('output_tokens','?')}" if usage else ''
    return f.name, f"{time.time()-t0:.0f}s/{len(section)}字{ustr}"


def main():
    _argv = sys.argv[1:]
    think = "--think" in _argv
    budget = 12000
    skip = set()
    for i, a in enumerate(_argv):
        if a == "--budget" and i + 1 < len(_argv):
            budget = int(_argv[i + 1])
            skip.update({i, i + 1})
    args = [a for j, a in enumerate(_argv) if j not in skip and not a.startswith("--")]
    if args:
        codes = args
    else:
        today = time.strftime("%Y-%m-%d")
        codes = sorted(p.stem.split("_")[2] for p in REPORTS.glob(f"deep_analysis_*_{today}.md"))
    if not codes:
        print("无今日报告可增强")
        return
    try:
        cfg = load_llm_cfg()
    except Exception as e:  # noqa: BLE001
        print(f"LLM配置不可用（{e}），跳过增强，保留模板报告")
        return
    ok, fail = [], []
    for code in codes:
        try:
            fname, stat = enhance_one(code, cfg, think=think, budget=budget)
            if fname is None:
                fail.append(code)
                print(f"[FAIL] {code}: {stat}")
            else:
                ok.append(code)
                print(f"[OK] {code} -> {fname} ({stat})")
        except Exception as e:  # noqa: BLE001
            fail.append(code)
            print(f"[FAIL] {code}: {e}")
        time.sleep(1)
    print(f"\n完成：成功{len(ok)}，失败/降级{len(fail)} {fail if fail else ''}")


if __name__ == "__main__":
    main()
