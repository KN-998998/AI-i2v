import { useEffect, useMemo, useRef, useState } from "react";
import { navigate } from "../router";
import { dismissTutorial, TUTORIAL_VERSION, tutorialChapters, type TutorialChapter } from "../tutorial";

type Props = { open: boolean; startIndex: number; onClose: () => void; onDismiss: () => void };

export function TutorialModal({ open, startIndex, onClose, onDismiss }: Props) {
  const [index, setIndex] = useState(startIndex);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) { setIndex(Math.min(Math.max(startIndex, 0), tutorialChapters.length - 1)); window.setTimeout(() => closeButtonRef.current?.focus(), 0); } }, [open, startIndex]);
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); if (event.key === "ArrowRight") setIndex(value => Math.min(value + 1, tutorialChapters.length - 1)); if (event.key === "ArrowLeft") setIndex(value => Math.max(value - 1, 0)); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);
  if (!open) return null;
  const chapter = tutorialChapters[index];
  const isLast = index === tutorialChapters.length - 1;
  const isIntro = chapter.kind === "welcome" || chapter.kind === "project";
  const stepNumber = chapter.kind === "workflow-step" ? index - 1 : undefined;
  const goNext = () => { if (isLast) onClose(); else setIndex(value => Math.min(value + 1, tutorialChapters.length - 1)); };
  const goChapter = (chapterItem: TutorialChapter) => { const nextIndex = tutorialChapters.findIndex(item => item.id === chapterItem.id); if (nextIndex >= 0) setIndex(nextIndex); };
  return <div className="tutorial-layer" role="presentation"><button className="tutorial-backdrop" type="button" aria-label="关闭教程" onClick={onClose} /><section className="tutorial-modal" role="dialog" aria-modal="true" aria-labelledby="tutorial-title"><header className="tutorial-head"><div><span className="panel-label">AI VIDEO WORKFLOW · TUTORIAL</span><h2 id="tutorial-title">{chapter.title}</h2></div><button ref={closeButtonRef} type="button" className="tutorial-close" onClick={onClose} aria-label="关闭教程">×</button></header><div className="tutorial-body"><nav className="tutorial-index" aria-label="教程章节"><div className="tutorial-index-title">教程目录 <small>{index + 1} / {tutorialChapters.length}</small></div>{tutorialChapters.map((item, itemIndex) => <button type="button" key={item.id} className={`tutorial-index-item ${itemIndex === index ? "active" : ""} ${item.kind === "workflow-step" ? "step-item" : ""}`} onClick={() => goChapter(item)}><span>{item.kind === "workflow-step" ? itemIndex - 1 : itemIndex === 0 ? "•" : itemIndex === tutorialChapters.length - 1 ? "✓" : "i"}</span><strong>{item.title}</strong></button>)}</nav><main className="tutorial-content"><div className={`tutorial-visual ${chapter.id === "step-4" ? "tutorial-visual-tall" : ""}`}>{chapter.screenshot ? <img src={`${import.meta.env.BASE_URL}tutorial/${chapter.screenshot}?v=${TUTORIAL_VERSION}`} alt={`${chapter.title} 页面截图`} /> : <div className="tutorial-welcome-visual"><span className="tutorial-welcome-mark">✦</span><strong>{isIntro ? "从素材到成片" : "制作完成"}</strong><small>{chapter.description}</small></div>}</div><div className="tutorial-copy"><span className="tutorial-eyebrow">{chapter.eyebrow}{stepNumber !== undefined ? ` · STEP ${stepNumber + 1}` : ""}</span><p className="tutorial-description">{chapter.description}</p><ul>{chapter.bullets.map(bullet => <li key={bullet}>{bullet}</li>)}</ul>{chapter.checkpoint && <div className="tutorial-callout success"><strong>完成标准</strong><span>{chapter.checkpoint}</span></div>}{chapter.warning && <div className="tutorial-callout warning"><strong>注意</strong><span>{chapter.warning}</span></div>}</div></main></div><footer className="tutorial-footer"><button type="button" className="tutorial-dismiss" onClick={() => { dismissTutorial(); onDismiss(); }}>不再提醒</button><div className="tutorial-footer-actions"><button type="button" className="btn" disabled={index === 0} onClick={() => setIndex(value => Math.max(value - 1, 0))}>上一步</button>{chapter.route && <button type="button" className="btn" onClick={() => { navigate(chapter.route!); onClose(); }}>进入本步骤</button>}<button type="button" className="btn btn-primary" onClick={goNext}>{isLast ? "开始使用" : "下一步"}</button></div></footer></section></div>;
}

export function useTutorialStartIndex(route: string): number {
  return useMemo(() => tutorialChapters.findIndex(chapter => chapter.route === route) >= 0 ? tutorialChapters.findIndex(chapter => chapter.route === route) : 1, [route]);
}
