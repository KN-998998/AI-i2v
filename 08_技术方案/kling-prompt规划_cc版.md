# 可灵 3.0 图生视频 · 提示词组装模块规格

> **文档性质**：实现规格（Specification）。不假设技术栈，不包含框架代码。
> **交付目标**：改造现有工具「提示词环节」，将自由文本输入替换为结构化槽位选择 + 确定性提示词组装。
> **版本**：v1.0
> **适用模型**：可灵 3.0（Kling 3.0）image-to-video

---

## 0. 范围界定

### 0.1 本次要做什么

实现一个**纯函数**（无副作用、无网络请求、同输入必同输出）：

```
assemblePrompt(config: PromptConfig) -> PromptResult
```

以及驱动该函数所需的**槽位选择 UI**。

### 0.2 本次不要做什么

| 不做 | 原因 |
|---|---|
| 不改动可灵 API 的调用层、鉴权、轮询、任务队列 | 现有实现可用，仅需接收一个新参数（见 §8） |
| 不做视频后处理与裁切 | 二期，见 §9 |
| 不做预设包（Preset） | 二期，但数据模型需预留字段，见 §9 |
| **不提供任何自由文本输入框**（`l2.target` 除外，且受严格校验） | 见 §1 原则 5 |

---

## 1. 核心设计原则（实现时不得违反）

> ⚠️ **给 AI 编程工具的重要提示**：以下 6 条是本规格的地基，不是可优化的实现细节。若你认为某条"可以改进"，请先向使用者确认，不要自行调整。

### 原则 1：可灵不是 LLM，是扩散模型

它的文本编码器做的是"把词映射到视觉特征"，不是"理解意图"。因此：

- **禁止**在提示词中加入任务概括（如"你的任务是根据参考图生成视频""基于参考图生成图生视频"）。`参考图`/`生成`/`任务`/`保持一致` 这类词在视觉空间中无对应物，只会稀释注意力。
- **禁止**在提示词中加入示例（few-shot）。模型会尝试把示例中的物体真的渲染进画面。
- 允许的"概括"仅限**视觉锚点**（如 `浅景深`、`实拍质感`），因其描述的是画面属性而非任务。

### 原则 2：否定句必须走 `negative_prompt` 字段

正向提示词的编码器对否定词的处理能力弱，`不要出现冰块` 极可能被提取为 `冰块`，反而诱发该元素。

**推论：空槽位必须整段删除，绝不能生成"无次级动态""不含火焰"之类的占位句。**

### 原则 3：一条 3 秒切片只能有一个镜头动作

3 秒约 90 帧。多个镜头指令会被模型平均成"轻微位移"。因此 `camera_move` 恒为单选。

### 原则 4：注意力预算有限，次级动态上限 2 项

点名越多，每项越退化。硬上限 2，超出即阻断。

### 原则 5：条件逻辑必须在前端解决

扩散模型不执行判断。提示词中**禁止出现** `若`/`如果`/`则`/`存在...时` 等条件句式。通用性由槽位组合实现，不由模型现场推理实现。

### 原则 6：分段结构的价值是"指令隔离"

【镜头】【主运动】【次级动态】【锁定】【光线】【节奏】六段，每段只承载一类指令。这防止了同一句话内出现自相矛盾的描述（例如"高光流动"与"不流淌"），也让工具可以做整段替换而不重写全串。

**段落顺序固定，不得调整。**

---

## 2. 数据模型

### 2.1 输入契约 `PromptConfig`

```
PromptConfig {
  mode:              Mode                  // 必填
  camera_move:       CameraMove            // 必填
  camera_amplitude:  Amplitude             // 必填
  elements:          Element[]             // 必填，L0，长度 >= 1
  l1_subject:        L1Subject             // 必填，L1
  l1_action_level:   ActionLevel | null    // 仅当 l1_subject ∈ {hand, chef} 时必填，否则必须为 null
  l1_action_verb:    ActionVerb | null     // 仅当 l1_action_level ∈ {2, 3} 时必填，否则必须为 null
  l2_dynamics:       L2Item[]              // L2，长度 0..2
  speed_curve:       SpeedCurve | null     // 仅当 mode = keyframes 时必填，否则必须为 null
  seamless_loop:     boolean               // 默认 false
}

L2Item {
  type:    L2Type      // 必填
  target:  string      // 必填，作用对象名词，见 §4.3 校验规则
}
```

### 2.2 输出契约 `PromptResult`

```
PromptResult {
  blocked:          boolean      // true 时禁止提交生成任务
  errors:           Issue[]      // 阻断级问题
  warnings:         Issue[]      // 提示级问题，不阻断
  prompt:           string       // 正向提示词，blocked=true 时为空串
  negative_prompt:  string       // 负向提示词，blocked=true 时为空串
  cfg_scale:        number       // blocked=true 时为 0
}

Issue {
  code:     string    // 如 "V2"、"W1"
  message:  string    // 面向用户的中文说明
  field:    string    // 关联的表单字段名，用于 UI 定位高亮
}
```

---

## 3. 枚举与文案词典

> 所有中文文案为**精确字符串**，实现时需逐字复制。标点使用中文全角（`，`、`；`、`。`），英文镜头术语的括号也使用全角 `（）`。

### 3.1 `Mode`

| 值 | 中文标签 | 说明 |
|---|---|---|
| `single_image` | 单图模式 | 只上传首帧 |
| `keyframes` | 首尾帧模式 | 上传首帧 + 尾帧 |

### 3.2 `CameraMove`

| 值 | UI 标签 | 组装文案 `text` |
|---|---|---|
| `dolly_in` | 缓慢推进 | `缓慢推进（dolly in）` |
| `dolly_out` | 缓慢后拉 | `缓慢后拉（dolly out）` |
| `crane_down` | 缓慢俯视下降 | `缓慢俯视下降（crane down）` |
| `crane_up` | 缓慢上升 | `缓慢上升（crane up）` |
| `truck_left` | 极小幅左横移 | `极小幅左横移（truck left）` |
| `truck_right` | 极小幅右横移 | `极小幅右横移（truck right）` |
| `orbit_right` | 小角度顺时针环绕 | `小角度顺时针环绕（orbit right）` |
| `locked_off` | 固定机位 | `固定机位不动（locked-off）` |

### 3.3 `Amplitude`

| 值 | UI 标签 | 组装文案 `text` |
|---|---|---|
| `subtle` | 极轻微（约8%） | `画面极轻微变化（约8%）` |
| `light` | 轻微（约15%） | `画面轻微变化（约15%）` |
| `medium` | 中等（约25%） | `画面中等变化（约25%）` |

> 上限锁死在 25%。超过此幅度，画面边缘外扩区域由模型凭空补全，崩坏率显著上升。UI 不得提供更高档位。

### 3.4 `Element`（L0 画面元素清单）

用户勾选"这张图里有什么"。字段 `label` 用于拼接【锁定】段。

| 值 | UI 标签 | `label`（用于锁定段） | 可否作为 L1 |
|---|---|---|---|
| `dish_cold` | 菜品主体·冷食 | `菜品` | ✅ |
| `dish_hot` | 菜品主体·热食 | `菜品` | ✅ |
| `garnish` | 配菜／装饰 | `配菜与装饰` | ❌ |
| `tableware` | 餐具器皿 | `餐具器皿` | ✅ |
| `surface` | 桌面／台面 | `桌面` | ❌ |
| `hand` | 手部 | `手部` | ✅ |
| `chef` | 厨师上半身 | `人物` | ✅ |
| `backdrop` | 背景陈设 | `背景陈设` | ❌ |

### 3.5 `L1Subject`

取值为 `Element` 中"可作为 L1"的项，外加 `none`：
`dish_cold` / `dish_hot` / `tableware` / `hand` / `chef` / `none`（纯运镜）

**单图模式下的主运动文案：**

| `l1_subject` | 组装文案 |
|---|---|
| `dish_cold` | `菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移` |
| `dish_hot` | `菜品保持原位不动，仅表面油光随镜头角度缓慢流动` |
| `tableware` | `餐具保持原位不动，仅釉面与金属反光随镜头角度缓慢滑过` |
| `none` | `画面内所有元素保持完全静止，仅视角发生变化` |
| `hand` / `chef` | 由 §3.6 动作幅度模板生成 |

**首尾帧模式下的主运动文案：**

| `l1_subject` | 组装文案 |
|---|---|
| `dish_cold` / `dish_hot` | `菜品位置与形态不变，仅视角与高光从首帧状态连续过渡到尾帧状态` |
| `tableware` | `餐具位置不变，仅反光与视角从首帧状态连续过渡到尾帧状态` |
| `none` | `镜头从首帧机位连续{camera_move.text}至尾帧机位` |
| `hand` / `chef` | 由 §3.6 动作幅度模板生成 |

> **首尾帧模式的核心差异：写"路径"不写"状态"。** 两张图已定义了起点与终点，若提示词再复述端点状态，文字与图像会争夺控制权，典型失败表现为中间闪切。

### 3.6 `ActionLevel`（动作幅度，仅 `hand` / `chef` 激活）

设 `S` = `hand` 时为 `手`，`chef` 时为 `厨师`。设 `V` = `l1_action_verb.text`。

**单图模式：**

| 值 | UI 标签 | 组装文案 |
|---|---|---|
| `1` | 存在感级 | `{S}保持当前姿势与握持关系不变，仅有极轻微自然稳定微动` |
| `2` | 片段级 | `{S}做出{V}的动作片段，动作缓慢连贯，握持关系不变，动作不完成` |
| `3` | 完整级 | `{S}在三秒内缓慢完成一次{V}并自然停住` |

**首尾帧模式：**

| 值 | 组装文案 |
|---|---|
| `1` | `{S}姿态从首帧连续过渡到尾帧，过程中仅有极轻微自然微动` |
| `2` | `{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成{V}的动作片段，中途不停顿、不回退` |
| `3` | `{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成一次{V}，中途不停顿、不回退` |

**面部处理（自动，无 UI）：**
- `l1_subject = chef` → 在主运动文案末尾追加 `，面部表情平静自然，五官稳定`
- `l1_subject = hand` → 无正向追加，但负向追加见 §5.3

### 3.7 `ActionVerb`

| 值 | `text` |
|---|---|
| `sprinkle_seasoning` | `撒落调味` |
| `pour_sauce` | `淋下酱汁` |
| `steady_plate` | `轻扶盘沿` |
| `rotate_plate` | `缓慢转动餐盘` |
| `pick_food` | `夹起食材` |
| `cut_slice` | `切下一刀` |
| `lift_plate` | `端起餐盘` |
| `place_garnish` | `摆放装饰` |

### 3.8 `L2Type`（次级动态）

设 `T` = `l2_item.target`。

| 值 | UI 标签 | 正向文案 | 专属负向词 |
|---|---|---|---|
| `steam` | 热气／蒸汽 | `极轻缓热气自{T}持续缓慢上升，不成团、不遮挡主体` | `浓烟, 白雾遮挡, 云雾成团, 烟雾旋转` |
| `liquid_pour` | 液体·倾倒 | `细流从{T}匀速落下，落点固定，流量恒定` | `飞溅, 液体倒流, 液面暴涨, 外溢, 容器变形, 液体凭空出现` |
| `liquid_ripple` | 液体·晃动 | `{T}表面极轻微晃动，反光随之位移，液面不溢出` | `沸腾, 翻涌, 液面剧烈起伏, 溢出` |
| `flame` | 火焰／炙烤 | `{T}处小簇火焰边缘轻微摇曳，火势范围不变` | `火势蔓延, 冒黑烟, 食材碳化, 焦化加深, 爆燃` |
| `ice_mist` | 冰雾／冷凝 | `极淡冷雾贴{T}表面缓慢流动，冷凝水珠保持附着不滑落` | `水珠滑落, 结霜蔓延, 融化, 白雾弥漫` |
| `specular` | 高光滑移 | `{T}湿润表面高光随镜头角度缓慢滑移` | （无） |
| `fabric_sway` | 织物／植物飘动 | `{T}边缘极轻微自然飘动` | `剧烈飘动, 形变` |
| `person_idle` | 人物微动 | `{T}保持姿态不变，仅极轻微呼吸起伏与自然眨眼` | `五官变形, 手指畸形, 表情夸张, 身体扭曲` |

> **每项自带专属负向词，这是深化的关键。** 通用负向词无法覆盖各类动态各自的翻车方式：蒸汽的翻车是"成团遮挡"，倾倒的翻车是"飞溅倒流"，两者毫无交集。

### 3.9 `SpeedCurve`（仅首尾帧模式）

| 值 | UI 标签 | `text` |
|---|---|---|
| `uniform` | 全程匀速（推荐） | `全程匀速` |
| `ease_in` | 慢起匀速收 | `慢起后转匀速` |
| `ease_out` | 匀速慢收 | `匀速后自然减速` |

默认 `uniform`。匀速的附加价值：3 秒素材裁切到任意时长，切点都不会突兀。

---

## 4. 校验规则

**执行顺序：先跑全部阻断规则，再跑全部提示规则。存在任一阻断规则命中时，`blocked = true`，不生成提示词。**

### 4.1 阻断级（Errors）

| 编码 | 条件 | `message` | `field` |
|---|---|---|---|
| `V1` | `l1_subject != none` 且其对应 `Element` 未在 `elements` 中勾选 | 主运动对象必须先在画面元素中勾选 | `l1_subject` |
| `V2` | `l2_dynamics.length > 2` | 3 秒最多承载 2 个次级动态，超出会导致每项都退化为轻微抖动 | `l2_dynamics` |
| `V3` | 某个 `l2_item.target` 与 L1 对应元素的 `label` 相同 | 次级动态不能指向主运动对象，二者会互相抵消 | `l2_dynamics` |
| `V4` | 同时存在 `flame` 与 `ice_mist` | 火焰与冰雾互斥，不能同时生成 | `l2_dynamics` |
| `V5` | `seamless_loop = true` 且（存在 `liquid_pour` 或 `l1_action_level >= 2`） | 无缝循环要求首尾状态一致，与不可逆动作冲突 | `seamless_loop` |
| `V6` | `l1_action_level != null` 且 `l1_subject ∉ {hand, chef}` | 动作幅度仅适用于手部或厨师主体 | `l1_action_level` |
| `V7` | `mode = keyframes` 且未上传尾帧图 | 首尾帧模式需要上传尾帧图片 | `end_image` |
| `V8` | `mode = single_image` 且 `speed_curve != null` | 速度曲线仅适用于首尾帧模式 | `speed_curve` |
| `V9` | `l2_item.target` 校验失败（见 §4.3） | 作用对象只能填写简短名词 | `l2_dynamics` |
| `V10` | `l1_action_level ∈ {2,3}` 且 `l1_action_verb = null` | 请选择具体动作 | `l1_action_verb` |
| `V11` | `elements.length = 0` | 请至少勾选一项画面元素 | `elements` |
| `V12` | `seamless_loop = true` 且 `camera_move ∉ {truck_left, truck_right, locked_off}` | 无缝循环仅支持极小幅横移或固定机位（推进／后拉无法闭环） | `camera_move` |

### 4.2 提示级（Warnings，不阻断）

| 编码 | 条件 | `message` |
|---|---|---|
| `W1` | 存在 `liquid_pour` 且 `camera_move = dolly_in` | 推进会拉长流体运动路径，飞溅风险较高，建议改用固定机位 |
| `W2` | `mode = single_image` 且 `l1_action_level = 3` | 单图模式下模型需自行编造动作终点，3 秒内成片率较低。建议改用首尾帧模式，由尾帧给定终点 |
| `W3` | `elements.length < 2` | 画面元素勾选过少，锁定层约束偏弱，非主体元素可能出现意外变化 |
| `W4` | `camera_move = locked_off` 且 `camera_amplitude != subtle` | 固定机位下运动幅度设置无效，将被忽略 |
| `W5` | `mode = single_image` 且 `l1_subject = none` 且 `l2_dynamics` 为空 | 当前配置下画面几乎完全静止，生成结果可能接近静态图 |

> **`W2` 是本规格中最重要的引导。** UI 应在此处提供一个"切换到首尾帧模式"的快捷按钮，而不只是文字提示。

### 4.3 `l2_item.target` 校验规则

`target` 是本模块**唯一**的文本输入，必须严格约束：

1. 长度 1–8 个字符（去除首尾空白后计算）
2. 不得包含任何标点符号（全角与半角均禁止）
3. 不得包含条件词：`若` `如果` `则` `当` `存在` `或者` `否则`
4. 不得包含否定词：`不` `无` `没有` `禁止`
5. 不得包含动词性描述——**推荐做法：UI 提供下拉候选（由 `elements` 勾选项的 `label` 自动生成）+「其他」选项才开放输入框**，可将非法输入概率降到最低

违反任一条 → 触发 `V9`。

---

## 5. 组装算法

### 5.1 主流程

```
assemblePrompt(config):
  1. errors   = runBlockingRules(config)
  2. warnings = runWarningRules(config)
  3. if errors 非空:
       return { blocked: true, errors, warnings, prompt: "", negative_prompt: "", cfg_scale: 0 }
  4. lockedSet = computeLockedSet(config)
  5. sections  = buildSections(config, lockedSet)
  6. prompt    = sections.filter(非空).join("\n")
  7. negative  = buildNegative(config)
  8. cfg       = mapCfgScale(config)
  9. return { blocked: false, errors: [], warnings, prompt, negative_prompt: negative, cfg_scale: cfg }
```

### 5.2 `computeLockedSet` — 锁定层推导

```
lockedSet = elements 中所有项的 label 集合
          - L1 对应元素的 label
          - 所有 l2_item.target 命中的 label
去重，按 §3.4 表格中的行顺序排序，用「、」连接
```

> **必须逐个点名，不得使用「其他元素」这类泛指。** 泛指的约束力显著弱于具体名词（`筷子、酱碟、青紫苏叶`）。

### 5.3 `buildSections` — 分段生成

**单图模式（`mode = single_image`）：**

| 段 | 模板 | 省略条件 |
|---|---|---|
| 镜头 | `【镜头】{camera.text}，极慢匀速，单镜头一镜到底，{amplitude.text}。` | 不省略 |
| 镜头（固定机位特例） | `【镜头】固定机位不动（locked-off），画面构图保持不变。` | `camera_move = locked_off` 时改用此句 |
| 主运动 | `【主运动】{l1_text}。` | 不省略 |
| 次级动态 | `【次级动态】{l2_texts.join("；")}，幅度极小，不影响主体形态。` | `l2_dynamics` 为空时**整段删除** |
| 锁定 | `【锁定】{lockedSet}保持绝对静止，位置、数量、形状、颜色不变。` | `lockedSet` 为空时**整段删除** |
| 光线 | `【光线】光源固定，明暗关系不变，无重新打光。` | 不省略 |
| 节奏 | `【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。` | 不省略 |
| 节奏（循环特例） | `【节奏】动作与运镜同步开始，全程匀速连续，首尾画面状态接近，可无缝循环。` | `seamless_loop = true` 时改用此句 |

**首尾帧模式（`mode = keyframes`）：**

| 段 | 模板 | 省略条件 |
|---|---|---|
| 过渡 | `【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。` | 不省略 |
| 主运动 | `【主运动】{l1_text}，{speed_curve.text}。` | 不省略 |
| 次级动态 | `【次级动态】{l2_texts.join("；")}，全程连续不中断。` | `l2_dynamics` 为空时**整段删除** |
| 锁定 | `【锁定】{lockedSet}在整个过渡过程中保持位置与形态不变。` | `lockedSet` 为空时**整段删除** |
| 光线 | `【光线】光源固定，明暗随视角连续渐变，不跳变。` | 不省略 |
| 节奏 | `【节奏】过渡末端稳定停在尾帧状态。` | 不省略 |

> 首尾帧模式**不输出【镜头】段**。镜头运动信息已隐含在两张图的机位差异中，重复声明会与图像冲突。`camera_move` 在此模式下仅用于 `l1_subject = none` 时填充主运动文案。

### 5.4 `buildNegative` — 负向组装

```
negativeParts = BASE
              + (mode = keyframes ? KEYFRAMES_EXTRA : [])
              + (l1_subject = hand ? HAND_EXTRA : [])
              + 每个 l2_item.type 的专属负向词

去重（保持首次出现顺序），用 ", " 连接
```

**`BASE`（恒定）：**
```
变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，涂抹感，二次构图，画质劣化
```

**`KEYFRAMES_EXTRA`：**
```
闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退
```

**`HAND_EXTRA`：**
```
面部入镜，人物面部，全身入镜
```

### 5.5 `mapCfgScale` — 参数映射

> 可灵的 `cfg_scale` 取值 0–1，**方向与直觉相反**：0 为最大创造自由度，1 为严格遵循提示词，默认 0.5。本模块的提示词以"静止／不变／不许"类约束为主，因此静物场景需**调高**才能压住乱动。

| 条件 | `cfg_scale` |
|---|---|
| `mode = keyframes`（任意 L1） | `0.45` |
| `single_image` + `l1_subject ∈ {dish_cold, dish_hot, tableware, none}` | `0.70` |
| `single_image` + `l1_subject ∈ {hand, chef}` + `l1_action_level = 1` | `0.60` |
| `single_image` + `l1_subject ∈ {hand, chef}` + `l1_action_level = 2` | `0.50` |
| `single_image` + `l1_subject ∈ {hand, chef}` + `l1_action_level = 3` | `0.40` |

**取值理由**（供后续调优参考）：
- 静物场景全是约束句，需严格遵循 → 高
- 首尾帧的双图已构成强约束，`cfg` 再调高会与图像打架 → 低
- 完整级动作需要模型自由度去补全中间帧，压太死反而不动 → 最低

> 这五个值是经验起点而非定论。建议上线前每类主体各跑 5 条做 A／B，并把最终值抽成可配置常量而非硬编码。

---

## 6. UI 规格

### 6.1 表单顺序与联动

```
[1] 模式选择          single_image / keyframes
      └ keyframes 时展示尾帧上传区

[2] 画面元素（L0）    多选，至少 1 项
      └ 勾选结果决定 [3] 的可选项，并自动生成 [4] 的 target 候选

[3] 主运动对象（L1）  单选，选项 = [2] 中可作 L1 的项 + "无（纯运镜）"
      └ 选中 hand/chef 时，展开动作幅度三档
            └ 选中 2/3 档时，展开动作词下拉

[4] 次级动态（L2）    多选，上限 2
      └ 每项包含：类型下拉 + 作用对象下拉（候选来自 [2]，含"其他"→输入框）

[5] 镜头运动          单选
      └ single_image 时展示；keyframes 时仅在 L1 = none 时展示

[6] 运动幅度          单选，locked_off 时置灰

[7] 速度曲线          仅 keyframes 展示

[8] 无缝循环          开关，默认关

[9] 锁定层预览        只读，实时显示自动推导结果

[10] 提示词预览       只读，实时显示 prompt / negative_prompt / cfg_scale
```

### 6.2 提示词预览（必做）

用户完成选择后，**实时展示最终组装出的三个值**。这是用户真正需要的"示例"——所见即所提交，且能在提交前发现配置错误。

预览区需支持一键复制。

### 6.3 错误与警告展示

- `errors` → 红色，定位并高亮 `field` 对应控件，**禁用生成按钮**
- `warnings` → 黄色，不禁用生成按钮
- `W2` 需额外渲染「切换到首尾帧模式」按钮，点击后自动切换 `mode` 并保留其余槽位值

---

## 7. 验收测试用例

> 实现完成后，以下 5 个用例必须逐字符匹配通过。

### 用例 1：冷食刺身特写（单图）

**输入**
```
mode: single_image
camera_move: dolly_in
camera_amplitude: light
elements: [dish_cold, garnish, tableware, surface]
l1_subject: dish_cold
l1_action_level: null
l1_action_verb: null
l2_dynamics: []
speed_curve: null
seamless_loop: false
```

**期望 `prompt`**
```
【镜头】缓慢推进（dolly in），极慢匀速，单镜头一镜到底，画面轻微变化（约15%）。
【主运动】菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移。
【锁定】配菜与装饰、餐具器皿、桌面保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。
```

**期望 `cfg_scale`** = `0.70`
**期望 `warnings`** = `[]`
**关键断言**：`l2_dynamics` 为空 → 【次级动态】整段不出现（**不得出现"无次级动态"字样**）

---

### 用例 2：厨师淋酱（首尾帧）

**输入**
```
mode: keyframes
camera_move: locked_off
camera_amplitude: subtle
elements: [dish_hot, tableware, surface, hand]
l1_subject: hand
l1_action_level: 2
l1_action_verb: pour_sauce
l2_dynamics: [
  { type: steam,       target: "菜品" },
  { type: liquid_pour, target: "酱汁壶" }
]
speed_curve: uniform
seamless_loop: false
```

**期望 `prompt`**
```
【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。
【主运动】手连贯自然地从首帧姿态过渡到尾帧姿态，完成淋下酱汁的动作片段，中途不停顿、不回退，全程匀速。
【次级动态】极轻缓热气自菜品持续缓慢上升，不成团、不遮挡主体；细流从酱汁壶匀速落下，落点固定，流量恒定，全程连续不中断。
【锁定】餐具器皿、桌面在整个过渡过程中保持位置与形态不变。
【光线】光源固定，明暗随视角连续渐变，不跳变。
【节奏】过渡末端稳定停在尾帧状态。
```

**期望 `negative_prompt`**
```
变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，涂抹感，二次构图，画质劣化, 闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退, 面部入镜，人物面部，全身入镜, 浓烟, 白雾遮挡, 云雾成团, 烟雾旋转, 飞溅, 液体倒流, 液面暴涨, 外溢, 容器变形, 液体凭空出现
```

**期望 `cfg_scale`** = `0.45`
**关键断言**：`dish_hot` 被 `steam` 的 target 命中 → 不出现在锁定层；`hand` 是 L1 → 不出现在锁定层

---

### 用例 3：俯拍纯运镜（单图）

**输入**
```
mode: single_image
camera_move: crane_down
camera_amplitude: subtle
elements: [dish_cold, garnish, tableware]
l1_subject: none
l2_dynamics: []
seamless_loop: false
```

**期望 `prompt`**
```
【镜头】缓慢俯视下降（crane down），极慢匀速，单镜头一镜到底，画面极轻微变化（约8%）。
【主运动】画面内所有元素保持完全静止，仅视角发生变化。
【锁定】菜品、配菜与装饰、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。
```

**期望 `cfg_scale`** = `0.70`
**期望 `warnings`** = `[W5]`

---

### 用例 4：阻断校验

**输入**
```
mode: single_image
camera_move: dolly_in
camera_amplitude: medium
elements: [dish_hot, tableware]
l1_subject: dish_hot
l2_dynamics: [
  { type: flame,    target: "菜品" },
  { type: ice_mist, target: "餐具器皿" },
  { type: steam,    target: "菜品" }
]
seamless_loop: false
```

**期望输出**
```
blocked: true
errors 包含: V2（超过2项）、V3（flame 的 target 与 L1 相同）、V4（火焰与冰雾互斥）
prompt: ""
negative_prompt: ""
cfg_scale: 0
```

---

### 用例 5：单图完整级动作（触发引导）

**输入**
```
mode: single_image
camera_move: locked_off
camera_amplitude: subtle
elements: [dish_cold, tableware, hand]
l1_subject: hand
l1_action_level: 3
l1_action_verb: pick_food
l2_dynamics: []
seamless_loop: false
```

**期望 `prompt`**
```
【镜头】固定机位不动（locked-off），画面构图保持不变。
【主运动】手在三秒内缓慢完成一次夹起食材并自然停住。
【锁定】菜品、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。
```

**期望 `cfg_scale`** = `0.40`
**期望 `warnings`** = `[W2]`，且 UI 渲染「切换到首尾帧模式」按钮

---

## 8. 调用层对接（现有代码的改动点）

现有 API 调用层**只需三处改动**：

| 编号 | 改动 | 说明 |
|---|---|---|
| `C1` | `cfg_scale` 从硬编码改为接收 `PromptResult.cfg_scale` | 必做。这是本次唯一的必须改动 |
| `C2` | 确认 `negative_prompt` 作为**独立请求字段**传入 | 若当前是拼接进 `prompt`，必须拆开，否则原则 2 失效 |
| `C3` | 确认以下固定参数已正确设置 | 见下表 |

**`C3` 固定参数清单：**

| 参数 | 值 | 说明 |
|---|---|---|
| `duration` | `3` | 可灵 3.0 支持 3–15 秒，取最低档 |
| `mode` | `pro` | 广告切片建议 pro |
| `sound` | `false` | 切片素材不需要音轨 |
| **分镜数** | **`1`** | ⚠️ **必须强制** |
| **智能分镜开关** | **关闭** | ⚠️ **必须强制** |

> **`C3` 中的分镜设置是最容易被忽略的致命项。** 可灵 3.0 新增了多镜头叙事能力（一次最多生成 6 个分镜），若不显式锁死为单分镜，3 秒视频也可能被自动切成 2–3 个镜头——对需要单一连续动作的切片素材而言是直接报废。

**提交前置条件：** `PromptResult.blocked = true` 时，调用层**不得**发起生成请求。

---

## 9. 二期预留

以下不在本次实现范围，但数据模型应预留扩展位。

### 9.1 预设包（Preset）

将常用槽位组合打包为一键按钮。`PromptConfig` 增加可选字段 `preset_id: string | null`，选中预设时批量填充其余字段，填充后用户仍可逐项修改。

候选预设：`刺身冷盘特写` / `热菜出锅` / `淋酱特写` / `倒酒特写` / `炙烤瞬间` / `摆盘手部` / `纯运镜空镜`

### 9.2 智能裁切策略

3 秒素材裁切到 1.5–2.5 秒时，不同 L1 类型需要不同策略：

| L1 类型 | 建议策略 | 理由 |
|---|---|---|
| `dish_*` / `tableware` / `none` | 裁尾，保留 0–1.5s 或 0–2.5s | 匀速光学变化，任意切点都不突兀；可灵末尾 0.3–0.5 秒是画质漂移与形变的高发段 |
| `hand` / `chef` 且 `action_level = 1` | 同上 | 微动无叙事完整性要求 |
| `hand` / `chef` 且 `action_level ∈ {2,3}` | 保留完整 3 秒，或裁到动作自然段落点 | 动作被拦腰截断会导致素材不可用 |

裁切策略应作为 `PromptResult` 的附加输出字段 `suggested_trim`，供后处理模块消费。

---

## 附录 A：给 AI 编程工具的实现禁令

实现过程中，以下行为一律禁止，即使你认为它们能"改善用户体验"：

1. ❌ 在 `prompt` 中加入任务描述、角色设定、元指令（原则 1）
2. ❌ 在 `prompt` 中加入示例或参考描述（原则 1）
3. ❌ 为空槽位生成占位句（如"无次级动态""不含火焰"）——必须整段删除（原则 2）
4. ❌ 把 `negative_prompt` 的内容拼进 `prompt`（原则 2）
5. ❌ 允许 `camera_move` 多选，或允许一次生成两个镜头动作（原则 3）
6. ❌ 放宽 `l2_dynamics` 的 2 项上限（原则 4）
7. ❌ 在提示词中生成任何条件句式（原则 5）
8. ❌ 调整六段的顺序，或合并段落（原则 6）
9. ❌ 新增自由文本输入框（`l2_item.target` 除外，且必须走 §4.3 校验）
10. ❌ 把 `cfg_scale` 继续硬编码

如需违反上述任一条，请先向使用者说明理由并取得确认。
