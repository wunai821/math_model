# D题：时频冲突检测、消解与容量扩展

这是“无线电装备时频资源分配”问题的完整建模与复现项目。项目从附件中的 150 项原始用频计划出发，依次完成：

1. 检测哪些装备存在用频冲突；
2. 通过频段平移、首次时间平移或撤销来消解冲突；
3. 在问题2方案固定的前提下，计算最多还能新增多少台 C 类装备；
4. 允许 C 类装备调整使用间隔后，重新寻找更好的冲突消解方案。

项目同时保存了最终 Excel 提交表、建模说明、可视化图表、验证程序和可复测代码。最终结果可以直接阅读；如果需要从原始附件重新计算，也可以按照下面的步骤操作。

## 先用一句话看懂四个问题

可以把整道题想成“给很多装备安排频率和时间，不能互相占同一块资源”：

| 问题 | 白话问题 | 我们实际做的事 |
|---|---|---|
| 1 | 现在到底哪里撞车了？ | 把150项计划两两检查，找出频率和时间都重叠的装备对。 |
| 2 | 撞车后怎么挪？ | 每台装备最多做一种小调整：挪频率、挪首次时间，或者撤销；目标是尽量少撤销、少调整。 |
| 3 | 还塞得下多少台新C类装备？ | 固定问题2的方案，在不扩大 `[0,100)×[0,643)` 资源窗口的前提下，寻找最多的新位置。 |
| 4 | 如果C类装备还能改变使用间隔，会不会更好？ | 重新从原始计划出发，允许C类改变间隔，再做一次冲突消解。 |

每个问题都按同一套专业流程处理：**读入数据 → 明确区间和约束 → 建立离散优化模型 → 求解 → 独立验证 → 导出Excel和图表**。因此文档中的“建模”不是只写公式，而是会说明“为什么这样判断、程序检查了什么、结果能不能称为最优”。想快速理解某一问，可直接打开：[问题1](answer/docs/问题1建模与结果.md)、[问题2](answer/docs/问题2建模与结果.md)、[问题3](answer/docs/问题3建模与结果.md)、[问题4](answer/docs/问题4建模与结果.md)。

## Markdown 和源码怎么联动

每一问的 Markdown 不是孤立的说明文字，而是和对应的程序入口、缓存结果、验证器及 Excel 导出程序一一对应：

| 环节 | 作用 | 典型产物 |
|---|---|---|
| 求解脚本 | 根据附件建立模型并寻找方案 | `answer/.cache/q*/solution.json` |
| 验证脚本 | 不依赖求解器，重新检查约束和冲突 | `answer/.cache/q*/verification.json` |
| 报告脚本 | 从已验证的缓存结果整理 Markdown 数值 | `answer/docs/问题*建模与结果.md` |
| 导出脚本 | 按附件2模板生成提交表 | `answer/results/result*.xlsx` |

每份题目说明的末尾都列出了对应源码链接，并增加了关键函数的源码解读。修改模型后，建议始终按“**重新求解 → 独立验证 → 生成报告 → 导出Excel**”的顺序运行；不要只手工改 Markdown 或 Excel，否则说明、程序和提交表可能不一致。

## 一、先看最终结果

如果只是查看答案，不需要重新运行求解器：

- 四问提交表：[`answer/results/`](answer/results/)
- 建模与结果说明：[`answer/docs/`](answer/docs/)
- 全部图表：[`answer/figures/`](answer/figures/)
- 原始题目：[`D题.pdf`](D题.pdf)
- 原始附件：[`附件/`](附件/)

当前已验证方案的主要结果如下。问题2和问题4采用“先最小化撤销，再逐层优化调整数量和调整幅度”的字典序目标；限时阶段只说明得到可行解，不把它误称为全局最优。

| 问题 | 结果 | 独立验证结论 |
|---|---|---|
| 问题1 | 297 对冲突，涉及 148 台装备 | 冲突检测通过 |
| 问题2 | 原样保留 18 项、调整 126 项、撤销 6 项，执行 144 项 | 最终冲突对数为 0；撤销总数 6 已证明最优 |
| 问题3 | 新增 142 台 C 类装备 | 在固定问题2方案和 `[0,100)×[0,643)` 窗口下已证明最优 |
| 问题4 | 原样保留 6 项、调整 141 项、撤销 3 项，执行 147 项 | 冲突对数为 0；当前撤销数为可行解，已知下界为 2，尚未证明最优 |

问题2的调整包括频移 91 项、时间平移 35 项。问题4的调整包括频移 57 项、首次时间平移 37 项、C 类间隔调整 47 项。

## 二、电脑环境

项目使用 Python 3.13 和 `uv` 管理依赖。下面命令以 Windows PowerShell 为例。

如果电脑尚未安装 `uv`，请先按 [uv 官方文档](https://docs.astral.sh/uv/) 安装。安装后检查：

```powershell
uv --version
python --version
```

从 GitHub 下载项目后，请确认目录结构没有被打乱：`附件` 和 `answer` 必须位于项目根目录 `D题` 下，不能把 `answer` 单独移走。

进入 `answer` 目录并安装锁定版本依赖：

```powershell
cd D:\D题\answer
uv sync --frozen --python 3.13.2
```

如果本机已经有兼容的 Python 3.13，也可以使用：

```powershell
uv sync --frozen
```

依赖主要包括：

- `openpyxl`：读取原始 Excel、核对模板并导出结果；
- `ortools`：运行 CP-SAT 组合优化模型；
- 项目自带的 Python 标准库代码：区间检查、报告生成和图表生成。

## 三、最快的完整复现流程

下面流程会按问题顺序重新生成中间结果、提交表、验证记录、报告和图表。求解器有时间限制，多线程限时求解在不同电脑上可能得到不同的可行方案；因此“重新运行”不一定逐字节得到仓库中保存的 Excel，但必须通过独立验证。

在 `answer` 目录执行：

```powershell
# 1. 检测原始冲突
uv run --frozen python src/q1/solve.py

# 2. 消解冲突
uv run --frozen python src/q2/solve_compact.py

# 3. 固定问题2方案，最大化新增 C 类装备
uv run --frozen python src/q3/solve.py --workers 4

# 4. 允许 C 类调整间隔后重新优化
uv run --frozen python src/q4/solve.py --workers 4

# 5. 按附件2模板导出四个 Excel
uv run --frozen python src/export_xlsx.py 1
uv run --frozen python src/export_xlsx.py 2
uv run --frozen python src/export_xlsx.py 3
uv run --frozen python src/export_xlsx.py 4

# 6. 独立验证四个结果
uv run --frozen python src/q2/verify.py
uv run --frozen python src/q3/verify.py
uv run --frozen python src/q4/verify.py

# 7. 生成建模与结果报告
uv run --frozen python src/q2/report.py
uv run --frozen python src/q3/report.py
uv run --frozen python src/q4/report.py

# 8. 重新生成图1—图13
uv run --frozen python src/visualize.py
```

注意：第 5 步的导出程序会读取 `.cache/q1` 至 `.cache/q4` 中的最新方案，因此必须先完成相应求解。问题1没有单独的 `verify.py`，运行 `q1/solve.py` 本身就会重新检测并写入冲突数据。

## 四、只查看或重新生成图表

仓库已经保存了生成好的图表，可以直接打开 `answer/figures`。如果已经拥有完整 `.cache`，只需执行：

```powershell
cd D:\D题\answer
uv run --frozen python src/visualize.py
```

程序会生成图1至图13。图3额外输出三种格式：

- `图3_装备用频冲突网络.png`：适合插入论文；
- `图3_装备用频冲突网络.svg`：适合继续编辑；
- `图3_装备用频冲突网络.pdf`：适合打印或论文排版。

图6和图13中的紫色标识含义如下：

- 图6：紫色描边表示发生频移或首次时间平移的调整计划；
- 图13：紫色描边表示改变 C 类使用间隔的计划。

## 五、四个问题分别做了什么

### 问题1：冲突检测

程序读取 `附件/附件1.xlsx` 中的 150 项计划。每项计划包含装备编号、频段、首次使用时间、单次使用时长、使用间隔和重复次数。

两台装备只要存在一组重复使用区间同时满足以下两点，就记为一对冲突：

- 频段区间相交；
- 时间区间相交。

所有区间均使用左闭右开表示，例如 `[0,10)` 与 `[10,20)` 只在端点相接，不算冲突。结果写入 `answer/.cache/q1/data.json`，包括冲突装备对、冲突类型统计和冲突度数。

运行：

```powershell
uv run --frozen python src/q1/solve.py
uv run --frozen python src/export_xlsx.py 1
```

### 问题2：频移或首次时间平移消解冲突

每台装备最多选择一种操作：

- 频移 `Δf∈[-10,10]`；
- 首次时间平移 `Δt∈[-5,5]`；
- 撤销。

频宽、单次时长、使用间隔和使用次数保持不变；频移和时间平移不能同时非零。最终所有未撤销装备必须没有冲突。

目标按以下顺序逐层优化：

1. 撤销总数；
2. A 类撤销数；
3. B 类撤销数；
4. 调整总数；
5. A 类调整数；
6. B 类调整数；
7. 平移幅度成本。

常用命令：

```powershell
uv run --frozen python src/q2/solve_compact.py
uv run --frozen python src/export_xlsx.py 2
uv run --frozen python src/q2/verify.py
uv run --frozen python src/q2/report.py
```

如果只想尝试一次限时续算，可以使用 `--hint` 指定已有方案、使用 `--output` 另存候选，不要直接覆盖正式方案：

```powershell
uv run --frozen python src/q2/solve_compact.py `
  --hint solution.json `
  --output candidate_q2.json `
  --workers 3
```

候选方案应先运行 `verify.py` 并与当前 `solution.json` 比较，确认更好后再采纳。

### 问题3：固定问题2方案后新增 C 类装备

问题3不重新调整问题2的装备，而是在问题2的有效计划固定后寻找新增位置。新增 C 类装备沿用附件1中的统一需求：频宽 3、单次时长 2、间隔 8、使用 12 次。

本项目将“不增加时频资源”解释为使用频域 `[0,100)`、时域 `[0,643)`。这个时间窗口是根据原始计划最后一次结束时刻计算出的建模假设，并非问题4的统一结束时刻。

运行：

```powershell
uv run --frozen python src/q3/solve.py --workers 4
uv run --frozen python src/export_xlsx.py 3
uv run --frozen python src/q3/verify.py
uv run --frozen python src/q3/report.py
```

验证程序会检查：问题2基准是否一致、新增装备是否在窗口内、12 次重复使用是否全部合法、原有与新增装备之间以及新增装备之间是否均无冲突。

### 问题4：允许 C 类调整使用间隔

问题4从附件1原始计划重新开始求解。除问题2允许的频移、首次时间平移和撤销外，C 类装备还可以调整使用间隔 `Δg∈[-10,10]`，且调整后间隔必须非负。A、B 类装备不能改变间隔。

同一台装备仍然只能选择一种操作：频移、首次时间平移、间隔调整或撤销。频宽、单次时长和使用次数不变。问题4没有强行套用问题3的 `[0,643)` 时间窗口；如果要增加统一结束时刻，必须同步修改模型、验证器并重新求解。

运行正式网格模型：

```powershell
uv run --frozen python src/q4/solve.py --workers 4
uv run --frozen python src/export_xlsx.py 4
uv run --frozen python src/q4/verify.py
uv run --frozen python src/q4/report.py
```

项目还提供一个等价的紧凑模型，可与网格模型的结果进行比较：

```powershell
Copy-Item .cache/q4/solution.json .cache/q4/grid_solution.json
uv run --frozen python src/q4/solve_compact.py --workers 4
uv run --frozen python src/q4/select.py grid_solution.json compact.json
```

`select.py` 会核查候选方案并按相同的七层目标择优。限时求解可能只返回可行解；报告中的 `OPTIMAL` 表示相应阶段已证明最优，`FEASIBLE` 表示当前方案可行但未证明全局最优。

如果只想复测当前问题4的核心指标，可以使用：

```powershell
uv run --frozen python src/q4/reproduce.py
```

该入口从原始附件重建约束，以项目中保存的基准作为提示，不依赖已有 `.cache`，也不会覆盖正式结果。它用于复测指定可行方案，不等同于重新证明整个多目标问题的全局最优性。想从头搜索可使用：

```powershell
uv run --frozen python src/q4/reproduce.py --mode search --seconds 120 --workers 2
```

## 六、验证和测试

验证程序与求解器相互独立，主要检查：

- 装备编号是否完整且无重复；
- 频移、时间平移、间隔调整是否为整数；
- 调整幅度和类别权限是否满足题目要求；
- 频段是否仍在资源边界内，首次时间是否非负；
- 频宽、单次时长、使用间隔、使用次数是否保持不变；
- 所有重复使用区间是否无冲突；
- Excel 模板的列位置、撤销标记、空白字段和行数是否正确。

运行全部边界测试：

```powershell
uv run --frozen python -m unittest discover -s src -p "test*.py" -v
```

测试覆盖非负间隔、类别权限、单参数限制、撤销与调整互斥、半开区间端点和最后一次重复时段冲突等情况。

## 七、目录说明

```text
D题/
├─ D题.pdf                         原始题目
├─ 附件/
│  ├─ 附件1.xlsx                   原始用频计划
│  └─ 附件2/result1~4.xlsx         Excel 结果模板
├─ answer/
│  ├─ pyproject.toml               Python 项目与依赖声明
│  ├─ uv.lock                      锁定依赖版本
│  ├─ src/
│  │  ├─ q1/solve.py               问题1冲突检测
│  │  ├─ q2/solve_compact.py       问题2紧凑优化模型
│  │  ├─ q3/solve.py               问题3新增容量模型
│  │  ├─ q4/solve.py               问题4网格优化模型
│  │  ├─ q4/solve_compact.py       问题4紧凑优化模型
│  │  ├─ q4/reproduce.py           问题4独立复测入口
│  │  ├─ export_xlsx.py            按模板导出 result1~4.xlsx
│  │  ├─ verify_schedule.py        通用区间验证工具
│  │  ├─ visualize.py              生成图1~图13
│  │  └─ test_*.py                 回归测试
│  ├─ results/                     最终提交表
│  ├─ figures/                     全部可视化图表
│  ├─ docs/                        建模、结果和复测说明
│  ├─ benchmarks/                  问题4复测基准
│  └─ .cache/                      求解中间文件（本地生成，默认不提交）
└─ README.md                       项目使用说明
```

## 八、几个容易混淆的地方

### 1. 为什么 GitHub 上没有 `.cache`？

`.cache` 保存求解中间结果、日志和预览文件，已加入 `.gitignore`，因此不会随仓库提交。最终 Excel、图表和报告不依赖阅读者拥有这些中间文件；如果要重新求解或重新生成图表，先按“完整复现流程”生成 `.cache`。

### 2. `OPTIMAL` 和“整个问题最优”是一回事吗？

不是。多目标模型按阶段求解。某个阶段标记 `OPTIMAL`，只表示在此前已锁定目标值的条件下，该阶段目标已经证明最优；后续阶段可能仍然只是 `FEASIBLE`。阅读问题2、问题4报告时，应同时看当前值、下界和状态。

### 3. 为什么重新运行后结果可能和仓库里的 Excel 不完全一样？

CP-SAT 使用限时、多线程和随机种子。相同模型可能找到多个同样可行的方案，或在限时结束时得到不同的后续目标值。只要方案通过独立验证，并且目标向量没有违反报告中的比较规则，就属于合法复现结果。

### 4. 为什么问题3有 `[0,643)` 窗口，而问题4没有？

问题3需要在“不增加时频资源”的前提下新增装备，因此显式采用原始计划覆盖出的窗口 `[0,643)`。原题没有给问题4统一结束时刻，问题4只使用题目明确给出的非负起点和调整幅度约束，不能自动套用问题3窗口。

### 5. 导出结果时应该改哪些单元格？

不要手工修改 `answer/results` 中的最终表。应修改或重新生成 `.cache/q*` 方案，再运行 `src/export_xlsx.py`。导出脚本会保留模板表头、清空旧数据，按当前方案重新填写结果，避免不同次求解的行数变化造成旧记录残留。

## 九、相关说明文件

- [问题1建模与结果](answer/docs/问题1建模与结果.md)
- [问题2建模与结果](answer/docs/问题2建模与结果.md)
- [问题3建模与结果](answer/docs/问题3建模与结果.md)
- [问题4建模与结果](answer/docs/问题4建模与结果.md)
- [问题4模型与复测说明](answer/docs/问题4模型与复测说明.md)
- [本轮优化记录](answer/docs/本轮优化记录.md)
- [图表清单](answer/figures/图表清单.md)
