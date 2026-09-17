import type { MouseEvent, ReactNode } from "react";
import { workflowStep, type WorkflowRoute } from "../router";

export function formatNodeValue(value: unknown, fallback = "待配置") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function Row({ label, value }: { label: string; value: string }) {
  return <div className="node-row"><span className="node-label">{label}</span><span className="node-value">{value}</span></div>;
}

export function Tag({ children, good = false, warn = false }: { children: string; good?: boolean; warn?: boolean }) {
  return <span className={`tag ${good ? "good" : ""} ${warn ? "warn" : ""}`}>{children}</span>;
}

export function Footer({ children }: { children: ReactNode }) {
  return <div className="node-footer">{children}</div>;
}

export function ActionButton({ children, onClick, primary = false, disabled = false, title }: { children: ReactNode; onClick: () => void; primary?: boolean; disabled?: boolean; title?: string }) {
  return <button className={`btn nodrag nopan ${primary ? "btn-primary" : ""}`} type="button" disabled={disabled} title={title} onClick={(event: MouseEvent<HTMLButtonElement>) => { event.stopPropagation(); onClick(); }}>{children}</button>;
}

/** 步骤页统一标题：「第 N 步 · 名称」+ 一句“这一步做什么、做完得到什么”。 */
export function StepHeading({ route }: { route: WorkflowRoute }) {
  const step = workflowStep(route);
  if (!step) return null;
  return <div><h1>第 {step.step} 步 · {step.label}</h1><p className="step-goal"><strong>这一步做什么：</strong>{step.goal}</p></div>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <div className="section-title">{children}</div>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Select({ value, options, onChange }: { value: string; options: string[]; onChange: (value: string) => void }) {
  return <select className="input" value={value} onChange={event => onChange(event.target.value)}>{options.map(option => <option key={option}>{option}</option>)}</select>;
}
