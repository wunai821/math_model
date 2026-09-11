# D题：时频冲突检测与消解

## 问题4模型复测入口

在 `answer` 目录执行 `uv sync --frozen --python 3.13.2`，再执行 `uv run --frozen python src/q4/reproduce.py`。此入口从原始附件重建完整约束，以持久基准为提示，复测目标向量 `(3,0,3,141,18,37,848)`；不依赖现有缓存，也不覆盖正式结果。它是指定指标的可行性复测，不是重新证明最优。

若要不读取任何旧方案、从头搜索3撤销且A类全保，执行 `uv run --frozen python src/q4/reproduce.py --mode search --seconds 120 --workers 2`。本轮已独立重新搜到该核心结果，后续调整指标可能不同。重复运行请用 `--output` 指定新的空目录。

完整模型、运行命令和验收条件见 [问题4模型与复测说明](answer/docs/问题4模型与复测说明.md)。正式求解和复测共用 `src/q4/model.py`，基准保存在可随项目交付的 `answer/benchmarks/q4_reference.json`。默认 `solve.py` 在无缓存时也会使用此基准作提示，并保留已验证方案的目标上界。

## 文件位置

```text
D题.pdf                      原始题目
附件/
  附件1.xlsx                 原始用频计划
  附件2/                     四问的原始结果模板
answer/
  .venv/                     uv Python虚拟环境
  pyproject.toml             Python项目与依赖声明
  uv.lock                    Python依赖锁定文件
  src/q1/
    solve.py                 问题1检测与独立复核
    export_xlsx.py           按模板导出问题1结果
  src/q2/
    solve_compact.py         问题2紧凑约束优化模型
    solve.py                 问题2网格候选参考模型
    verify.py                独立检查最终方案和提交表
    export_xlsx.py           按模板导出问题2结果
    report.py                生成问题2建模与统计说明
  src/q3/
    solve.py                 固定问题2方案，最大化新增C类装备数量
    export_xlsx.py           按模板导出问题3结果
    verify.py                独立复核基准计划、新增计划与提交表
    report.py                生成问题3建模与结果说明
  src/q4/
    solve.py                 含C类间隔调整的网格候选优化模型
    solve_compact.py         等价的装备对与安全时间模式优化模型
    select.py                独立检查候选方案，按7层目标择优
    improve_local.py         固定邻域外计划的小范围重排
    lower_bound.py           子集放松模型，用于下界诊断
    export_xlsx.py           按模板导出问题4结果
    verify.py                独立检查单参数限制、周期冲突与提交表
    report.py                生成问题4建模与统计说明
  src/scheduling.py          问题3、4共用输入和资源网格函数
  src/verify_schedule.py     不依赖求解器的独立区间验证
  src/test_scheduling.py     边界回归测试
  results/                   最终提交文件
    result1.xlsx
    result2.xlsx
    result3.xlsx
    result4.xlsx
  docs/                      建模方法与结果说明
    问题1建模与结果.md
    问题2建模与结果.md
    问题3建模与结果.md
    问题4建模与结果.md
  .cache/q1/                 问题1中间数据、预览与检查记录
  .cache/q2/                 问题2完整方案、求解状态和验证记录
```

原始题目和附件保留在原位置。四问代码分别位于 `answer/src/q1` 至 `q4`，提交表统一放入 `answer/results`，建模说明统一放入 `answer/docs`。

## 队友电脑运行说明

从 GitHub 获取项目后，必须保持 `附件/` 与 `answer/` 同级。在 `answer` 目录执行 `uv sync` 即可恢复 Python 依赖。

Excel 导出统一使用项目自带的 Python 脚本：

```powershell
uv run python src/export_xlsx.py 1
uv run python src/export_xlsx.py 2
uv run python src/export_xlsx.py 3
uv run python src/export_xlsx.py 4
```

每一问求解完成后再运行对应导出，不需要额外安装其他运行时。

## 运行问题1

在 `answer` 目录执行：

```powershell
uv sync
uv run python src/q1/solve.py
```

程序读取原始附件，执行区间交叠检测与独立网格复核，将冲突对和统计结果写入 `.cache/q1/data.json`。当前结果为297个冲突装备对，涉及148台装备。

导出问题1结果，在 `answer` 目录执行：

```powershell
uv run python src/export_xlsx.py 1
```

运行后更新 `results/result1.xlsx`。Python依赖可直接用 `uv sync` 恢复。

`.venv`、`.cache` 和Python缓存已加入Git忽略规则。最终结果文件和建模说明不忽略。

## 运行问题2

在 `answer` 目录执行：

```powershell
uv sync
uv run python src/q2/solve_compact.py
uv run python src/export_xlsx.py 2
uv run python src/q2/verify.py
uv run python src/q2/report.py
```

本轮正式续算固定前两个已证明目标，使用 B 类撤销阶段480秒、调整总数阶段120秒、其余阶段60秒和3个工作线程：

```powershell
uv run python src/q2/solve_compact.py --hint solution.json --output candidate_q2_20260911.json --fix-prefix 2 --cancel-b-seconds 480 --mid-seconds 120 --late-seconds 60 --workers 3
```

续算得到目标向量 **(6, 0, 4, 126, 16, 34, 775)**；前两个目标已证明最优，B类撤销阶段为限时可行，求解器下界为1。与此前方案相比，B类撤销由5降至4，但调整总数和成本分别由125、771变为126、775。候选文件应先独立核验并与现有方案比较，确认采纳后再更新 `solution.json`、导出和生成报告。多线程限时优化重复运行可能得到不同的可行方案，应以对应验证结果和阶段状态为准。

求解使用OR-Tools CP-SAT，分阶段优化撤销数量、调整数量、类别优先级和平移幅度。时间限制内返回的可行解不一定最优，具体状态和下界写入建模说明。`verify.py`独立读取原始数据，核查最终全部计划与导出的Excel；发现错误时返回非零退出码。

主模型输出 `.cache/q2/solution.json`，最终提交表为 `results/result2.xlsx`，报告为 `docs/问题2建模与结果.md`。

第二轮补充了 `src/q2/improve_local.py`。它释放部分装备、固定其余计划，以严格字典序目标重排。`--size 150`释放全体装备；`--fix-prefix 3`仅固定当前前三项目标数量，不表示第三项目标已经证明最优。候选经过独立操作与冲突核查，仅记录实际改善，默认不替换正式方案。

```powershell
uv run python src/q2/improve_local.py --input solution.json --output round2_full.json --rounds 1 --size 150 --seconds 150 --workers 3 --seed 9187 --fix-prefix 3
```

本轮12次局部重排及上述全体重排均未改善现有方案，因此问题2提交表不变，问题3继续使用已核验的142台方案。局部模型返回OPTIMAL仅表示对应固定邻域内最优。新增测试覆盖候选提示、固定前缀、邻域选择及目标优先级，连同现有测试共20项。

## 运行问题3

先完成问题2的求解、导出和验证，再在 `answer` 目录执行：

```powershell
uv run python src/q3/solve.py --workers 4
uv run python src/export_xlsx.py 3
uv run python src/q3/verify.py
uv run python src/q3/report.py
```

模型固定当前问题2的144项有效计划，新增装备继承附件1中C类统一需求（频宽3、单次时长2、空闲间隔8、使用12次）。不增加资源解释为使用原始频域 `[0,100)` 和时域 `[0,643)`，时间窗口右端点取附件1所有计划最后一次结束时刻的最大值。在此假设下，当前基准方案最多新增 **142台**，CP-SAT已证明最优。

程序枚举全部合法频段与首次时间起点，过滤与固定计划冲突的候选，再优化新增候选之间的资源排斥。`--seconds` 设置求解时限，默认180秒。若限时仅有可行解，记录数量与上界，不声称达到最大值。

`.cache/q3/solution.json`记录q2基准及原始附件的SHA-256。更改q2方案后必须重跑q3；验证程序会检查基准是否变化，并独立读取result2.xlsx及result3.xlsx核对全部行。完整方案、验证记录位于 `.cache/q3`。

## 运行问题4

在 `answer` 目录执行：

```powershell
uv run python src/q4/solve.py --workers 4
uv run python src/export_xlsx.py 4
uv run python src/q4/verify.py
uv run python src/q4/report.py
```

问题4从附件1原始计划重新求解；若存在q2完整方案，仅用作初始提示，不固定其决策。允许C类选择调整空闲间隔±10，调整后间隔非负；每台装备仍只能选择频移、首次时间平移、间隔调整中的一种，或者撤销。A、B类不允许调整间隔。频宽、单次时长和使用次数保持不变。

默认撤销总数阶段180秒，其余每阶段60秒，可用 `--primary-seconds`、`--seconds`、`--workers` 调整。各阶段结果逐次保存；限时可行解与最优性证明明确区分，后续目标的界以前序锁定值为条件。最终统计和阶段状态见 `docs/问题4建模与结果.md`。

本次另外用紧凑模型继续求解并择优。复现此步骤时，在网格求解之后、最终导出之前执行：

```powershell
Copy-Item .cache/q4/solution.json .cache/q4/grid_solution.json
uv run python src/q4/solve_compact.py --workers 4
uv run python src/q4/select.py grid_solution.json compact.json
```

紧凑模型默认首阶段120秒，后续阶段各60秒，支持 `--primary-seconds`、`--later-seconds`。此前一次运行后续阶段仅20秒，第二阶段返回UNKNOWN，保留了首阶段找到的4撤销方案；该方案属于历史结果。另在本轮全模型中限制撤销不超过2，搜索120秒返回UNKNOWN，不能证明2撤销不可行。目前全局撤销下界仍为2。

紧凑模型将时间平移和间隔变化枚举为有限模式，预计算每对装备的安全模式组合；与网格模型遵守完全相同的单参数和无冲突约束。默认只写 `.cache/q4/compact.json`，选择程序核查两份方案后更新 `solution.json`，随后应重新导出、验证并生成报告。

### 问题4续算（历史过程记录）

此前一轮续算入口可从经过独立检查的q4方案启动。以下命令先做局部重排，再固定撤销总数及A/B类撤销数，优化剩余目标：

```powershell
uv run python src/q4/improve_local.py
uv run python src/q4/solve.py --hint local.json --output grid_refined.json --fix-prefix 3 --seconds 45 --workers 4
uv run python src/q4/select.py solution.json local.json grid_refined.json
uv run python src/export_xlsx.py 4
uv run python src/q4/report.py
```

`--hint`、`--output`均为 `.cache/q4` 内的文件名。`--fix-prefix 3`固定输入方案的前三项目标，不等于证明这三项已最优；后续求解的界都以此前固定值为条件。局部搜索使用严格字典序的混合进位整数目标，只接受目标向量改善；其邻域下界不作为全局下界。最终选择程序保留历史比较中的最强撤销下界。

此前另一轮续算还将紧凑模型主阶段延长到300秒（`--output refined.json --primary-seconds 300 --later-seconds 90 --workers 4`），未降低撤销数；其固定调整140项后的阶段被139项的局部方案支配，因此停止了后续无益计算。该历史网格优化结果见问题4报告早期记录；不同线程调度可能产生不同的限时结果。

历史续算曾得到 `(4, 0, 1, 139, 16, 37, 828)`；随后得到的 `(4, 0, 1, 135, 16, 37, 826)` 也属于历史结果。本轮使用保留 A 类的3撤销候选继续优化：

```powershell
uv run python src/q4/check_cancel_limit.py --limit 3 --keep-a --seconds 90 --workers 2
uv run python src/q4/solve.py --hint cancel_limit_3_keep_a_candidate.json --output cancel3_keep_a_refined.json --fix-prefix 1 --seconds 10 --workers 3
uv run python src/q4/select.py solution.json cancel3_keep_a_refined.json
uv run python src/export_xlsx.py 4
uv run python src/q4/report.py
```

当前择优方案的目标向量为 **(3, 0, 3, 141, 18, 37, 848)**，对应撤销总数、A类撤销、B类撤销、调整总数、A类调整、B类调整和归一化成本。相较历史4撤销方案，撤销总数按既定优先顺序改善，A 类撤销数保持为0；代价是 B 类撤销由1增至3、调整总数由135增至141。撤销总数已知下界为2，当前方案及后续目标均为限时可行结果，尚未证明字典序最优。按当前 `solution.json` 计算，超过问题3窗口右端643的有效计划为 C068（650）、C088（651）、C082（652）、C085（681），最晚结束时刻为681。问题4没有统一结束时刻上限，不能套用问题3的 `[0,643)` 窗口。最终文件为 `results/result4.xlsx`，统计与求解条件见 `docs/问题4建模与结果.md`。

此前第二轮使用不同随机种子进行全局搜索，再固定前四项目标续算，将调整总数从137降至135，其他指标不变（历史过程）：

```powershell
uv run python src/q4/solve.py --hint solution.json --output round2_global.json --primary-seconds 180 --seconds 12 --workers 3 --seed 20260912
uv run python src/q4/solve.py --hint round2_global.json --output round2_refined.json --fix-prefix 4 --seconds 40 --workers 3 --seed 9174
uv run python src/q4/select.py solution.json round2_global.json round2_refined.json
```

择优后重新导出、验证并生成报告。限时结果可能随机器和线程调度变化。

比赛规则和可确认的AI参与环节已记入 `docs/规则核对与AI使用记录.md`。该文件明确区分程序自动核验与参赛队人工审查，不能代替最终人工复核及规定的AI使用详情PDF。

问题3、4也使用 `src/export_xlsx.py` 导出，不依赖额外运行时。问题3、4验证器要求对应最终Excel存在；失败返回非零退出码。

报告程序会再次调用验证器，避免输出未经验证或与当前表格不一致的统计。

运行边界测试：

```powershell
uv run python -m unittest discover -s src -p "test*.py" -v
```

测试覆盖非负间隔、类别权限、单参数限制、撤销与调整互斥、半开区间端点以及最后一次重复时段冲突。
