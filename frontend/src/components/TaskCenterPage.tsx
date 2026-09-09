import { isActiveTaskStatus } from "../api";
import { navigate } from "../router";
import { nodeCatalog, type ComposeJob, type NodeKind, type TaskStatus, type WorkflowNode } from "../model";
import { useWorkflowStore } from "../workflowStore";

type TaskRow = {
  id: string;
  kind: NodeKind | "compose";
  title: string;
  status: TaskStatus;
  stage: string;
  detail: string;
  route: "/workflow/image-processing" | "/workflow/generator" | "/workflow/compose" | "/workflow/sound" | "/workflow/output";
};

const statusLabels: Record<TaskStatus, string> = {
  queued: "排队中",
  running: "处理中",
  polling: "等待平台结果",
  downloading: "下载中",
  analyzing: "质量分析中",
  retrying: "等待重试",
  done: "已完成",
  error: "失败",
};

export function TaskCenterPage({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const clipsLastLoadedAt = useWorkflowStore(state => state.clipsLastLoadedAt);
  const clipsLoadError = useWorkflowStore(state => state.clipsLoadError);
  const tasks = buildTaskRows(nodes, workspaces);
  const activeCount = tasks.filter(task => isActiveTaskStatus(task.status)).length;
  const errorCount = tasks.filter(task => task.status === "error").length;
  const doneCount = tasks.filter(task => task.status === "done").length;

  return <main className="main-column task-center-page">
    <div className="task-center-hero">
      <div>
        <span className="panel-label">TASK CONTROL CENTER</span>
        <h1>任务中心</h1>
        <p>集中查看图片处理、Kling 生成、片段评分、成片合成和最终输出的当前状态。</p>
      </div>
      <div className="task-hero-actions"><span className={`task-sync-pill ${clipsLoadError ? "error" : clipsLastLoadedAt ? "ready" : ""}`}>{clipsLoadError ? "片段库同步异常" : clipsLastLoadedAt ? `片段库已同步 · ${new Date(clipsLastLoadedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}` : "片段库等待首次同步"}</span><button type="button" className="btn" onClick={() => navigate("/canvas-mvp")}>回到流程画布</button></div>
    </div>

    <div className="task-summary-grid">
      <SummaryCard label="进行中" value={String(activeCount)} tone="active" hint="正在执行或等待外部平台" />
      <SummaryCard label="已完成" value={String(doneCount)} tone="done" hint="可以继续下一步操作" />
      <SummaryCard label="需要处理" value={String(errorCount)} tone="error" hint="请检查错误并重新执行" />
    </div>

    <section className="task-center-panel">
      <div className="panel-section-head"><div><span className="panel-label">WORKFLOW TASKS</span><h2>所有任务</h2><p className="muted">任务状态会随着后台阶段变化更新；失败任务不会自动重新创建 Kling 外部任务。</p></div><span className="task-count-pill">{tasks.length} 个记录</span></div>
      {clipsLoadError && <div className="task-inline-warning">片段库同步失败：{clipsLoadError}</div>}
      {tasks.length === 0 ? <div className="task-empty"><strong>当前没有运行中的任务</strong><span>从素材与菜品开始，或进入流程画布查看各节点状态。</span><button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/assets")}>开始添加素材</button></div> : <div className="task-list">{tasks.map(task => <TaskRowCard key={task.id} task={task} onToast={onToast} />)}</div>}
    </section>

    <section className="task-center-panel task-lifecycle-panel"><div className="panel-section-head"><div><span className="panel-label">LIFECYCLE</span><h2>任务阶段说明</h2></div></div><div className="task-lifecycle"><LifecycleItem status="queued" label="排队" /><LifecycleItem status="running" label="处理" /><LifecycleItem status="polling" label="轮询" /><LifecycleItem status="downloading" label="下载" /><LifecycleItem status="analyzing" label="评分入库" /><LifecycleItem status="done" label="完成" /></div><p className="muted">本地下载、质量评分和合成失败会按任务策略有限重试；外部 Kling 任务不会被重复提交。</p></section>
  </main>;
}

function SummaryCard({ label, value, tone, hint }: { label: string; value: string; tone: string; hint: string }) {
  return <div className={`task-summary-card ${tone}`}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>;
}

function TaskRowCard({ task, onToast }: { task: TaskRow; onToast: (message: string) => void }) {
  const active = isActiveTaskStatus(task.status);
  return <article className={`task-row-card ${task.status}`}><div className="task-row-icon">{task.kind === "compose" ? "合" : task.kind === "generator" ? "K" : task.kind === "image_process" ? "图" : "出"}</div><div className="task-row-main"><div className="task-row-title"><strong>{task.title}</strong><span className={`task-status-badge ${task.status}`}>{statusLabels[task.status]}</span></div><p>{task.stage}</p><small>{task.detail}</small></div><div className="task-row-actions"><button type="button" className="btn" onClick={() => navigate(task.route)}>{task.kind === "compose" ? "查看合成" : "查看节点"}</button>{task.status === "error" && <button type="button" className="btn btn-danger" onClick={() => onToast("请回到对应页面重新执行任务")}>处理失败</button>}{active && <span className="task-live-dot">实时</span>}</div></article>;
}

function LifecycleItem({ status, label }: { status: TaskStatus; label: string }) {
  return <div className={`lifecycle-item ${status}`}><span className="lifecycle-dot" /><strong>{label}</strong><small>{statusLabels[status]}</small></div>;
}

function buildTaskRows(nodes: WorkflowNode[], workspaces: Array<{ id: string; title: string; job: ComposeJob | null; finalJob?: ComposeJob | null }>): TaskRow[] {
  const rows: TaskRow[] = [];
  nodes.forEach(node => {
    if (node.data.kind === "image_process" && (node.data.imageProcessingJobId || /处理中|处理失败|已处理/.test(node.data.status))) {
      const status: TaskStatus = /失败/.test(node.data.status) ? "error" : /已处理/.test(node.data.status) ? "done" : "running";
      rows.push({ id: `image:${node.id}`, kind: "image_process", title: node.data.title, status, stage: status === "done" ? "首帧处理和质量分析已完成" : status === "error" ? "图片处理失败，请检查素材或背景模板" : "正在执行抠图、背景合成和质量分析", detail: node.data.dishName || "等待素材信息", route: "/workflow/image-processing" });
    }
    if (node.data.kind === "generator" && /生成中|生成失败|已生成/.test(node.data.status)) {
      const status: TaskStatus = /失败/.test(node.data.status) ? "error" : /已生成/.test(node.data.status) ? "done" : "polling";
      rows.push({ id: `generator:${node.id}`, kind: "generator", title: node.data.title, status, stage: status === "done" ? "视频已下载并完成本地质量评分" : status === "error" ? "Kling 任务失败，请检查提示词和素材" : "Kling 正在生成，后台会自动轮询并下载", detail: `${node.data.dishName || "未命名菜品"} · ${node.data.duration || "3s"}`, route: "/workflow/generator" });
    }
  });
  workspaces.forEach(workspace => {
    addComposeRow(rows, workspace.id, workspace.title, workspace.job, false);
    addComposeRow(rows, workspace.id, workspace.title, workspace.finalJob ?? null, true);
  });
  return rows.sort((left, right) => Number(isActiveTaskStatus(right.status)) - Number(isActiveTaskStatus(left.status)));
}

function addComposeRow(rows: TaskRow[], id: string, title: string, job: ComposeJob | null, final: boolean) {
  if (!job) return;
  rows.push({ id: `${final ? "final" : "compose"}:${id}:${job.job_id}`, kind: "compose", title: `${title}${final ? " · 有声成片" : " · 无声成片"}`, status: job.status, stage: job.stage || (job.status === "done" ? "成片已输出" : job.status === "error" ? "成片合成失败" : "正在合成片段和音轨"), detail: `${job.timeline_count} 个片段${job.include_sound ? " · 已包含 BGM、人声和文字" : " · 等待声音与文字"}`, route: final ? "/workflow/sound" : "/workflow/compose" });
}
