// ---------------------------------------------------------------------------
// 第 3 步「动态效果」。
//
// 改这一页的起因（Patrick 2026-09-21 第一次从头走一道菜）：原来页面上只有一张所有菜
// 共用的「基础提示词模板」卡片，写着「已装配 · L0 5」「实时装配」，看不出这是给哪道菜
// 的，也看不出视频会怎么动，效果全藏在「编辑节点」的侧栏里。
//
// 现在每道菜一张卡片，用第 2 步的首帧把「镜头怎么走、哪里在动、哪里不动」画出来，
// 效果由 effectRules.ts 按这道菜的冷热自动选好，不合适再点一个换。
// ---------------------------------------------------------------------------
import { assemblePrompt, availablePromptPresets, CAMERA_OPTIONS, L2_OPTIONS, matchPromptPreset, PROMPT_PRESETS, type PromptConfig, type PromptPresetId } from "../promptAssembler";
import { DEFAULT_EFFECT_RULES, EFFECT_CLASS_LABELS, EFFECT_COPY, effectClassFor, effectivePromptConfig, effectReason, effectRuleOverridden, presetForDish, type EffectClass, type EffectRules } from "../effectRules";
import { promptAssemblyBlockReason, promptUpstreamNodes } from "../promptAssemblyReadiness";
import type { WorkflowData } from "../model";
import { useWorkflowStore } from "../workflowStore";
import { navigate } from "../router";
import { StepNext } from "./StepPages";

const PRESET_LABELS: Record<PromptPresetId, string> = Object.fromEntries(PROMPT_PRESETS.map(preset => [preset.id, preset.label])) as Record<PromptPresetId, string>;

/** 卡片上的状态只给一个短说法，长句留给鼠标悬停；卡片一行放不下整句校验原因。 */
function shortBlockReason(reason: string): string {
  if (reason.includes("原始图片")) return "待上传原图";
  if (reason.includes("图片处理失败")) return "图片处理失败";
  if (reason.includes("图片处理")) return "待图片处理";
  if (reason.includes("素材节点")) return "待连接素材";
  if (reason.includes("提示词校验")) return "效果配不出来";
  return "待处理";
}

/** 批量规则面板里「原图有手或厨师」那一格：写清楚人是不动的，不然运营会以为手会动。 */
function ruleLabel(klass: EffectClass, presetId: PromptPresetId): string {
  if (klass === "person" && presetId === "glow") return "人保持姿势，只动高光";
  return PRESET_LABELS[presetId];
}

/**
 * 首帧上那三行图例（镜头 / 在动 / 不动）。
 * 有对得上的效果就用它那份大白话；在高级设置里手调到对不上任何效果时，退回按配置
 * 里的镜头名称和次级动态名称拼一行——宁可说得干一点，也不能什么都不写。
 */
function legendFor(config: PromptConfig, copy: { camera: string; moving: string; still: string } | null) {
  if (copy) return copy;
  const camera = CAMERA_OPTIONS.find(item => item.value === config.camera_move)?.label ?? "固定机位";
  const moving = config.l2_dynamics.map(item => L2_OPTIONS.find(option => option.value === item.type)?.label ?? item.type).join("、");
  return { camera, moving: moving || "只有镜头在动", still: "画面里其余部分" };
}

/**
 * 首帧上叠的示意图：环绕画弧线箭头，推近画四角向内的箭头，热气画几道波浪线，
 * 高光滑移画两颗小星。都是静态 SVG，动的那部分交给外面那层 CSS 循环动画。
 */
function EffectOverlay({ config }: { config: PromptConfig }) {
  const steam = config.l2_dynamics.some(item => item.type === "steam");
  const specular = config.l2_dynamics.some(item => item.type === "specular");
  return <svg className="effect-overlay" viewBox="0 0 540 960" preserveAspectRatio="none" aria-hidden="true">
    <defs><marker id="effect-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#ffffff" /></marker></defs>
    {config.camera_move === "orbit_right" && <path d="M 70 640 A 210 78 0 1 0 470 610" fill="none" stroke="#ffffff" strokeWidth="5" strokeDasharray="14 10" markerEnd="url(#effect-arrow)" opacity=".95" />}
    {config.camera_move === "dolly_in" && <g fill="none" stroke="#ffffff" strokeWidth="4" opacity=".85">
      <rect x="40" y="70" width="460" height="818" rx="10" strokeDasharray="12 10" />
      <path d="M46 76 l46 46 M494 76 l-46 46 M46 882 l46 -46 M494 882 l-46 -46" strokeWidth="5" strokeLinecap="round" />
    </g>}
    {steam && <g fill="none" stroke="#ffffff" strokeWidth="5" strokeLinecap="round" opacity=".9">
      <path d="M110 360 c-22 -30 22 -52 0 -84 c-20 -30 18 -50 2 -80" />
      <path d="M175 350 c-22 -30 22 -52 0 -84 c-20 -30 18 -50 2 -80" />
      <path d="M240 360 c-22 -30 22 -52 0 -84 c-20 -30 18 -50 2 -80" />
    </g>}
    {specular && <g fill="#fff8d6" opacity=".95">
      <path d="M200 505 l6 16 l16 6 l-16 6 l-6 16 l-6 -16 l-16 -6 l16 -6z" />
      <path d="M300 492 l4 11 l11 4 l-11 4 l-4 11 l-4 -11 l-11 -4 l11 -4z" />
    </g>}
  </svg>;
}

export function EffectStepPage({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const edges = useWorkflowStore(state => state.edges);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const beginNodeEdit = useWorkflowStore(state => state.beginNodeEdit);
  const setDishEffect = useWorkflowStore(state => state.setDishEffect);
  const resetPromptEffect = useWorkflowStore(state => state.resetPromptEffect);

  // 一道菜 = 一个提示词节点。卡片要显示的首帧、菜名、冷热都在它上游的图片处理和素材节点上。
  const dishes = nodes.filter(node => node.data.kind === "prompt").map((prompt, index) => {
    const { process, input } = promptUpstreamNodes(prompt, nodes, edges);
    const inputData: Partial<WorkflowData> = input?.data ?? {};
    const reason = promptAssemblyBlockReason(prompt, nodes, edges);
    return {
      index: index + 1,
      prompt,
      process,
      inputData,
      reason,
      name: inputData.dishName || prompt.data.title || "未命名菜品",
      preview: process?.data.processedImagePreview || inputData.imagePreview,
      config: effectivePromptConfig(prompt.data, inputData),
    };
  });
  const readyCount = dishes.filter(dish => dish.reason === null).length;
  const current = dishes.find(dish => dish.prompt.id === selectedNodeId) ?? dishes[0];

  if (!current) {
    return <div className="step-page-grid"><div className="step-page-main">
      <section className="step-panel empty-panel">
        <h2>还没有菜品</h2>
        <p>先去第 1 步上传菜品图，工具会按冷热自动配好每道菜的动态效果。</p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/assets")}>去第 1 步上传菜品图</button>
      </section>
    </div></div>;
  }

  const rules: EffectRules = (current.prompt.data.effectRules ?? {}) as EffectRules;
  const custom = current.prompt.data.effectMode === "custom";
  const dishClass = effectClassFor(current.inputData.foodType, current.inputData.visualSubjectType);
  const activePreset: PromptPresetId | null = custom
    ? matchPromptPreset(current.config)
    : presetForDish(current.inputData.foodType, current.inputData.visualSubjectType, rules);
  const copy = activePreset ? EFFECT_COPY[activePreset] : null;
  const legend = legendFor(current.config, copy);
  const reasonText = effectReason(current.prompt.data, current.inputData);
  const presets = availablePromptPresets(current.config);
  const tags = [current.inputData.dishCategory, current.inputData.foodType || "未标冷热"].filter(Boolean);
  const person = current.inputData.visualSubjectType && current.inputData.visualSubjectType !== "菜品主体";
  const personTag = person ? (current.inputData.visualSubjectType === "厨师上半身" ? "原图有厨师" : "原图有手") : null;
  // 镜头怎么走就让首帧怎么动：环绕小幅左右摆，推近缓慢放大，其余不动。
  const animation = current.config.camera_move === "orbit_right" ? "effect-anim-orbit"
    : current.config.camera_move === "dolly_in" ? "effect-anim-dolly"
    : "";
  const backToImages = () => {
    if (current.process) setSelection(current.process.id);
    navigate("/workflow/image-processing");
  };
  const chooseEffect = (presetId: PromptPresetId) => {
    setDishEffect(current.prompt.id, presetId);
    onToast(`已把${EFFECT_CLASS_LABELS[dishClass]}的效果改成「${PRESET_LABELS[presetId]}」，这一页和批量里的${EFFECT_CLASS_LABELS[dishClass]}都会用它`);
  };

  return <div className="step-page-grid"><div className="step-page-main">
    <section className="step-panel image-process-node-overview">
      <div className="panel-section-head">
        <div><h2>菜品 · {dishes.length} 道</h2><p className="muted">点一张卡片，看这道菜会怎么动。</p></div>
        <span className="image-process-queue-count">{readyCount}/{dishes.length} 已配好</span>
      </div>
      <div className="image-process-node-grid effect-dish-grid">{dishes.map(dish => {
        const dishPreset = dish.prompt.data.effectMode === "custom"
          ? matchPromptPreset(dish.config)
          : presetForDish(dish.inputData.foodType, dish.inputData.visualSubjectType, (dish.prompt.data.effectRules ?? {}) as EffectRules);
        const dishPerson = dish.inputData.visualSubjectType && dish.inputData.visualSubjectType !== "菜品主体";
        const dishTags = [dish.inputData.dishCategory, dish.inputData.foodType || "未标冷热"].filter(Boolean);
        if (dishPerson) dishTags.push(dish.inputData.visualSubjectType === "厨师上半身" ? "原图有厨师" : "原图有手");
        return <button type="button" key={dish.prompt.id} className={"image-process-node-card effect-dish-card" + (dish.prompt.id === current.prompt.id ? " selected" : "")} onClick={() => setSelection(dish.prompt.id)}>
          {dish.preview ? <img className="effect-dish-thumb" src={dish.preview} alt="" /> : <span className="effect-dish-thumb effect-dish-thumb-empty">未上传</span>}
          <div className="effect-dish-body">
            <div className="effect-dish-head">
              <span className="node-record-index">{String(dish.index).padStart(2, "0")}</span>
              <strong>{dish.name}</strong>
              <span className={"node-status" + (dish.reason === null ? " is-ok" : "")} title={dish.reason ?? "已配好"}>{dish.reason === null ? "已配好" : shortBlockReason(dish.reason)}</span>
            </div>
            <span className="effect-dish-tags">{dishTags.join(" · ")}</span>
            <span className="effect-meta-name">{dishPreset ? <>{PRESET_LABELS[dishPreset]} <em>· {effectReason(dish.prompt.data, dish.inputData)}</em></> : effectReason(dish.prompt.data, dish.inputData)}</span>
          </div>
        </button>;
      })}</div>
    </section>

    <section className="step-panel ip-studio effect-studio">
      <div className="ip-preview">
        <div className="ip-preview-head"><h2>{current.name} 会这样动</h2><span className="ip-live is-live">按这个效果循环示意</span></div>
        <div className="ip-preview-frame effect-frame">
          {current.preview
            ? <img className={animation} src={current.preview} alt={`${current.name} 的首帧`} />
            : <em>这道菜还没有首帧，先到第 2 步做一次图片处理</em>}
          {current.preview && <EffectOverlay config={current.config} />}
          {current.preview && <span className="ip-frame-tag">第 2 步的首帧</span>}
          {current.preview && <div className="effect-legend">
            <div><b>镜头</b>{legend.camera}</div>
            <div><b>在动</b>{legend.moving}</div>
            <div><b>不动</b>{legend.still}</div>
          </div>}
        </div>
        <div className="ip-preview-foot">
          <button type="button" className="link-button" onClick={backToImages}>画面要改（背景、大小、位置）回第 2 步</button>
        </div>
      </div>
      <div className="ip-controls">
        <p className="effect-dish-line">{[current.name, ...tags].join(" · ")}{personTag ? ` · ${personTag}` : ""}</p>
        <h2 className="effect-title">{activePreset ? PRESET_LABELS[activePreset] : "手调的效果"}<span className="effect-auto-tag">{reasonText}</span></h2>
        {custom
          ? <p className="effect-plain">这道菜用的是在高级设置里手调的效果。<button type="button" className="link-button" onClick={() => { resetPromptEffect(current.prompt.id); onToast(`${current.name} 已改回按冷热自动选`); }}>改回自动</button></p>
          : <p className="effect-plain">{copy ? copy.sentence(current.name) : `镜头${legend.camera}，在动的是${legend.moving}。`}</p>}
        <div className="ip-divider" />
        <h3 className="effect-sub">换一个效果<small>这道菜能用的 {presets.length} 个</small></h3>
        <div className="prompt-preset-grid effect-presets">{presets.map(preset => <button type="button" key={preset.id} className={`prompt-preset ${activePreset === preset.id ? "active" : ""}`} aria-pressed={activePreset === preset.id} onClick={() => chooseEffect(preset.id)}>
          {activePreset === preset.id && <span className="effect-auto-mini">{!custom && !effectRuleOverridden(rules, dishClass) ? "自动选的" : "当前"}</span>}
          <strong>{preset.label}</strong>
          <small>{preset.description}</small>
        </button>)}</div>
        <details className="effect-more">
          <summary>看给 AI 的完整指令<small>一般不用看，想知道 AI 收到了什么时再点开</small></summary>
          <pre className="effect-instruction">{assemblePrompt(current.config).prompt}</pre>
          <p className="effect-instruction-note">指令里没有菜名：可灵是看着左边这张首帧生成的，指令只管「怎么动」。</p>
        </details>
        <details className="effect-more">
          <summary>自己调镜头和动作（高级）<small>原来的全部选项都在这里</small></summary>
          <div className="effect-advanced-open">
            <button type="button" className="btn" onClick={() => beginNodeEdit(current.prompt.id)}>打开高级设置</button>
            <span className="muted">逐项调镜头、画面元素和动作；调过之后这道菜就不再跟着冷热规则变。</span>
          </div>
        </details>
      </div>
    </section>

    <section className="step-panel effect-batch-rule">
      <div>
        <h2>批量生产时，每道菜按这个规则自动配</h2>
        <p className="muted">你在上面给某道菜换了效果，批量里同一类的菜也会跟着换。在高级设置里手调的只管那一道菜。</p>
      </div>
      <dl className="effect-rule-list">{(Object.keys(EFFECT_CLASS_LABELS) as EffectClass[]).map(klass => {
        const presetId = rules[klass] ?? DEFAULT_EFFECT_RULES[klass];
        return <div key={klass}><dt>{EFFECT_CLASS_LABELS[klass]}</dt><dd>{ruleLabel(klass, presetId)}</dd></div>;
      })}</dl>
    </section>

    <div className="step-context">
      <div className="step-summary">
        <strong>{readyCount === dishes.length ? `${dishes.length} 道菜都已配好` : `还有 ${dishes.length - readyCount} 道菜没配好`}</strong>
        <p>本页修改会自动保存到同一份画布草稿。</p>
      </div>
      <StepNext route="/workflow/prompts" />
    </div>
  </div></div>;
}
