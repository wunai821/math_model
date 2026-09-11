"""Paper-ready Figure 3 using the verified q1 conflict data."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import networkx as nx
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ANSWER = ROOT / "answer"
OUT = ANSWER / "figures"
PNG = OUT / "图3_装备用频冲突网络.png"
SVG = OUT / "图3_装备用频冲突网络.svg"
PDF = OUT / "图3_装备用频冲突网络.pdf"

FONT = "Microsoft YaHei"
COLORS = {"A": "#5B83AA", "B": "#E39A50", "C": "#6EA46A"}
EDGE = "#8EA5B8"
TEXT = "#26384A"
SUBTEXT = "#617487"
GRID = "#E6EBF0"
INSET_COLORS = {"BC": "#D6812E", "AC": "#7A9DBB", "AB": "#A9BED0", "CC": "#8FBC8A", "BB": "#E8B778", "AA": "#D8DFE6"}


def load_network():
    data = json.loads((ANSWER / ".cache/q1/data.json").read_text(encoding="utf-8"))
    edges = [tuple(pair) for pair in data["pairs"]]
    graph = nx.Graph()
    graph.add_edges_from(edges)
    degree = dict(graph.degree())
    categories = {node: node[0] for node in graph.nodes}
    expected_focus = {"B009", "B016", "B024", "B027", "B030", "C076"}
    if len(graph.nodes) != 148 or len(graph.edges) != 297:
        raise ValueError(f"冲突网络数据异常：{len(graph.nodes)}个节点、{len(graph.edges)}条边")
    if set(node for node, d in degree.items() if d == 8) != expected_focus:
        raise ValueError("最高冲突度节点与现有数据不一致")
    return data, graph, degree, categories


def type_counts(data):
    types = data["stats"]["types"]
    return {key: types.get(key, 0) for key in ["BC", "AC", "AB", "CC", "BB", "AA"]}


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def place_labels(ax, fig, pos, degree, focus):
    """Place focus callouts while avoiding nodes, bounds, and other labels."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axis_box = ax.get_window_extent(renderer=renderer)
    node_display = {node: ax.transData.transform(pos[node]) for node in focus}
    all_node_display = np.array([ax.transData.transform(pos[node]) for node in pos])
    label_w, label_h = 174, 38
    base_candidates = [(92, 48), (92, -48), (-92, 48), (-92, -48),
                       (0, 78), (0, -78), (135, 0), (-135, 0)]
    placed = []
    center = np.array([axis_box.x0 + axis_box.width / 2, axis_box.y0 + axis_box.height / 2])
    for node in sorted(focus, key=lambda n: -np.linalg.norm(node_display[n] - center)):
        nxp, nyp = node_display[node]
        outward = node_display[node] - center
        candidates = sorted(
            base_candidates,
            key=lambda p: -np.dot(np.asarray(p, dtype=float), outward),
        )
        best = None
        for dx, dy in candidates:
            cx, cy = nxp + dx, nyp + dy
            box = (cx - label_w / 2, cy - label_h / 2, cx + label_w / 2, cy + label_h / 2)
            outside = max(0, axis_box.x0 + 8 - box[0]) + max(0, box[2] - axis_box.x1 + 8) + max(0, axis_box.y0 + 8 - box[1]) + max(0, box[3] - axis_box.y1 + 8)
            overlap_cost = sum(1 for other in placed if overlap(box, other))
            padded = (box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6)
            covered_nodes = np.count_nonzero(
                (all_node_display[:, 0] >= padded[0]) & (all_node_display[:, 0] <= padded[2])
                & (all_node_display[:, 1] >= padded[1]) & (all_node_display[:, 1] <= padded[3])
            )
            score = outside * 10000 + overlap_cost * 1_000_000 + covered_nodes * 100_000 + dx * dx + dy * dy
            if best is None or score < best[0]:
                best = (score, cx, cy, box)
        _, cx, cy, box = best
        placed.append(box)
        point_offset = (cx - nxp) * 72 / fig.dpi, (cy - nyp) * 72 / fig.dpi
        ax.annotate(
            f"{node} (d={degree[node]})",
            xy=pos[node], xycoords="data", xytext=point_offset, textcoords="offset points",
            ha="center", va="center", fontsize=8.5, fontweight="bold", color=TEXT,
            bbox=dict(boxstyle="round,pad=0.32", fc="white", ec=TEXT, lw=0.75, alpha=0.97),
            arrowprops=dict(arrowstyle="-", color="#506477", lw=0.75, alpha=0.70, shrinkA=5, shrinkB=4),
            zorder=8,
        )


def render():
    data, graph, degree, categories = load_network()
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "Microsoft YaHei UI", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })

    fig = plt.figure(figsize=(16, 9), dpi=200, facecolor="white")
    fig.text(0.045, 0.955, "图3  装备用频冲突网络", fontsize=18, fontweight="bold", color=TEXT, ha="left", va="top")
    fig.text(0.046, 0.908, "节点表示冲突装备，连线表示装备间存在用频冲突；节点越大，关联的冲突装备越多", fontsize=9.5, color=SUBTEXT, ha="left", va="top")
    fig.lines.append(plt.Line2D([0.045, 0.955], [0.878, 0.878], transform=fig.transFigure, color="#CBD5DF", lw=0.8))

    # The topology gets most of the canvas; the narrower right rail carries
    # exact statistics without competing with the network itself.
    ax = fig.add_axes([0.045, 0.135, 0.675, 0.705])
    ax.set_facecolor("white")
    raw_pos = nx.spring_layout(graph, seed=42, k=0.54, iterations=500, scale=1.0)
    nodes_ordered = list(graph.nodes)
    points = np.array([raw_pos[node] for node in nodes_ordered])
    points -= points.mean(axis=0)
    # Rotate the long axis horizontally so the topology uses the landscape panel.
    _, _, vh = np.linalg.svd(points, full_matrices=False)
    points = points @ vh.T
    # Centre by the bounding box rather than the arithmetic mean; long sparse
    # branches otherwise make the visible network appear to sink in the panel.
    points -= (points.min(axis=0) + points.max(axis=0)) / 2
    half_range = (points.max(axis=0) - points.min(axis=0)) / 2
    points /= np.maximum(half_range, 1e-9)
    pos = {node: (points[i, 0], points[i, 1] * 0.86) for i, node in enumerate(nodes_ordered)}
    ax.set_xlim(-1.18, 1.18)
    ax.set_ylim(-0.93, 0.93)
    ax.axis("off")

    nx.draw_networkx_edges(graph, pos, ax=ax, edge_color=EDGE, width=0.68, alpha=0.25)
    for group in "ABC":
        nodes = [node for node in graph.nodes if categories[node] == group]
        # Diameter follows size0 + k*sqrt(degree); marker area is the square of it.
        diameter = np.array([4.2 + 2.25 * math.sqrt(degree[node]) for node in nodes])
        nx.draw_networkx_nodes(
            graph, pos, nodelist=nodes, node_color=COLORS[group], node_size=diameter**2,
            linewidths=0.45, edgecolors="white", alpha=0.96, ax=ax,
        )

    focus = ["B009", "B016", "B024", "B027", "B030", "C076"]
    # Ordinary nodes remain readable but smaller; degree-8 focus nodes are
    # deliberately enlarged by about 15% relative to the previous version.
    focus_diameter = np.array([15.8 for node in focus])
    nx.draw_networkx_nodes(
        graph, pos, nodelist=focus, node_color=[COLORS[categories[node]] for node in focus],
        node_size=focus_diameter**2, linewidths=1.0, edgecolors=TEXT, alpha=1.0, ax=ax,
    )
    place_labels(ax, fig, pos, degree, focus)

    legend_handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS[g], markeredgecolor="white", markeredgewidth=0.5, markersize=7, label=f"{g}类") for g in "ABC"]
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(0.00, 1.02), ncol=3, frameon=False, fontsize=9.0, handletextpad=0.35, columnspacing=1.2)
    ax.text(1.0, 1.01, "圆圈描边：最高冲突度节点（d=8）", transform=ax.transAxes, ha="right", va="bottom", fontsize=8.1, color=SUBTEXT)

    # Summary card.
    card = FancyBboxPatch((0.755, 0.585), 0.20, 0.245, transform=fig.transFigure,
                          boxstyle="round,pad=0.008,rounding_size=0.008",
                          facecolor="#F7F9FB", edgecolor="#D7E0E8", linewidth=0.8)
    fig.patches.append(card)
    fig.text(0.772, 0.797, "网络摘要", fontsize=10.5, fontweight="bold", color=TEXT)
    summary = [("148", "冲突装备"), ("297", "冲突关系"), ("4.01", "平均冲突度")]
    for i, (value, label) in enumerate(summary):
        x = 0.773 + i * 0.059
        fig.text(x, 0.737, value, fontsize=17, fontweight="bold", color=TEXT, ha="left")
        fig.text(x, 0.707, label, fontsize=7.5, color=SUBTEXT, ha="left")
    fig.lines.append(plt.Line2D([0.772, 0.937], [0.682, 0.682], transform=fig.transFigure, color="#DCE4EB", lw=0.7))
    fig.text(0.772, 0.648, "最高冲突度  8", fontsize=9.0, fontweight="bold", color=TEXT)
    fig.text(0.772, 0.615, "B009 · B016 · B024 · B027 · B030 · C076", fontsize=7.2, color=SUBTEXT)

    # Exact type counts in a separate aligned panel.
    inset = fig.add_axes([0.765, 0.205, 0.18, 0.285])
    inset.set_facecolor("white")
    counts = type_counts(data)
    order = ["AA", "BB", "CC", "AB", "AC", "BC"]
    values = [counts[k] for k in order]
    bars = inset.barh(order, values, color=[INSET_COLORS[k] for k in order], height=0.58, edgecolor="none")
    inset.set_xlim(0, 205)
    inset.set_xticks([0, 50, 100, 150, 200])
    inset.set_xticklabels(["0", "50", "100", "150", "200"], fontsize=6.5, color=SUBTEXT)
    inset.tick_params(axis="y", labelsize=7.5, colors=TEXT, length=0)
    inset.grid(axis="x", color=GRID, lw=0.55)
    inset.set_axisbelow(True)
    inset.set_title("冲突类型统计（对）", fontsize=10.0, loc="left", pad=16, color=TEXT, fontweight="bold")
    inset.text(0.0, 1.035, "B-C 占 60.94%，是最主要的冲突类型", transform=inset.transAxes, fontsize=7.4, color=INSET_COLORS["BC"], fontweight="bold", ha="left", va="bottom")
    for bar, value, key in zip(bars, values, order):
        inset.text(value + 3, bar.get_y() + bar.get_height() / 2, str(value), va="center", ha="left", fontsize=7.5, color=INSET_COLORS[key] if value else SUBTEXT, fontweight="bold")
    for spine in inset.spines.values():
        spine.set_color("#CBD5DF")
        spine.set_linewidth(0.65)
    inset.spines["top"].set_visible(False)
    inset.spines["right"].set_visible(False)

    note = "注：C007、C060 未发生冲突，故未显示；节点位置由力导向布局确定，仅反映网络拓扑关系，不代表实际时频坐标。"
    fig.lines.append(plt.Line2D([0.045, 0.955], [0.102, 0.102], transform=fig.transFigure, color="#CBD5DF", lw=0.8))
    fig.text(0.045, 0.055, note, fontsize=8.0, color=SUBTEXT, ha="left", va="bottom")

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG, dpi=200, facecolor="white")
    fig.savefig(SVG, format="svg", facecolor="white")
    fig.savefig(PDF, format="pdf", facecolor="white")
    plt.close(fig)
    print(f"generated {PNG}")
    print(f"generated {SVG}")
    print(f"generated {PDF}")


if __name__ == "__main__":
    render()
