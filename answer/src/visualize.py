"""Generate Chinese, paper-ready visualizations for the four questions."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw, ImageFont

from figure3_network_mpl import render as render_figure3


ROOT = Path(__file__).resolve().parents[2]
ANSWER = ROOT / "answer"
OUT = ANSWER / "figures"
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
W, H = 2000, 1200

COLORS = {
    "A": "#4E79A7",
    "B": "#F28E2B",
    "C": "#59A14F",
    "冲突": "#D62728",
    "保留": "#7F8C8D",
    "调整": "#4E79A7",
    "撤销": "#D62728",
    "频移": "#4E79A7",
    "时移": "#F28E2B",
    "间隔调整": "#9C6ADE",
    "新增": "#E15759",
    "网格": "#D9DEE7",
    "文字": "#243447",
    "次文字": "#657786",
}


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def text_size(draw, value, f):
    box = draw.textbbox((0, 0), str(value), font=f)
    return box[2] - box[0], box[3] - box[1]


def center_text(draw, xy, value, f, fill=COLORS["文字"]):
    w, h = text_size(draw, value, f)
    draw.text((xy[0] - w / 2, xy[1] - h / 2), str(value), font=f, fill=fill)


def right_text(draw, xy, value, f, fill=COLORS["文字"]):
    w, h = text_size(draw, value, f)
    draw.text((xy[0] - w, xy[1] - h / 2), str(value), font=f, fill=fill)


def new_canvas(title: str, subtitle: str | None = None):
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.text((80, 46), title, font=font(38, True), fill=COLORS["文字"])
    if subtitle:
        d.text((82, 103), subtitle, font=font(22), fill=COLORS["次文字"])
    d.line((80, 150, W - 80, 150), fill="#D5DCE5", width=2)
    return im, d


def save(im: Image.Image, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / name, dpi=(220, 220))


def parse_interval(value):
    a, b = map(int, re.findall(r"-?\d+", str(value)))
    return a, b


def read_source():
    book = openpyxl.load_workbook(ROOT / "附件/附件1.xlsx", data_only=True)
    plans = []
    for ident, freq, time, gap, count in list(book.active.values)[1:]:
        lo, hi = parse_interval(freq)
        start, end = parse_interval(time)
        plans.append({
            "id": str(ident), "lo": lo, "hi": hi, "start": start, "end": end,
            "gap": int(gap), "count": int(count),
        })
    book.close()
    return plans


def periods(p):
    duration = p["end"] - p["start"]
    gap = p.get("gap", 0)
    return [
        (p["start"] + k * (duration + gap), p["end"] + k * (duration + gap))
        for k in range(p["count"])
    ]


def load_json(rel):
    return json.loads((ANSWER / rel).read_text(encoding="utf-8"))


def axes(draw, box, x_max, y_max, x_label="时间（Δt）", y_label="频段（Δf）", x_ticks=None, y_ticks=None):
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline="#AAB7C4", width=2)
    x_ticks = x_ticks or list(range(0, x_max + 1, max(1, x_max // 5)))
    y_ticks = y_ticks or list(range(0, y_max + 1, max(1, y_max // 5)))
    for x in x_ticks:
        px = x0 + x / x_max * (x1 - x0)
        draw.line((px, y0, px, y1), fill=COLORS["网格"], width=1)
        center_text(draw, (px, y1 + 30), x, font(18), COLORS["次文字"])
    for y in y_ticks:
        py = y1 - y / y_max * (y1 - y0)
        draw.line((x0, py, x1, py), fill=COLORS["网格"], width=1)
        right_text(draw, (x0 - 16, py), y, font(18), COLORS["次文字"])
    center_text(draw, ((x0 + x1) / 2, y1 + 78), x_label, font(22), COLORS["文字"])
    center_text(draw, (x0 - 78, (y0 + y1) / 2), y_label, font(22), COLORS["文字"])


def tf_rect(draw, box, p, s, e, fill, outline=None, alpha=130, y_max=100, x_max=643):
    x0, y0, x1, y1 = box
    xa = x0 + s / x_max * (x1 - x0)
    xb = x0 + e / x_max * (x1 - x0)
    ya = y1 - p["hi"] / y_max * (y1 - y0)
    yb = y1 - p["lo"] / y_max * (y1 - y0)
    draw.rectangle((xa, ya, xb, yb), fill=fill + f"{alpha:02X}", outline=outline, width=1)


def draw_legend(draw, items, x=120, y=180, gap=190):
    xcur = x
    for label, color in items:
        draw.rounded_rectangle((xcur, y - 10, xcur + 24, y + 14), radius=4, fill=color)
        draw.text((xcur + 34, y - 11), label, font=font(20), fill=COLORS["文字"])
        xcur += gap


def draw_plan_stack(draw, box, plans, alpha=120, colors=None, skip_canceled=True):
    colors = colors or COLORS
    for p in plans:
        if skip_canceled and p.get("canceled", False):
            continue
        group = p["id"][0] if isinstance(p["id"], str) and p["id"][:1] in "ABC" else "C"
        c = colors.get(group, COLORS["新增"])
        for s, e in periods(p):
            tf_rect(draw, box, p, s, e, c, alpha=alpha, x_max=643)


def fig01_raw(source):
    im, d = new_canvas("图1  原始时频资源占用", "每个矩形表示一台装备的一次使用；只有时间区间和频段同时交叠才构成冲突")
    box = (150, 250, 1910, 1000)
    axes(d, box, 643, 100, x_ticks=[0, 100, 200, 300, 400, 500, 600], y_ticks=[0, 20, 40, 60, 80, 100])
    draw_plan_stack(d, box, source, alpha=90)
    draw_legend(d, [("A类装备", COLORS["A"]), ("B类装备", COLORS["B"]), ("C类装备", COLORS["C"])], 160, 195, 250)
    d.rounded_rectangle((1280, 175, 1870, 225), radius=8, fill="#F7F9FB", outline="#D5DCE5")
    d.text((1310, 190), "原始计划：150项", font=font(21), fill=COLORS["文字"])
    save(im, "图1_原始时频资源占用.png")


def draw_vbars(draw, box, labels, values, colors, max_value=None, value_suffix="", highlight=None):
    x0, y0, x1, y1 = box
    max_value = max_value or max(values) * 1.18
    max_value = max(max_value, 1)
    n = len(labels)
    slot = (x1 - x0) / n
    bar_w = min(120, slot * 0.62)
    for i, (lab, val) in enumerate(zip(labels, values)):
        cx = x0 + slot * (i + 0.5)
        top = y1 - val / max_value * (y1 - y0)
        col = colors[i] if isinstance(colors, list) else colors
        draw.rectangle((cx - bar_w / 2, top, cx + bar_w / 2, y1), fill=col)
        center_text(draw, (cx, top - 26), f"{val}{value_suffix}", font(21, True), col)
        center_text(draw, (cx, y1 + 32), lab, font(20), COLORS["文字"])
    for tick in range(0, int(max_value) + 1, max(1, int(max_value) // 5)):
        py = y1 - tick / max_value * (y1 - y0)
        draw.line((x0, py, x1, py), fill=COLORS["网格"], width=1)
        right_text(draw, (x0 - 15, py), tick, font(18), COLORS["次文字"])
    draw.line((x0, y0, x0, y1), fill="#AAB7C4", width=2)
    draw.line((x0, y1, x1, y1), fill="#AAB7C4", width=2)


def fig02_conflict_type(stats):
    im, d = new_canvas("图2  冲突类型统计", "问题1：按装备类别组合统计冲突装备对")
    labels = ["A-A", "A-B", "A-C", "B-B", "B-C", "C-C"]
    vals = [stats.get(k, 0) for k in ["AA", "AB", "AC", "BB", "BC", "CC"]]
    colors = ["#B7C9DC", COLORS["A"], "#76A5C8", "#F6C27A", "#D95F02", "#9FCB9B"]
    draw_vbars(d, (190, 300, 1840, 930), labels, vals, colors, max_value=210)
    d.text((1330, 245), "B-C冲突：181对，占60.94%", font=font(26, True), fill=COLORS["冲突"])
    d.text((1360, 285), "总冲突对数：297", font=font(23), fill=COLORS["文字"])
    save(im, "图2_冲突类型统计.png")


def fig03_network(q1):
    render_figure3()


def fig04_top(q1):
    pairs = [tuple(x) for x in q1["pairs"]]
    degree = Counter(x for e in pairs for x in e)
    top = degree.most_common(20)
    im, d = new_canvas("图4  装备冲突度排序", "问题1：冲突度 = 与该装备发生冲突的其他装备数量，展示前20台")
    x0, y0, x1, y1 = 360, 230, 1800, 1030
    maxv = max(v for _, v in top) + 1
    row_h = (y1 - y0) / len(top)
    for i, (ident, val) in enumerate(top):
        y = y0 + i * row_h + row_h / 2
        col = COLORS[ident[0]]
        d.rounded_rectangle((x0, y - 12, x0 + (x1-x0) * val / maxv, y + 12), radius=7, fill=col)
        right_text(d, (x0 - 22, y), ident, font(20, True), col)
        d.text((x0 + (x1-x0) * val / maxv + 16, y - 14), str(val), font=font(20, True), fill=COLORS["文字"])
        if i % 2 == 0:
            d.line((x0, y + row_h/2 - 2, x1, y + row_h/2 - 2), fill="#F1F4F7", width=1)
    for tick in range(0, maxv + 1):
        px = x0 + (x1 - x0) * tick / maxv
        d.line((px, y0 - 10, px, y1), fill=COLORS["网格"], width=1)
        center_text(d, (px, y1 + 28), tick, font(18), COLORS["次文字"])
    center_text(d, ((x0+x1)/2, y1 + 70), "冲突装备数（台）", font(22), COLORS["文字"])
    save(im, "图4_装备冲突度排序.png")


def fig05_q2_resolution(q2):
    stats = q2["stats"]
    labels = ["A类", "B类", "C类", "合计"]
    data = [
        [stats[g]["unchanged"] for g in "ABC"] + [sum(stats[g]["unchanged"] for g in "ABC")],
        [stats[g]["adjusted"] for g in "ABC"] + [sum(stats[g]["adjusted"] for g in "ABC")],
        [stats[g]["canceled"] for g in "ABC"] + [sum(stats[g]["canceled"] for g in "ABC")],
    ]
    im, d = new_canvas("图5  问题2冲突消解结果", "原样保留、调整、撤销三类状态互斥；最终执行144项计划")
    box = (220, 330, 1810, 940)
    maxv = 150
    n = len(labels); slot = (box[2]-box[0])/n; bar_w = 82
    bottoms = [0]*n
    for label, vals, key in zip(["原样保留", "调整", "撤销"], data, ["保留", "调整", "撤销"]):
        for i, v in enumerate(vals):
            cx = box[0] + slot*(i+0.5)
            top = box[3] - (bottoms[i]+v)/maxv*(box[3]-box[1])
            bottom = box[3] - bottoms[i]/maxv*(box[3]-box[1])
            d.rectangle((cx-bar_w/2, top, cx+bar_w/2, bottom), fill=COLORS[key])
            if v >= 8:
                center_text(d, (cx, (top+bottom)/2), v, font(20, True), "white")
            bottoms[i] += v
    for tick in range(0, 151, 30):
        py = box[3] - tick/maxv*(box[3]-box[1])
        d.line((box[0], py, box[2], py), fill=COLORS["网格"], width=1)
        right_text(d, (box[0]-15, py), tick, font(18), COLORS["次文字"])
    for i, lab in enumerate(labels):
        center_text(d, (box[0] + slot*(i+0.5), box[3]+32), lab, font(22, True), COLORS["文字"])
    draw_legend(d, [("原样保留", COLORS["保留"]), ("调整", COLORS["调整"]), ("撤销", COLORS["撤销"])], 270, 215, 220)
    unchanged_total = sum(stats[g]["unchanged"] for g in "ABC")
    adjusted_total = sum(stats[g]["adjusted"] for g in "ABC")
    canceled_total = sum(stats[g]["canceled"] for g in "ABC")
    d.text((1390, 215), f"{unchanged_total} + {adjusted_total} + {canceled_total} = 150", font=font(24, True), fill=COLORS["文字"])
    save(im, "图5_问题2消解结果.png")


def draw_tf_panel(d, box, plans, title, title_color, conflict_events=None, source_map=None):
    d.text((box[0], box[1]-58), title, font=font(28, True), fill=title_color)
    axes(d, box, 643, 100, x_ticks=[0, 200, 400, 600], y_ticks=[0, 50, 100])
    draw_plan_stack(d, box, plans, alpha=100)
    if conflict_events and source_map:
        for a, b, _, _, s, e in conflict_events:
            pa, pb = source_map[a], source_map[b]
            lo = max(pa["lo"], pb["lo"]); hi = min(pa["hi"], pb["hi"])
            q = {"lo": lo, "hi": hi}
            tf_rect(d, box, q, s, e, COLORS["冲突"], alpha=62)


def fig06_q2_before_after(source, q1, q2):
    im, d = new_canvas("图6  问题2消解前后时频占用对比", "左：原始方案及冲突区域；右：完成调整后的方案。红色区域为重复使用时段与频段的交集")
    left = (120, 300, 970, 970)
    right = (1030, 300, 1880, 970)
    source_map = {p["id"]: p for p in source}
    draw_tf_panel(d, left, source, "原始方案：297对冲突", COLORS["冲突"], q1["events"], source_map)
    active = [p for p in q2["plans"] if not p.get("canceled", False)]
    draw_tf_panel(d, right, active, "调整后：0对冲突", COLORS["A"])
    d.rounded_rectangle((730, 1030, 1250, 1090), radius=9, fill="#FDECEC", outline="#F2B3B3")
    center_text(d, (990, 1060), "冲突装备对：297 → 0", font(25, True), COLORS["冲突"])
    save(im, "图6_问题2消解前后时频占用.png")


def hist(draw, box, values, label, color, max_x):
    x0, y0, x1, y1 = box
    counts = Counter(values)
    n = max_x + 1
    slot = (x1-x0)/n
    maxc = max(counts.values()) if counts else 1
    for i in range(n):
        v = counts.get(i, 0)
        top = y1 - v/maxc*(y1-y0)
        draw.rectangle((x0 + i*slot + 2, top, x0 + (i+1)*slot - 2, y1), fill=color)
        center_text(draw, (x0 + (i+0.5)*slot, y1 + 25), i, font(17), COLORS["次文字"])
        if v:
            center_text(draw, (x0 + (i+0.5)*slot, top - 18), v, font(16, True), color)
    for tick in range(0, maxc+1, max(1, maxc//4)):
        py = y1 - tick/maxc*(y1-y0)
        draw.line((x0, py, x1, py), fill=COLORS["网格"], width=1)
        right_text(draw, (x0 - 12, py), tick, font(16), COLORS["次文字"])
    draw.line((x0, y0, x0, y1), fill="#AAB7C4", width=2)
    draw.line((x0, y1, x1, y1), fill="#AAB7C4", width=2)
    center_text(draw, ((x0+x1)/2, y1+60), label, font(20), COLORS["文字"])


def fig07_q2_modes(q2):
    freq_count = sum(q2["stats"][g]["frequency"] for g in "ABC")
    time_count = sum(q2["stats"][g]["time"] for g in "ABC")
    im, d = new_canvas("图7  问题2调整方式与幅度分布", f"频移{freq_count}项、时间平移{time_count}项；所有单项调整均满足 |频移|≤10、|时间平移|≤5")
    draw_vbars(d, (180, 290, 900, 850), ["频段平移", "时间平移"], [freq_count, time_count], [COLORS["频移"], COLORS["时移"]], max_value=110, value_suffix="项")
    df_abs = [abs(p["df"]) for p in q2["plans"] if not p.get("canceled") and p["df"]]
    dt_abs = [abs(p["dt"]) for p in q2["plans"] if not p.get("canceled") and p["dt"]]
    d.text((1080, 245), "频移幅度 |Δf|", font=font(25, True), fill=COLORS["频移"])
    hist(d, (1060, 320, 1810, 610), df_abs, "频移幅度（Δf）", COLORS["频移"], 10)
    d.text((1080, 690), "时间平移幅度 |Δt|", font=font(25, True), fill=COLORS["时移"])
    hist(d, (1060, 765, 1810, 1010), dt_abs, "时间平移幅度（Δt）", COLORS["时移"], 5)
    save(im, "图7_问题2调整方式与幅度.png")


def fig08_q3(source, q2, q3):
    im, d = new_canvas("图8  问题3新增C类装备布局", f"底图为问题2无冲突方案；醒目色为新增{q3['count']}台C类装备，资源窗口为频段[0,100)、时间[0,643)")
    box = (150, 250, 1880, 900)
    axes(d, box, 643, 100, x_ticks=[0, 200, 400, 600], y_ticks=[0, 20, 40, 60, 80, 100])
    active = [p for p in q2["plans"] if not p.get("canceled", False)]
    draw_plan_stack(d, box, active, alpha=42)
    for p in q3["plans"]:
        for s, e in periods(p):
            tf_rect(d, box, p, s, e, COLORS["新增"], alpha=108, outline="#B2182B")
    draw_legend(d, [("A类装备", COLORS["A"]), ("B类装备", COLORS["B"]), ("C类装备", COLORS["C"]), ("新增C类装备", COLORS["新增"])], 130, 190, 205)
    d.rounded_rectangle((1360, 176, 1830, 226), radius=8, fill="#FFF1F1", outline="#E9A1A1")
    d.text((1390, 190), f"新增数量：{q3['count']}台（最优）", font=font(22, True), fill=COLORS["新增"])
    save(im, "图8_问题3新增C类装备布局.png")


def fig09_q4_compare(q2, q4):
    q2_cancel = sum(q2["stats"][g]["canceled"] for g in "ABC")
    q4_cancel = sum(q4["stats"][g]["canceled"] for g in "ABC")
    im, d = new_canvas("图9  问题2与问题4方案对比", f"允许C类调整使用间隔后，撤销数量由{q2_cancel}项降至{q4_cancel}项，最终执行计划由{150-q2_cancel}项增至{150-q4_cancel}项")
    labels = ["原样保留", "调整", "撤销"]
    q2v = [sum(q2["stats"][g][k] for g in "ABC") for k in ["unchanged", "adjusted", "canceled"]]
    q4v = [sum(q4["stats"][g][k] for g in "ABC") for k in ["unchanged", "adjusted", "canceled"]]
    box = (220, 320, 1810, 930)
    maxv = 150; slot = (box[2]-box[0])/3; bw = 95
    for i, lab in enumerate(labels):
        cx = box[0] + slot*(i+0.5)
        for off, v, col in [(-58, q2v[i], COLORS["A"]), (58, q4v[i], COLORS["新增"])]:
            top = box[3] - v/maxv*(box[3]-box[1])
            d.rectangle((cx+off-bw/2, top, cx+off+bw/2, box[3]), fill=col)
            center_text(d, (cx+off, top-24), v, font(22, True), col)
        center_text(d, (cx, box[3]+34), lab, font(22, True), COLORS["文字"])
    for tick in range(0, 151, 30):
        py=box[3]-tick/maxv*(box[3]-box[1])
        d.line((box[0], py, box[2], py), fill=COLORS["网格"], width=1)
        right_text(d, (box[0]-15, py), tick, font(18), COLORS["次文字"])
    d.line((box[0], box[1], box[0], box[3]), fill="#AAB7C4", width=2)
    d.line((box[0], box[3], box[2], box[3]), fill="#AAB7C4", width=2)
    draw_legend(d, [("问题2", COLORS["A"]), ("问题4", COLORS["新增"])], 310, 215, 180)
    d.rounded_rectangle((1120, 190, 1800, 240), radius=8, fill="#FFF1F1", outline="#E9A1A1")
    d.text((1160, 204), f"撤销：{q2_cancel} → {q4_cancel}    执行：{150-q2_cancel} → {150-q4_cancel}", font=font(23, True), fill=COLORS["撤销"])
    save(im, "图9_问题2与问题4方案对比.png")


def fig10_q4_modes(q4):
    s = q4["stats"]
    values = [sum(s[g][k] for g in "ABC") for k in ["frequency", "time", "gap", "canceled"]]
    labels = ["频移", "时间平移", "间隔调整", "撤销"]
    cols = [COLORS["频移"], COLORS["时移"], COLORS["间隔调整"], COLORS["撤销"]]
    gap_count = sum(s[g]["gap"] for g in "ABC")
    im, d = new_canvas("图10  问题4方案调整方式构成", f"问题4允许C类改变使用间隔；间隔调整{gap_count}项，是减少撤销的重要操作来源")
    draw_vbars(d, (230, 320, 1770, 920), labels, values, cols, max_value=65, value_suffix="项")
    d.rounded_rectangle((1050, 200, 1770, 255), radius=8, fill="#F4EEFF", outline="#CBB2F2")
    d.text((1090, 217), f"间隔调整：{gap_count}项（C类）", font=font(24, True), fill=COLORS["间隔调整"])
    save(im, "图10_问题4调整方式构成.png")


def main():
    source = read_source()
    q1 = load_json(".cache/q1/data.json")
    q2 = load_json(".cache/q2/solution.json")
    q3 = load_json(".cache/q3/solution.json")
    q4 = load_json(".cache/q4/solution.json")
    fig01_raw(source)
    fig02_conflict_type(q1["stats"]["types"])
    fig03_network(q1)
    fig04_top(q1)
    fig05_q2_resolution(q2)
    fig06_q2_before_after(source, q1, q2)
    fig07_q2_modes(q2)
    fig08_q3(source, q2, q3)
    fig09_q4_compare(q2, q4)
    fig10_q4_modes(q4)
    manifest = """# D题可视化图表清单

| 图号 | 文件 |
|---|---|
| 图1 | 图1_原始时频资源占用.png |
| 图2 | 图2_冲突类型统计.png |
| 图3 | 图3_装备用频冲突网络.png |
| 图4 | 图4_装备冲突度排序.png |
| 图5 | 图5_问题2消解结果.png |
| 图6 | 图6_问题2消解前后时频占用.png |
| 图7 | 图7_问题2调整方式与幅度.png |
| 图8 | 图8_问题3新增C类装备布局.png |
| 图9 | 图9_问题2与问题4方案对比.png |
| 图10 | 图10_问题4调整方式构成.png |

图中文字、坐标轴、图例和注释均为中文；所有图按统一的A/B/C配色和时频窗口绘制。
"""
    (OUT / "图表清单.md").write_text(manifest, encoding="utf-8")
    print(f"generated {len(list(OUT.glob('图*.png')))} figures in {OUT}")


if __name__ == "__main__":
    main()
