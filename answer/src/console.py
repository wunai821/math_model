"""Small, human-readable Chinese console reporting helpers.

The JSON cache files remain the machine-readable source of truth.  These
helpers only format terminal output so long solver runs are easy to follow.
"""

import sys
import threading
import time
from contextlib import contextmanager


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


OBJECTIVE_LABELS = {
    "cancel_total": "撤销总数",
    "cancel_A": "A类撤销数",
    "cancel_B": "B类撤销数",
    "adjust_total": "调整总数",
    "adjust_A": "A类调整数",
    "adjust_B": "B类调整数",
    "shift_cost": "调整幅度成本",
}

STATUS_LABELS = {
    "OPTIMAL": "已证明最优",
    "FEASIBLE": "已找到可行解（限时）",
    "UNKNOWN": "未确定",
    "INFEASIBLE": "无解",
    "MODEL_INVALID": "模型无效",
}


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}"
    return str(value)


def header(title):
    print(f"\n【{title}】", flush=True)


def summary(label, **items):
    text = "，".join(f"{name}={_fmt(value)}" for name, value in items.items())
    print(f"  {label}：{text}", flush=True)


@contextmanager
def heartbeat(label, interval=15):
    """Print a quiet progress heartbeat while a solver is running."""
    started = time.monotonic()
    stop = threading.Event()

    def run():
        while not stop.wait(interval):
            elapsed = time.monotonic() - started
            print(f"  进行中｜{label}｜已运行 {_fmt(elapsed)} 秒", flush=True)

    print(f"  开始｜{label}", flush=True)
    worker = threading.Thread(target=run, name="solver-heartbeat", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=1)


def stage(record, index=None):
    name = OBJECTIVE_LABELS.get(record.get("objective"), record.get("objective", "当前阶段"))
    status = STATUS_LABELS.get(record.get("status"), record.get("status", "未知状态"))
    prefix = f"  阶段{index}｜" if index is not None else "  "
    parts = [f"{prefix}{name}", f"状态：{status}"]
    if "value" in record:
        parts.append(f"当前值：{_fmt(record['value'])}")
    bound = None
    bound_name = None
    if "lower_bound" in record:
        bound, bound_name = record["lower_bound"], "下界"
    elif "upper_bound" in record:
        bound, bound_name = record["upper_bound"], "上界"
    if bound_name is not None:
        parts.append(f"{bound_name}：{_fmt(bound)}")
        if "value" in record and bound is not None:
            parts.append(f"界差距：{_fmt(abs(record['value'] - bound))}")
    if "seconds" in record:
        parts.append(f"用时：{_fmt(record['seconds'])}秒")
    if record.get("note"):
        parts.append(str(record["note"]))
    print("；".join(parts), flush=True)


def verification(report, label="独立验证"):
    if report.get("ok"):
        extras = []
        for key, name in (("fixed", "固定计划"), ("added", "新增计划"),
                          ("pair_checks", "检查计划对"), ("conflicts", "冲突对")):
            if key in report:
                extras.append(f"{name}：{report[key]}")
        print(f"【{label}】通过" + ("；" + "；".join(extras) if extras else ""), flush=True)
    else:
        errors = report.get("errors", [])
        print(f"【{label}】失败；错误数：{len(errors)}", flush=True)
        for error in errors[:5]:
            print(f"  - {error}", flush=True)
        if len(errors) > 5:
            print(f"  - 其余 {len(errors) - 5} 条错误已写入验证报告", flush=True)


def finished(label, output=None, objective=None):
    items = {}
    if objective is not None:
        items["最终目标"] = objective
    if output is not None:
        items["输出文件"] = output
    summary(f"{label}完成", **items)
