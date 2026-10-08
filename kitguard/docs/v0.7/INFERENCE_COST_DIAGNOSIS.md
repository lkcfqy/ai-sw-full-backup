# v0.3 推理阶段成本与错误来源诊断

复算时间：2026-10-02（韩国时间）。本轮只读了历史原始输出与冻结快照，没有运行 MLX、修改模型、挑选新测试图或改写旧结果。下文开发28图与当时留出64图均已曝光，今后使用只能称为开发/回归。

## 结论

**值得试验单方向清单后进行条件身份核查，但现有记录不支持直接晋升。** 在历史64图中，旋转核验没有挡住首轮的2个错误，反而使3个首轮正确结果弃权；两次同向错误的拦截来自局部身份核查。旋转占这次完整观察总耗时32.8%。不过开发28图的旋转确实挡住1个错误，且删去旋转会引入原来未执行的身份调用，无法用历史输出给候选“补算准确率”。

## 来源与计数定义

原始记录目录：

- `evaluation-runs/v03_guarded_integrated_development_v1/`：2026-09-26 21:23:59—21:41:04（韩国时间），28图。
- `evaluation-runs/v03_guarded_holdout_v1/`：2026-09-26 21:42:33—22:20:05（韩国时间），64图。

每图依次取原向清单、旋转清单、二者一致性派生结果、实际最终结果。C=四类数量完整正确且明确；W=数量有错但明确；U=未知/有阻断问题/要求补证；E=执行错误。任何U均保留在总分母。原向及旋转为真实保存输出；一致性是从两个真实输出按既有规则重建的中间状态，不是新模型调用。

逐行校验了运行状态、完整顺序和原定分母、manifest中的图片SHA与真值、首轮与最终计分；另以本次独立的接受条件逐件复算全部身份阻断类别，确认最终计数正好是二方向结果加这些阻断，没有改数为真值。未重新解码核验全部图像输入；这部分已有历史独立审计，本次没有将其冒称新做。

| 原始文件 | SHA-256 |
|---|---|
| 开发 predictions.jsonl | `defa8353d8f0ea2eb89ec3ae8fd0ecb0bc4e90b80caa8a32c075765548d6e9a4` |
| 开发 run.json | `da1467a6229ae184adea96adba5b1d0a972c5f53c6397e5120e03c6ebe72b3a0` |
| 开发 manifest.json | `8e85c97a5dee7d0c571964597a8282b312e7691e66c8c36da541cf41dd2283c6` |
| 64图 predictions.jsonl | `4a6ef7c976271cc3096bdd369b897b1db46bec21d2287699f55226308e7536a3` |
| 64图 run.json | `4e28b4508f5c390ca663c230c5c8d6546fb9dc6913526b8f36cafb7138882280` |
| 64图 manifest.json | `85f331c47d50256e1e98c3b346bef109e30a98e7e101da6ea3f46c9b7b3dcaf2` |

两次模型、revision、1536px、提示及身份判据相同，但 `vision.py` 快照哈希不同：开发为 `13107205a9c9366876b8e29bffe8f9f91471406d62cddf5b570540c62fee399e`，64图为 `1f69d3b45d35ff8bedda746f2c72bb506ea690bb66ccc855e64513253630b8ef`。实际diff仅增加身份调用前状态及异常诊断保存；观察协议哈希因此不同。两次各自在运行前后源码未变化，不能把两个运行说成逐字节相同版本。

## 分阶段结果

| 集合 | 原向清单 C/W/U/E | 单独旋转清单 C/W/U/E | 两方向一致性 C/W/U/E | 最终身份核查后 C/W/U/E |
|---|---|---|---|---|
| 开发28图 | 25/3/0/0 | 25/3/0/0 | 24/2/2/0 | 24/0/4/0 |
| 历史留出64图 | 62/2/0/0 | 59/5/0/0 | 59/2/3/0 | 59/0/5/0 |

开发集：旋转挡住1个错误，新增1个正确转弃权，保留2个两轮一致的错误；身份检查再挡住2个错误，没有新增正确转弃权。

64图：旋转挡错0个，新增3个正确转弃权，仍保留2个两轮一致的错误；身份检查挡住这2个错误，没有新增正确转弃权。最终正确明确覆盖从62/64降至59/64，错误明确从2/64降至0/64。**“挡错”在本项目中是转为未知，不是把错误答案自动修对。**

### 所有受影响案例

表中计数顺序固定为 bolt/nut/washer/bracket；`?` 表示未知。

| 集合与 case_id | 真值 | 原向 | 旋转 | 最终 | 变化来源 |
|---|---|---|---|---|---|
| 开发 `mvtec-loco-screw_bag-train-good-312` | 2/2/2/0 | 2/1/3/0 | 2/2/2/0 | 2/?/?/0 | 旋转分歧挡住原向误分；身份未调用 |
| 开发 `mvtec-loco-screw_bag-test-logical_anomalies-087` | 2/1/2/0 | 2/1/2/0 | 1/2/2/0 | ?/?/2/0 | 旋转引入误分，原向正确转弃权；身份未调用 |
| 开发 `v03-screws-screws_222-56eea59f64ca` | 2/1/0/0 | 2/0/1/0 | 2/0/1/0 | 2/?/?/0 | 身份将候选washer识别为nut，阻断两类 |
| 开发 `v03-screws-screws_122-2e63c6dbddd2` | 3/3/0/0 | 2/3/1/0 | 2/3/1/0 | ?/3/?/0 | 身份将候选washer识别为bolt，中心为closed_recess |
| 64图 `v03-screws-screws_343-db94a130dd55` | 3/2/0/0 | 3/2/0/0 | 3/0/2/0 | 3/?/?/0 | 旋转引入nut/washer误分；身份未调用 |
| 64图 `v03-screws-screws_127-3b1dbf13c1ae` | 0/2/0/0 | 0/2/0/0 | 0/1/1/0 | 0/?/?/0 | 旋转引入nut/washer误分；身份未调用 |
| 64图 `v03-screws-screws_113-402caabbd5cc` | 2/2/0/0 | 2/1/1/0 | 2/1/1/0 | 2/?/?/0 | 身份将候选washer识别为nut，阻断两类 |
| 64图 `v03-screws-screws_243-aab2c04ba8a4` | 3/3/0/0 | 2/3/1/0 | 2/3/1/0 | ?/3/?/0 | 身份将候选washer识别为bolt，中心为closed_recess |
| 64图 `v03-new-loco-screw_bag-test-logical_anomalies-055` | 2/2/3/0 | 2/2/3/0 | 1/2/3/0 | ?/2/3/0 | 旋转少计bolt；身份未调用 |

两批共有4个“两方向同错、身份挡住”的案例，保存的身份输出均发现原washer候选其实是nut或bolt。但这是事后诊断，**不据此临时改成只核查washer**：原有开发样本可能已塑造该错误分布，未覆盖的nut误分或遗漏无法因此排除。

## 时延分解

`runtime.seconds` 是包裹实际 `runtime["generate"]` 调用的墙钟秒数，包含该调用内部图像处理等，不是纯GPU kernel或只有token生成；不含之前的模型加载、模板与grammar创建、外部文件/裁图等。`row.latency_ms` 是历史benchmark上传与观察路径，不是新产品完整API/真人操作时间。两者相减只称未归入generate的余项。

| 集合/阶段 | 调用或图片数 | 总秒数 | 中位秒数 | p95（nearest-rank） | 最大秒数 |
|---|---:|---:|---:|---:|---:|
| 开发：原向 generate | 28 | 338.234 | 13.576 | 15.894 | 15.927 |
| 开发：旋转 generate | 28 | 337.661 | 13.555 | 15.831 | 16.020 |
| 开发：身份 generate | 23 | 338.876 | 17.678 | 20.565 | 21.000 |
| 开发：完整观察路径 | 28 | 1024.512 | 43.501 | 52.448 | 53.025 |
| 64图：原向 generate | 64 | 744.140 | 13.114 | 15.893 | 16.765 |
| 64图：旋转 generate | 64 | 738.801 | 13.093 | 15.783 | 15.927 |
| 64图：身份 generate | 53 | 752.306 | 15.823 | 18.204 | 20.608 |
| 64图：完整观察路径 | 64 | 2252.105 | 40.579 | 49.692 | 52.504 |

64图完整总耗时：原向33.04%、旋转32.80%、身份33.40%、其余0.75%；四项按未四舍五入值相加为100%。未归入generate的余项合计16.858秒、中位0.251秒、最大4.015秒。开发相应余项为9.741秒、中位0.262秒、最大3.930秒。并非每图都有身份调用，不能把三项中位数相加为总体中位数。

身份调用分布：开发23次（21次保持、2次阻断），5次跳过（2次两方向不清楚、3次无候选）；64图53次（51次保持、2次阻断），11次跳过（3次两方向不清楚、8次无候选）。64图共165个身份目标；一次调用批量核查所有所选点，而不是每个点一次调用。

| 64图身份目标数/次 | 实际调用数 | generate中位秒数 |
|---:|---:|---:|
| 1 | 8 | 5.824 |
| 2 | 6 | 9.633 |
| 3 | 12 | 13.352 |
| 4 | 26 | 17.758 |
| 5 | 1 | 20.608 |

这是按历史病例组成的描述性关系，不能直接推导裁剪数减少的因果收益，也不能随意只核查“看起来最可疑”的点后沿用原成绩。

## 最小候选开发实验

固定28张既有开发图，保持同一模型revision、1536px、原向空间清单提示、900token、身份提示与裁图几何、1800token、温度0。一次原向观察若不清楚就维持未知；若清楚且清单中有nut/washer，检查这些点的身份与独立性；全部通过才保留原计数，否则只把受影响类别设为未知。没有候选则保留原向结果。不要加入根据BOM、数据集名称、真值或当前结果是否答错进行分流的条件。

先开发并冻结一个候选，不并行搜索多个触发器；与当前guarded在同28图的真实运行比较C/W/U/E、错误类别、每阶段调用与完整路径时间。旧记录可作诊断参考，但新的速度比较应使用相同运行时/计时边界。协议、代码、模型、输入与完整分母保存，失败照记。开发上任何错误增加或结构性回归都应检查；在独立新来源留出前不改默认。

软件适配有一项必须透明：当前 `identity.select_targets` 和 `apply_decision` 的严格边界要求真实双方向verification。单向候选不能复制首轮假装第二方向。应另建显式单向实验适配，复用裁图、提示、响应结构与原接受判据，实验输出不冒称 `spatial_guarded`。

## 不能从历史记录推断的事

- 原方向清楚但二方向冲突的开发2图、64图3图没有执行身份核查；删旋转后这5图将进入新的身份调用，其结果和耗时未知。
- 原向+历史身份的子集可以用来说明哪些既有调用包含了支持证据，不能当作完整候选跑分。不得填造缺失身份结果，也不能把这些缺失病例移出分母。
- 738.801秒是历史旋转阶段成本，不等于部署删除旋转后必然净省的时间；新增身份调用、缓存/热状态、批量图像处理和新API开销需要实际测量。
- 单次重复旋转同错不能证明身份核查永远正确；本方法无法发现第一轮根本没列出的对象，零个已观察错误不是零风险。
- 64图已有相同公开采集域、无角码阳性等边界。该批现已参与本轮候选构思，不能在后续称为新留出。

## 无模型复算代码

从项目根目录执行下段Python即可重建主表与分阶段时延；仅使用标准库，读取上述原始文件，不加载模型、不写历史数据。完整身份接受条件复算已在本次诊断实际执行，下面保留同一公式。

```python
import collections, json, math, statistics
from pathlib import Path
PARTS = ('bolt', 'nut', 'washer', 'bracket')
def inventory(value):
    counts = {p: sum(o['part'] == p for o in value['objects']) for p in PARTS}
    unknown = set(value['uncertain_parts'])
    bad = bool(unknown or value['issues'] or value['action']['kind'] != 'none')
    if bad and not unknown:
        unknown = set(PARTS)
    return {p: None if p in unknown else counts[p] for p in PARTS}, not bad
def category(counts, clear, truth):
    return 'C' if clear and counts == truth else 'W' if clear else 'U'
def stats(values):
    ordered = sorted(values)
    return dict(n=len(values), total=sum(values), median=statistics.median(values),
                p95=ordered[math.ceil(.95 * len(values)) - 1], maximum=max(values))
for run in ('v03_guarded_integrated_development_v1', 'v03_guarded_holdout_v1'):
    root = Path('evaluation-runs') / run
    rows = [json.loads(line) for line in (root / 'predictions.jsonl').read_text().splitlines()]
    meta = json.loads((root / 'run.json').read_text())
    cases = {c['id']: c for c in json.loads((root / 'manifest.json').read_text())['cases']}
    assert meta['status'] == 'completed' and not meta['source_changed_during_run']
    assert len(rows) == meta['expected_cases'] and [r['case_id'] for r in rows] == meta['case_ids']
    metrics = {k: collections.Counter() for k in ('first', 'second', 'consensus', 'final')}
    times = {k: [] for k in ('first', 'second', 'identity', 'pipeline', 'residual')}
    transitions = collections.Counter()
    for r in rows:
        assert r['sha256'] == cases[r['case_id']]['sha256']
        assert r['ground_truth'] == cases[r['case_id']]['ground_truth']
        d = r['observation_diagnostics']; first, second = d['passes']
        a, ac = inventory(first['inventory']); b, bc = inventory(second['inventory'])
        c = {p: a[p] if a[p] is not None and a[p] == b[p] else None for p in PARTS}
        cc = ac and bc and all(v is not None for v in c.values())
        identity = d['identity']; blocked = set(); response = {
            i['id']: i for i in identity.get('response', {}).get('objects', [])}
        for target in identity.get('crops', []):
            i = response[target['id']]
            accepted = (i['part'] == target['original_part'] and
                        i['status'] == 'independent_object' and not i['issue'].strip() and
                        (i['part'] != 'washer' or i['opening'] == 'through_hole'))
            if not accepted:
                blocked.add(target['original_part'])
                if i['part'] != 'unknown' and i['part'] != target['original_part']:
                    blocked.add(i['part'])
        assert blocked == set(identity.get('blocked_categories', []))
        o = r['observation']
        assert o['observed'] == {p: None if p in blocked else c[p] for p in PARTS}
        oc = (all(v is not None for v in o['observed'].values()) and
              not o['issues'] and o['action']['kind'] == 'none')
        assert r['counts_exact'] == (o['observed'] == r['ground_truth'])
        assert r['actionable_counts'] == oc
        scores = [category(a, ac, r['ground_truth']), category(b, bc, r['ground_truth']),
                  category(c, cc, r['ground_truth']),
                  'E' if r['error'] else category(o['observed'], oc, r['ground_truth'])]
        for key, score in zip(metrics, scores): metrics[key][score] += 1
        transitions[tuple(scores)] += 1
        seconds = [first['runtime']['seconds'], second['runtime']['seconds']]
        times['first'].append(seconds[0]); times['second'].append(seconds[1])
        if 'seconds' in identity.get('runtime', {}):
            v = identity['runtime']['seconds']; times['identity'].append(v); seconds.append(v)
        total = r['latency_ms'] / 1000
        times['pipeline'].append(total); times['residual'].append(total - sum(seconds))
    print(run, metrics, transitions, {k: stats(v) for k, v in times.items()})
```
