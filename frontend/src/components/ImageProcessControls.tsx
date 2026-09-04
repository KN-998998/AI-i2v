import type { WorkflowData } from "../model";
import { Field } from "./ui";

type ImageProcessSetting = {
  key: "backgroundBlur" | "backgroundBrightness" | "subjectScale" | "subjectX" | "subjectY";
  label: string;
  help: string;
  min: number;
  max: number;
  step: number;
  fallback: number;
};

const SETTINGS: ImageProcessSetting[] = [
  { key: "backgroundBlur", label: "背景虚化", help: "0 为清晰，24 为最强；只处理背景模板。", min: 0, max: 24, step: 1, fallback: 4 },
  { key: "backgroundBrightness", label: "背景亮度", help: "1 为原始亮度；数值越小，背景越暗。", min: 0.35, max: 1, step: 0.05, fallback: 0.72 },
  { key: "subjectScale", label: "菜品大小", help: "按画面占比缩放，最高不会超过画面高度的 72%。", min: 0.2, max: 1, step: 0.05, fallback: 0.68 },
  { key: "subjectX", label: "水平位置", help: "0.5 为居中；数值越大，菜品越靠右。", min: 0.05, max: 0.95, step: 0.05, fallback: 0.5 },
  { key: "subjectY", label: "垂直位置", help: "0.5 为居中；数值越大，菜品越靠下。", min: 0.05, max: 0.95, step: 0.05, fallback: 0.58 },
];

function normalise(value: number, setting: ImageProcessSetting) {
  return Math.min(setting.max, Math.max(setting.min, value));
}

export function ImageProcessControlFields({ data, update }: { data: WorkflowData; update: (patch: Partial<WorkflowData>) => void }) {
  const preserveOriginal = data.processingMode === "preserve_original" || data.visualSubjectType === "手部" || data.visualSubjectType === "厨师上半身" || data.visualSubjectType === "手部+厨师上半身";
  if (preserveOriginal) return <div className="preview-box"><strong>保留原图动作路线</strong><span>该素材包含{data.visualSubjectType}，生成时会保留人物、手部和原始环境，不执行 GoodsMatting，也不替换背景模板。请在提示词节点选择具体动作。</span></div>;
  const setValue = (setting: ImageProcessSetting, rawValue: number) => {
    const value = Number.isFinite(rawValue) ? normalise(rawValue, setting) : setting.fallback;
    update({ [setting.key]: value } as Partial<WorkflowData>);
  };

  return <>{SETTINGS.map(setting => {
    const rawValue = data[setting.key];
    const value = typeof rawValue === "number" ? normalise(rawValue, setting) : setting.fallback;
    return <Field key={setting.key} label={`${setting.label} (${setting.min}-${setting.max})`}>
      <div className="image-process-control">
        <input className="range" aria-label={setting.label} type="range" min={setting.min} max={setting.max} step={setting.step} value={value} onChange={event => setValue(setting, Number(event.target.value))} />
        <input className="input image-process-value" aria-label={`${setting.label}数值`} type="number" min={setting.min} max={setting.max} step={setting.step} value={value} onChange={event => setValue(setting, Number(event.target.value))} />
      </div>
      <small className="field-help">{setting.help}</small>
    </Field>;
  })}</>;
}
