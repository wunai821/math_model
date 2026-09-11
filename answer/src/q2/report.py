"""Generate the Question 2 Markdown report from the selected, verified solution."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
data = json.loads((ROOT/'answer/.cache/q2/solution.json').read_text(encoding='utf-8'))
verification = json.loads((ROOT/'answer/.cache/q2/verification.json').read_text(encoding='utf-8'))
assert verification['ok'], 'Verify solution before generating report'
stats = data['stats']
total = {key: sum(s[key] for s in stats.values()) for key in ('unchanged','adjusted','canceled','frequency','time')}
names = dict(cancel_total='撤销总数',cancel_A='A类撤销数',cancel_B='B类撤销数',adjust_total='调整总数',adjust_A='A类调整数',adjust_B='B类调整数',shift_cost='平移成本')
table = '\n'.join(f"| {c}类 | {stats[c]['unchanged']} | {stats[c]['adjusted']} | {stats[c]['canceled']} |" for c in 'ABC')
stages = '\n'.join(f"| {names.get(s['objective'],s['objective'])} | {s.get('value','—')} | {s.get('lower_bound','—')} | {s['status']} |" for s in data['stages'])
revoked = '、'.join(p['id'] for p in data['plans'] if p['canceled']) or '无'
proven = all(s['status']=='OPTIMAL' for s in data['stages']) and len(data['stages'])==7
optimality = '所有分层目标均已由求解器证明最优，因此该方案是下述目标顺序下的字典序最优解。' if proven else '该方案已验证可行，但部分目标在时间限制内未证明最优，不能称为全局最优方案。后续目标是在已锁定的前序目标值下求解，其下界和最优性均具有这一条件。'
primary = data['stages'][0]
if primary['status'] == 'OPTIMAL':
    optimality = f"撤销总数的最优值已证明为{primary['value']}，即在题目约束下无法保留超过{150-primary['value']}项计划。" + optimality
text = rf'''# 问题2：时频冲突消解

## 结果概述

针对附件1的150项用频计划，本方案原样保留{total['unchanged']}项、调整{total['adjusted']}项、撤销{total['canceled']}项，最终执行{150-total['canceled']}项计划。调整中，频段平移{total['frequency']}项，时间平移{total['time']}项。独立两两检测得到最终冲突装备对数为 **0**。

{optimality}

## 变量与允许操作

以 Δf 和 Δt 为单位。装备 i 的原频段为 [a_i,b_i)，首次时间为 [s_i,e_i)，单次时长 d_i=e_i−s_i，间隔 g_i，次数 n_i。令整数频移为 u_i、整数时间平移为 v_i、撤销指示为 z_i∈{{0,1}}。

约束如下：

- −10≤u_i≤10，−5≤v_i≤5；
- 0≤a_i+u_i<b_i+u_i≤100，s_i+v_i≥0；
- u_i与v_i至多一个非零；撤销时二者均为零；
- 频段宽度、单次时长、使用间隔、使用次数均不变。

保留计划第 k 次的使用时间为

T_ik = [s_i+v_i+k(d_i+g_i), s_i+v_i+k(d_i+g_i)+d_i)，k=0,…,n_i−1。

时间约束使用题目给出的平移幅度和非负起点，不额外假定一个未给定的统一结束时刻。

## 无冲突约束

任意两台未撤销装备 i、j 必须满足下列至少一项：

1. b_i+u_i≤a_j+u_j，即i的频段完全位于j左侧；
2. b_j+u_j≤a_i+u_i，即j的频段完全位于i左侧；
3. 两台装备的所有使用时间区间均不相交。

全部区间采用左闭右开形式，因此端点相接合法。约束覆盖所有装备对，包括调整后可能新产生冲突的装备对。

为减少约束规模，对每个装备对预先枚举相对时间平移 δ=v_i−v_j∈{{−10,…,10}}。令 S_ij 为不会使任何一组重复时段相交的δ集合，则第三项可精确表示为 v_i−v_j∈S_ij。这样可将多次使用的检查压缩成频段分离或相对时间差安全的逻辑约束。

另保留一个有限候选模型作为参考：每台装备枚举原位、20种频移、10种时间平移和撤销，去除越界项；每台恰选一个候选，每个离散时频单元最多被一个选中候选占用。两种模型遵守相同的允许操作与冲突定义。

## 多目标处理

题目没有给出数值权重，本方案使用下列字典序目标：

1. 最小化撤销总数；
2. 固定前项，最小化A类撤销数；
3. 固定前项，最小化B类撤销数；
4. 固定前项，最小化调整总数；
5. 固定前项，最小化A类调整数；
6. 固定前项，最小化B类调整数；
7. 固定前项，最小化平移成本 Σ(|u_i|+2|v_i|)。

最后一项等于归一化幅度之和 Σ(|u_i|/10+|v_i|/5) 的10倍，避免直接相加不同量纲的物理频率与时间。撤销与调整分别计数，不将撤销当作调整。

每阶段锁定已得到的前序目标值后继续求解。若某阶段超时但得到可行解，使用该阶段当前值继续，并保留上下界，不将其解释为已证明的字典序最优。

## 消解统计（题目表1）

本表“保留数量”指原样保留，与“调整数量”“撤销数量”互斥；最终执行数量等于保留数量加调整数量。

| 类别 | 保留数量 | 调整数量 | 撤销数量 |
|---|---:|---:|---:|
{table}
| 合计 | {total['unchanged']} | {total['adjusted']} | {total['canceled']} |

撤销装备：{revoked}。

## 求解状态与界

| 目标 | 当前值 | 求解器下界 | 状态 |
|---|---:|---:|---|
{stages}

OPTIMAL表示相应阶段已证明最优，FEASIBLE表示仅取得可行解。非首阶段的界均以此前目标取当前锁定值为条件。

## 独立验证与交付

验证程序独立读取附件1并逐台检查单参数操作、整数平移、幅度限制、频域边界、非负时间、频宽和时长不变、间隔和次数不变，再对所有最终执行计划枚举重复时间区间，确认无冲突。另核对提交表的装备编号、列位置、空白字段、撤销标记及所有数据行。

提交文件：[result2.xlsx](../results/result2.xlsx)。按附件2模板，只填写调整或撤销的装备：频移只填B列，时间平移只填C列，撤销只在D列填“是”，其余单元格留空。

完整最终计划和求解状态保存在 `answer/.cache/q2/solution.json`，可供问题3使用；独立验证记录保存在 `answer/.cache/q2/verification.json`。
'''
(ROOT/'answer/docs/问题2建模与结果.md').write_text(text, encoding='utf-8')
print(f"【问题2｜报告生成】完成；原样保留：{total['unchanged']}；调整：{total['adjusted']}；撤销：{total['canceled']}；最终执行：{150 - total['canceled']}")
