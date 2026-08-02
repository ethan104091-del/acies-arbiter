#!/usr/bin/env python3
"""把觀戰席的 Markdown 戰史編成一份印刷級 HTML → Chrome headless 轉 PDF。"""
import re, html, subprocess, os, signal, time
from pathlib import Path

OBS = Path.home() / "Desktop" / "料鋒_觀戰席"
OUT_HTML = OBS / "料鋒_純戰場_戰史.html"
OUT_PDF = OBS / "料鋒_純戰場_戰史.pdf"


# ── 極簡 Markdown → HTML（只支援本文用到的語法）────────────────────
def md2html(md):
    out, i = [], 0
    lines = md.split("\n")
    in_code = in_table = in_list = False
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append('<pre class="map">')
                in_code = True
            i += 1
            continue
        if in_code:
            out.append(html.escape(ln))
            i += 1
            continue
        # 表格
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not in_table:
                out.append('<table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
                if i + 1 < len(lines) and set(lines[i + 1].replace("|", "").replace(":", "").strip()) <= {"-", " "}:
                    i += 1
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            i += 1
            continue
        elif in_table:
            out.append("</tbody></table>")
            in_table = False
        # 清單
        m = re.match(r"^(\s*)[-*] (.*)$", ln)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(m.group(2))}</li>")
            i += 1
            continue
        m = re.match(r"^(\d+)\. (.*)$", ln)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f'<li><span class="num">{m.group(1)}.</span> {inline(m.group(2))}</li>')
            i += 1
            continue
        if in_list and ln.strip() == "":
            out.append("</ul>")
            in_list = False
        # 標題 / 分隔線 / 引言
        if ln.startswith("#"):
            lvl = len(ln) - len(ln.lstrip("#"))
            txt = ln.lstrip("#").strip()
            cls = ""
            if "══" in txt:
                txt = txt.replace("═", "").strip()
                cls = ' class="tick"'
            out.append(f"<h{min(lvl,4)}{cls}>{inline(txt)}</h{min(lvl,4)}>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
        elif ln.strip() in ("---", "***"):
            out.append('<hr>')
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    if in_table:
        out.append("</tbody></table>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def inline(t):
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)
    return t


CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Songti TC","Songti SC","PingFang TC",serif; font-size: 10.5pt;
       line-height: 1.75; color: #1a1a1a; margin: 0; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: center;
         text-align: center; page-break-after: always; }
.cover .zh { font-size: 40pt; letter-spacing: .35em; font-weight: 600; margin: 0 0 6mm 0; }
.cover .sub { font-size: 15pt; letter-spacing: .12em; color: #555; margin-bottom: 22mm; }
.cover .vs { font-size: 13pt; line-height: 2.2; }
.cover .vs b { font-weight: 600; }
.cover .score { margin-top: 20mm; font-size: 26pt; font-weight: 600; letter-spacing: .05em; }
.cover .meta { margin-top: 18mm; font-size: 9.5pt; color: #666; line-height: 2; }
.rule { width: 46mm; height: 1px; background: #333; margin: 8mm auto; }
h1 { font-size: 19pt; margin: 0 0 4mm; padding-bottom: 2.5mm; border-bottom: 2px solid #222;
     page-break-after: avoid; }
h1.tick { page-break-before: always; font-size: 17pt; letter-spacing: .03em; }
h2 { font-size: 13.5pt; margin: 7mm 0 2.5mm; padding-left: 2.5mm; border-left: 3.5px solid #444;
     page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 5mm 0 2mm; color: #333; page-break-after: avoid; }
h4 { font-size: 10.5pt; margin: 4mm 0 1.5mm; color: #444; }
p { margin: 0 0 2.2mm; text-align: justify; }
strong { font-weight: 600; }
code { font-family: "Menlo",monospace; font-size: 8.8pt; background: #f2f2f0;
       padding: .5px 2.5px; border-radius: 2px; }
pre.map { font-family: "Menlo",monospace; font-size: 5.4pt; line-height: 1.28;
          background: #fbfbf9; border: 1px solid #ddd; padding: 3mm; overflow: hidden;
          page-break-inside: avoid; white-space: pre; letter-spacing: -.2px; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0 4mm; font-size: 9pt;
        page-break-inside: avoid; }
th { background: #efefec; border: 1px solid #ccc; padding: 1.6mm 2mm; text-align: left;
     font-weight: 600; }
td { border: 1px solid #ddd; padding: 1.4mm 2mm; vertical-align: top; }
ul { margin: 1.5mm 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1.2mm; }
li .num { font-weight: 600; margin-right: 1mm; }
blockquote { margin: 3mm 0; padding: 2.5mm 4mm; background: #f7f7f4;
             border-left: 3px solid #999; font-size: 9.5pt; color: #333; }
hr { border: none; border-top: 1px solid #ddd; margin: 6mm 0; }
.toc { page-break-after: always; }
.toc h1 { border: none; }
.toc ol { font-size: 11pt; line-height: 2.4; padding-left: 7mm; }
.part { page-break-before: always; text-align: center; padding-top: 70mm; }
.part .k { font-size: 11pt; letter-spacing: .5em; color: #777; }
.part .t { font-size: 26pt; font-weight: 600; margin-top: 6mm; letter-spacing: .1em; }
.part .d { font-size: 10pt; color: #666; margin-top: 8mm; line-height: 1.9; }
"""


def part(kicker, title, desc=""):
    return (f'<div class="part"><div class="k">{kicker}</div><div class="t">{title}</div>'
            f'<div class="d">{desc}</div></div>')


def main():
    hist = (OBS / "戰報_實時.md").read_text()
    # 去掉開頭那份 tick 0 前的 god_md 傾印（重複資訊）
    hist = hist.split("# ⚠ 裁判勘誤紀錄")[0].split("# ══════════ Tick 0")[0] + \
        "# ══════════ Tick 0" + hist.split("# ══════════ Tick 0", 1)[1]
    hist = re.sub(r"^# 純戰場 實時戰史（上帝視角）.*?(?=# ══)", "", hist, flags=re.S)
    summary = (OBS / "00_終局總結.md").read_text()
    setup = (OBS / "00_對局說明.md").read_text()

    # 附錄 A：雙方每 tick 的作戰意圖
    intents = []
    for n in range(9):
        f = OBS / f"雙方命令_T{n}.md"
        if not f.exists():
            continue
        txt = f.read_text()
        blue, red = txt.split("## 紅軍")[0], "## 紅軍" + txt.split("## 紅軍", 1)[1]

        def grab(t):
            m = re.search(r"## 意圖\s*\n(.*?)(?=\n## )", t, flags=re.S)
            return m.group(1).strip() if m else "（未載明）"
        intents.append(f"## Tick {n}\n\n### 藍軍（Claude Opus 5）\n\n{grab(blue)}\n\n"
                       f"### 紅軍（Codex gpt-5.6-terra）\n\n{grab(red)}\n")
    appendix_a = "# 附錄 A：雙方逐 tick 作戰意圖對照\n\n" \
        "這是兩位 AI 指揮官每個 tick 在**只看得到自己視角**的前提下寫下的判斷原文，" \
        "包含他們的推理、算式與誤判。命令全文見資料夾內 `雙方命令_T*.md`。\n\n" + "\n".join(intents)

    maps = []
    for n in (0, 4, 8):
        p = OBS / f"地圖_T{n}.txt"
        if p.exists():
            maps.append(f"## Tick {n} 態勢\n\n```\n{p.read_text()}\n```\n")
    appendix_b = "# 附錄 B：關鍵態勢圖（上帝視角）\n\n" + "\n".join(maps)

    body = "\n".join([
        f'''<div class="cover">
  <div class="zh">料鋒</div>
  <div class="sub">ACIES ｜ 純戰場 The Open Field</div>
  <div class="rule"></div>
  <div class="vs">
    <b>Codex</b>（gpt-5.6-terra, reasoning high）執紅軍<br>
    <span style="color:#888">vs</span><br>
    <b>Claude Opus 5</b> subagent 執藍軍<br>
    <span style="font-size:10pt;color:#666">裁判：Claude Opus 5（上帝視角、中立解算）</span>
  </div>
  <div class="score">藍軍 8,813 : 1,790 紅軍</div>
  <div style="font-size:11pt;color:#555;margin-top:4mm">藍軍決定性勝利</div>
  <div class="meta">
    戰役時間　1944-08-25 06:00 – 08-27 12:00（48 小時／8 ticks）<br>
    對局日期　2026-07-25　｜　地圖 30×18，180° 旋轉對稱<br>
    完整戰史・逐項計算可驗算
  </div>
</div>''',
        '''<div class="toc"><h1>目次</h1><ol>
<li>序章：這是什麼對局</li>
<li>第一部　逐 tick 戰史（Tick 0 – Tick 8）</li>
<li>第二部　終局總結與覆盤</li>
<li>附錄 A　雙方逐 tick 作戰意圖對照</li>
<li>附錄 B　關鍵態勢圖</li>
</ol></div>''',
        "<h1>序章：這是什麼對局</h1>",
        md2html(setup.split("# 料鋒 Acies")[-1].split("\n", 1)[1]),
        md2html("""
## 對局如何保證公平

- **兩份指揮官手冊由同一個模板產出**，以 `diff` 驗證過除「allies/axis」一字外完全相同，包含後來追加的
  45 條裁判裁示與砲擊完整公式——**雙方永遠拿到一字不差的同一份規則**。
- **雙方戰報由同一個函式產生**（`brief_md(state, side)`，只差一個參數），內容包含：己方部隊完整資料、
  指揮所守備狀態、**僅列已偵獲的敵情**、延遲中的命令、雙方公開計分、己方可觀察日誌。
- **所有數值解算寫成程式**：移動速率、Dijkstra 路徑、確定性能見狀態、對稱偵察判定、補給走廊、
  資源消耗、砲擊解算、地面戰 Force Ratio、疲勞效應——對兩邊套同一份表，零擲骰。
- **裁判中立**：不給任何一方戰術建議；每一次裁量判斷都在戰報寫明「怎麼判、為什麼」；
  每一次裁判自身的錯誤都公開自曝，並明確說出該次錯誤對哪一方不利。

## 情報不對稱如何維持

雙方各只能看到自己偵獲的敵軍。視距（切比雪夫距離，白天／夜間）：師級 **3／2**、特戰旅 **4／3**、
拉出的偵察營 **5／3**。目標的能見狀態由其自身處境決定（開闊移動 EXPOSED、開闊靜止 STANDARD、
森林移動 CAMOUFLAGED、森林靜止滿 2hr CONCEALED；特戰旅永遠好一級），
CAMOUFLAGED 需 ≤2 格、CONCEALED 需 ≤1 格才會被發現。指揮所位置須靠偵察摸到 2 格內（夜 1 格）。
"""),
        part("PART ONE", "逐 tick 戰史", "1944-08-25 06:00 – 08-27 12:00<br>八個 tick、四十八小時"),
        md2html(hist),
        part("PART TWO", "終局總結與覆盤", "分數怎麼跑出來・決定勝負的三件事<br>紅軍做對的事・裁判過失全紀錄"),
        md2html(summary.split("\n", 1)[1]),
        part("APPENDIX", "附錄", "雙方作戰意圖對照・關鍵態勢圖"),
        md2html(appendix_a),
        md2html(appendix_b),
    ])
    OUT_HTML.write_text(f"<!doctype html><html><head><meta charset='utf-8'>"
                        f"<title>料鋒 純戰場戰史</title><style>{CSS}</style></head>"
                        f"<body>{body}</body></html>")
    print("✅ HTML", OUT_HTML, OUT_HTML.stat().st_size, "bytes")

    # ── Chrome headless → PDF（自訂 profile；印完主動收，不 pkill）──
    prof = Path("/private/tmp/claude-501/-Users-ethan/cc3113fc-aaac-4221-a45c-761794239adb/scratchpad/chrome_prof")
    prof.mkdir(exist_ok=True)
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    p = subprocess.Popen([chrome, "--headless", "--disable-gpu", "--no-first-run",
                          f"--user-data-dir={prof}", "--no-pdf-header-footer",
                          f"--print-to-pdf={OUT_PDF}", f"file://{OUT_HTML}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(1)
        if OUT_PDF.exists() and p.poll() is not None:
            break
    if p.poll() is None:
        p.send_signal(signal.SIGTERM)
        time.sleep(2)
        if p.poll() is None:
            p.kill()
    print("✅ PDF", OUT_PDF, OUT_PDF.stat().st_size if OUT_PDF.exists() else "FAILED", "bytes")


main()
