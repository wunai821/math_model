"""Generate Q3/Q4 methods and results only from freshly verified artifacts."""
import json
from pathlib import Path

from scheduling import ANSWER
from verify_schedule import verify


def report(question):
    if verify(question):
        raise RuntimeError('Verification failed; report not generated')
    data = json.loads((ANSWER / f'.cache/q{question}/solution.json').read_text(encoding='utf-8'))
    text = q3_report(data) if question == 3 else q4_report(data)
    output = ANSWER / f'docs/问题{question}建模与结果.md'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding='utf-8')
    print(output)


def q3_report(data):
    optimality = (f"CP-SAT 返回 OPTIMAL，目标值与上界均为 {data['count']}，因此在本文明确的资源窗口、C 类需求和固定 q2 方案下，新增数量的最大值已得到证明。"
                  if data['status'] == 'OPTIMAL' else
                  f"当前方案可行，新增数量为 {data['count']}，求解器上界为 {data['upper_bound']}，尚未证明达到最大值。")
    return f'''# 问题3：固定问题2方案后的新增容量

## 结果

新增 **{data['count']} 台 C 类装备**。{optimality}

提交文件为 [result3.xlsx](../results/result3.xlsx)，每行代表一台新增装备；时间列填写首次使用区间，之后仍按间隔8、使用12次的规则展开。

## 资源窗口与建模假设

原题未单独给出时间资源窗口的右端点。本文将“不增加时频资源”解释为继续使用附件1覆盖的原始窗口：频域 [0,100)，时域 [0,{data['horizon']})。右端点由原计划最后一次使用结束时刻的最大值计算，不通过推迟新增装备扩大窗口。当前 q2 的所有有效计划也均落在该窗口内。

问题2的有效计划全部固定，包括原样保留与调整后的计划；已撤销计划不占用资源。问题3不重新优化 q2，也不限制新增数量为原有或被撤销的 C 类数量。新增装备没有待调整的原始坐标，因此分别选择其频段和首次时间位置；原题对已有计划的“只改一个参数”不被解释为要求新增装备引用一项不存在的原始计划。

附件1中90台 C 类装备均具有相同需求：频宽3、单次时长2、空闲间隔8、使用次数12。新增装备沿用这一完整需求，不能缩窄频宽、缩短时长或减少次数。若采用其他时间窗口或允许重排 q2，须重新求解，本文最优值不直接适用。

## 完整候选枚举

设新增计划的频域起点为 f，首次时间起点为 s，则

- f∈{{0,…,97}}；
- s∈{{0,…,{data['horizon'] - 112}}}；
- 频段为 [f,f+3)；
- 第 k 次时间区间为 [s+10k,s+10k+2)，k=0,…,11。

最后一次结束时刻为 s+112。完整枚举上述整数起点，删除与任一 q2 有效计划冲突的候选，剩余 **{data['candidates']}** 个。端点相接不算交叠。

每个候选 c 对应一个二元变量 x_c。每个离散时频单元 r 的候选集合记为 C(r)，模型为

最大化 Σ_c x_c，约束 Σ_{{c∈C(r)}} x_c≤1，x_c∈{{0,1}}。

由于所有端点均为整数，单位网格资源排斥与区间无冲突完全等价。每台新增装备使用正面积资源，相同位置不能安排两台，因此每个位置一个二元变量足以表示任意数量的新增装备；候选枚举完整，所得最优值不是贪心填空数量。

去重后有 {data['resource_constraints']} 条资源排斥约束。原方案占用 {data['occupied_cells']} 个时频单元，每台新增装备占用72个，面积上界为 {data['area_upper_bound']} 台；面积上界忽略连续性和周期结构，较松。最终最优性以求解器的精确模型上界为准。

## 求解记录与验证

| 项目 | 数值 |
|---|---:|
| 新增数量 | {data['count']} |
| 求解器上界 | {data['upper_bound']} |
| 求解状态 | {data['status']} |
| 求解时间（秒，不含建模） | {data['seconds']} |
| 工作线程数 | {data['workers']} |

独立验证重新读取附件1及 q2 完整计划，核对 q2 操作和 result2.xlsx；随后检查新增装备的全部12次使用都在原资源窗口内，逐对枚举原有与新增、以及新增之间的时间和频率交叠，冲突数为 **0**。同时核对 result3.xlsx 表头、序号、列位置和全部行。

q2 基准文件 SHA-256：`{data['q2_sha256']}`。验证器会拒绝与该基准不一致的结果，防止 q2 更新后继续使用旧 q3 方案。

来源：根目录 `D题.pdf` 问题3及附录、`附件/附件1.xlsx`、`附件/附件2/result3.xlsx`，以及当前 `answer/.cache/q2/solution.json`。所有数值以 Δf、Δt 为单位。

## 文档与源码对应关系

| 内容 | 源码或结果 |
|---|---|
| 新增容量求解程序 | [`src/q3/solve.py`](../src/q3/solve.py) |
| 独立验证程序 | [`src/q3/verify.py`](../src/q3/verify.py) |
| Markdown 报告生成 | [`src/q3/report.py`](../src/q3/report.py) 与 [`src/report_schedule.py`](../src/report_schedule.py) |
| Excel 导出程序 | [`src/export_xlsx.py`](../src/export_xlsx.py) |
| q3 求解结果 | `.cache/q3/solution.json` |
| q3 验证结果 | `.cache/q3/verification.json` |
| 提交表 | [`result3.xlsx`](../results/result3.xlsx) |
'''


def q4_report(data):
    stats = data['stats']
    total = {key: sum(s[key] for s in stats.values()) for key in stats['A']}
    table = '\n'.join(f"| {g}类 | {stats[g]['unchanged']} | {stats[g]['adjusted']} | {stats[g]['canceled']} |" for g in 'ABC')
    names = dict(cancel_total='撤销总数', cancel_A='A类撤销数', cancel_B='B类撤销数',
                 adjust_total='调整总数', adjust_A='A类调整数', adjust_B='B类调整数', shift_cost='归一化调整成本')
    stages = '\n'.join(f"| {names[s['objective']]} | {s.get('value', '—')} | {s['lower_bound']} | {s['status']} | {s['seconds'] if s.get('seconds') is not None else '—'} |" for s in data['stages'])
    primary = data['stages'][0]
    best_bound = max(primary['lower_bound'], data.get('comparison', {}).get('cancel_lower_bound', 0))
    if primary['status'] == 'OPTIMAL' or best_bound == primary['value']:
        primary_text = f"最少撤销数量已证明为 {primary['value']}。"
    else:
        primary_text = f"撤销数量当前为 {primary['value']}，历次等价模型求解所得最强下界为 {best_bound}，尚未证明最优。"
    all_optimal = len(data['stages']) == 7 and all(s['status'] == 'OPTIMAL' for s in data['stages'])
    status_text = '全部7个阶段均证明最优。' if all_optimal else '部分后续目标尚未完成优化或未证明最优，不能将整个方案称为字典序全局最优。'
    gap_ids = '、'.join(p['id'] for p in data['plans'] if p['dg']) or '无'
    canceled = '、'.join(p['id'] for p in data['plans'] if p['canceled']) or '无'
    shift_sums = {key: sum(abs(p[key]) for p in data['plans']) for key in ('df', 'dt', 'dg')}
    last_ends = [(p['id'], p['end'] + (p['count'] - 1) *
                  (p['end'] - p['start'] + p['gap']))
                 for p in data['plans'] if not p['canceled']]
    overflow_table = '\n'.join(f'| {ident} | {end} | {"是" if end > 650 else "否"} |'
                               for ident, end in last_ends if end > 643) or '| 无 | — | — |'
    meta = data['metadata']
    previous = next((c['objectives'] for c in data.get('comparison', {}).get('candidates', [])
                     if c['file'] == 'before_refinement.json'), None)
    comparison_text = ''
    if previous is not None:
        comparison_text = f'''## 续算前后对比

以下“续算前”指本轮优化前保存的q4方案，不是q2方案。目标顺序保持不变。

| 指标 | 续算前 | 当前方案 |
|---|---:|---:|
| 撤销总数 | {previous[0]} | {total['canceled']} |
| A类撤销数 | {previous[1]} | {stats['A']['canceled']} |
| B类撤销数 | {previous[2]} | {stats['B']['canceled']} |
| 调整总数 | {previous[3]} | {total['adjusted']} |
| A类调整数 | {previous[4]} | {stats['A']['adjusted']} |
| B类调整数 | {previous[5]} | {stats['B']['adjusted']} |
| 归一化调整成本 | {previous[6]} | {data['shift_cost']} |

'''
    stage_note = ('本表为局部搜索最终方案的7项目标统计，未分7个全局阶段独立求解，故各项目时间留空、下界仅记通用非负下界0。全局撤销下界来自此前未限制邻域的等价模型。'
                  if meta.get('local_search') else
                  '表中记录最终入选方案自身的阶段日志。若某阶段返回UNKNOWN，则保留此前可行方案；表中未列出的后续阶段没有执行。比较模型的首阶段下界也可用于约束全局撤销最优值，已在结果概述中合并说明。')
    if meta.get('frozen_prefix'):
        stage_note += f" 前{meta['frozen_prefix']}项目标值从已验证的输入方案固定，记录沿用输入方案，未在本轮重新证明；之后的求解器下界与最优性均以这些固定值为条件。"
    if meta.get('method') == 'local_search':
        model_summary = '最终方案经过局部邻域优化：固定邻域外的有效计划，枚举邻域内全部合法操作，只接受7层目标向量严格改善的方案。局部搜索的目标界不作为全局最优性证据。'
    elif 'pair_constraints' in meta:
        model_summary = f"最终方案由紧凑模型取得，包含 {meta['pair_constraints']} 组装备对约束和 {meta['time_safe_tables']} 张安全时间模式表。"
    else:
        model_summary = f"最终方案由网格模型取得，包含 {meta['candidates']} 个候选和 {meta['resource_constraints']} 条去重资源约束。"
    return f'''# 问题4：允许C类调整使用间隔的冲突消解

## 结果

150项原始计划中，原样保留 {total['unchanged']} 项、调整 {total['adjusted']} 项、撤销 {total['canceled']} 项，最终执行 {150 - total['canceled']} 项。独立验证冲突装备对数为 **0**。{primary_text}{status_text}

## 允许操作

下列坐标均用资源格数表示：频率坐标的物理单位为Δf，时间坐标的物理单位为Δt；整数平移量不能与未归一化的物理频率或时间混用。

| 符号 | 含义 | 取值或单位 |
|---|---|---|
| i，k | 装备索引、使用次数索引 | k=0,…,n_i−1 |
| [a_i,b_i) | 原频段区间 | 频率格坐标 |
| [s_i,e_i) | 原首次时间区间 | 时间格坐标 |
| d_i=e_i−s_i | 单次使用时长 | 正整数时间格数 |
| g_i，n_i | 原空闲间隔、使用次数 | 非负整数时间格数、正整数次数 |
| u_i，v_i，h_i | 频移、首次时间平移、间隔变化 | 整数格数 |
| z_i | 是否撤销 | 0或1 |
| x_c | 是否选择候选c | 0或1 |

本问从附件1原始计划重新求解。每台装备枚举原样保留、频移 u∈[-10,10]、时间平移 v∈[-5,5]、撤销。C 类额外允许间隔变化 h∈[-10,10]，且原间隔 g+h≥0。所有变量均为整数，零间隔表示前次结束后立即开始下一次，合法且不自相交。

频宽、单次时长和使用次数均不变；A、B类间隔不变。一个有效候选中 u、v、h 至多一个非零；撤销候选三者全为零。间隔调整是独立选项，不能同时叠加频移或首次时间平移。

为简化单台装备公式，以下暂省略下标i。对原参数 [a,b)、[s,e)、间隔g和次数n，令d=e−s，第k次区间为

[s+v+k(d+g+h), e+v+k(d+g+h))，k=0,…,n−1；频段为 [a+u,b+u)。

要求0≤a+u<b+u≤100，s+v≥0，g+h≥0。与问题2一致，本问使用题目明确给出的非负时间和调整幅度限制，不额外添加未明确规定的结束时刻上限。问题3的“不增加时频资源”窗口约束只用于问题3。

### 规划窗口适用条件与审计

原题未规定650这一时间上限。问题3当前另作有限窗口[0,643)的假设，643取自原始计划最后结束时刻的最大值；它不是四问统一采用的时间边界。当前问题4方案的验证结论仅针对上述无统一结束上限的模型。

各有效计划的最后结束时刻为 e+v+(n−1)(d+g+h)，应检查全部重复使用，不能只检查首次区间。如果论文选择统一窗口[0,H)，则必须补充 e+v+(n−1)(d+g+h)≤H；恰好在H结束合法。当前方案超过643的装备如下：

| 装备 | 最后结束时刻 | 是否超过650 |
|---|---:|---|
{overflow_table}

因此，当前方案不能作为统一[0,643)或[0,650)窗口模型的提交结果。采用任一统一窗口时，应先同步求解器与独立验证器的结束上限，再重新求解问题4；若问题3窗口从643改为650，其新增数量也必须重算。

## 有限候选优化模型

每台装备i的合法候选集合记为K_i，对每个候选c设置二元变量x_c。撤销候选不占资源。约束为：

1. 每台恰选一种操作：Σ_{{c∈K_i}} x_c=1；
2. 每个单位时频单元最多由一个候选占用：Σ_{{c占用r}} x_c≤1。

枚举所有候选的全部重复时间区间，约束覆盖原始冲突及调整后可能出现的新冲突。左闭右开区间的端点相接合法。输入和操作均离散，故网格约束精确等价于无交叠条件。

网格模型使用问题2方案作为可行初始提示，但不固定其任何决策或目标值。

另实现等价的紧凑模型：每台设频移变量和离散时间模式变量，模式枚举合法的首次时间平移或间隔变化，并通过允许组合表保证单参数限制。把每个模式的完整时间占用表示为整数位集，对每对装备预先计算不交叠的模式组合。两台不冲突等价于：至少一台撤销，或频段分离，或时间模式组合安全。该模型与网格模型允许的操作完全相同，可使用现有q4方案作为初始提示。

{model_summary} 各次求解的候选方案按相同7层目标比较，选取字典序更好的方案进行独立验证与导出。

## 多目标顺序

沿用问题2的明确建模选择：最小撤销总数 → A类撤销数 → B类撤销数 → 调整总数 → A类调整数 → B类调整数 → 调整幅度。题目定性要求没有规定唯一权重或严格先后，本顺序是为了与问题2保持可比。

最后一层成本取 Σ(|u|+2|v|+|h|)，为归一化幅度 Σ(|u|/10+|v|/5+|h|/10) 的10倍。间隔变化按参数变化量计费；它造成的后续累计时间移动为kh，已完整纳入冲突约束，但不重复计入参数调整幅度。

当前幅度分解为Σ|u|={shift_sums['df']}、Σ|v|={shift_sums['dt']}、Σ|h|={shift_sums['dg']}。未加权参数格数之和为{sum(shift_sums.values())}；无量纲归一化幅度D={data['shift_cost']/10:g}，求解器为使用整数目标而记录10D={data['shift_cost']}。时间项的系数2来自允许幅度5与10的比例，与时间区间的端点数量无关。求解状态表中的“归一化调整成本”均指10D。

每阶段锁定当前取得的目标值，再优化下一阶段。限时阶段仅返回可行解时，明确记录下界；后续阶段的最优性与下界都以此前锁定值为条件。

## 消解统计（题目表1）

“保留数量”指原样保留，与调整和撤销互斥；有效执行总数为保留加调整。

| 类别 | 保留数量 | 调整数量 | 撤销数量 |
|---|---:|---:|---:|
{table}
| 合计 | {total['unchanged']} | {total['adjusted']} | {total['canceled']} |

调整方式：频移 {total['frequency']} 项、首次时间平移 {total['time']} 项、间隔调整 {total['gap']} 项。

间隔调整装备：{gap_ids}。

撤销装备：{canceled}。

{comparison_text}
## 求解状态

| 目标 | 当前值 | 下界 | 状态 | 时间（秒） |
|---|---:|---:|---|---:|
{stages}

{stage_note}

本次随机种子为{data['metadata'].get('seed', 42)}，使用 {data['metadata']['workers']} 个工作线程。多线程限时优化重复运行可能得到不同方案，应以对应结果、界和验证记录为准。

## 验证与交付

验证程序不调用求解器的候选或资源网格函数。它重新读取附件1，检查编号完整性、整数操作、单参数限制、类别限制、调整幅度、非负间隔、边界、频宽/单次时长/次数不变，并对所有有效计划逐对枚举全部重复区间。另核查分组统计、阶段目标值以及提交表每个字段。

提交文件：[result4.xlsx](../results/result4.xlsx)。只写调整或撤销的装备：B列频段、C列首次时间、D列新间隔、E列撤销“是”，每行仅填写其中一项，其他列留空。

来源：根目录 `D题.pdf` 问题4及附录、`附件/附件1.xlsx`、`附件/附件2/result4.xlsx`。所有数值以 Δf、Δt 为单位。

## 文档与源码对应关系

| 内容 | 源码或结果 |
|---|---|
| 网格模型主程序 | [`src/q4/solve.py`](../src/q4/solve.py) |
| 紧凑模型 | [`src/q4/solve_compact.py`](../src/q4/solve_compact.py) 与 [`src/q4/model.py`](../src/q4/model.py) |
| 候选方案比较 | [`src/q4/select.py`](../src/q4/select.py) |
| 独立验证程序 | [`src/q4/verify.py`](../src/q4/verify.py) |
| 复测入口 | [`src/q4/reproduce.py`](../src/q4/reproduce.py) |
| Markdown 报告生成 | [`src/q4/report.py`](../src/q4/report.py) 与 [`src/report_schedule.py`](../src/report_schedule.py) |
| Excel 导出程序 | [`src/export_xlsx.py`](../src/export_xlsx.py) |
| q4 求解结果 | `.cache/q4/solution.json` |
| q4 验证结果 | `.cache/q4/verification.json` |
| 提交表 | [`result4.xlsx`](../results/result4.xlsx) |
'''
