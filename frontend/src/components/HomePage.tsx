import { navigate, workflowRoutes } from "../router";
import { useWorkflowStore } from "../workflowStore";
import { deriveWorkflowProgress, firstIncompleteWorkflowRoute } from "../workflowProgress";

/**
 * 工作台首页。
 *
 * 这个工具其实有两条路：用一道菜把背景、动态效果和字幕调成样板（1–7 步），
 * 以及按样板批量生产（选素材库 → 确认分类 → 自动抠图/生成/选片/合成 → 审片）。
 * 以前打开直接落在流程画布上，两条路都没说，批量入口还藏在侧栏第四项。
 * 这一页只做一件事：把这两条路摆到明面上，并让人能接着上次继续。
 */
export function HomePage() {
  const nodes = useWorkflowStore(state => state.nodes);
  const edges = useWorkflowStore(state => state.edges);
  const candidateClips = useWorkflowStore(state => state.candidateClips);
  const workspaces = useWorkflowStore(state => state.composeWorkspaces);
  const lastSavedAt = useWorkflowStore(state => state.lastSavedAt);
  const progress = deriveWorkflowProgress(nodes, candidateClips, workspaces, edges);
  const resumeRoute = firstIncompleteWorkflowRoute(progress);
  const resumeStep = workflowRoutes.find(item => item.path === resumeRoute);
  const dishes = nodes
    .filter(node => node.data.kind === "input")
    .map(node => node.data.dishName)
    .filter((name): name is string => Boolean(name && name.trim()));
  // 只有真的上传过菜品图才提示"继续上次"，空草稿不打扰。
  const canResume = progress.steps[0].complete && dishes.length > 0;
  const savedAt = lastSavedAt
    ? new Date(lastSavedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "";
  return <main className="step-main home-page">
    <h1>把菜品照片，变成能直接发布的竖版短视频</h1>
    <p className="home-lead">先用<strong>一道菜把样板调好</strong>，之后<strong>按样板批量生产</strong>：抠图、生成、选片、合成全部自动，你只需要确认素材分类和审片。</p>
    <div className="home-entries">
      <section className="home-entry">
        <h2>精修一道菜，调样板</h2>
        <p>上传一张菜品图，走完六步，把背景、动态效果和字幕调到满意。这套设置会保存为样板。</p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/assets")}>开始调样板</button>
      </section>
      <section className="home-entry">
        <h2>按样板批量生产</h2>
        <p>选一个素材库和数量，工具自动抽菜、抠图、生成、选片、合成；你只需要确认分类和审片。</p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/weekly-plan")}>开始批量生产</button>
      </section>
    </div>
    {canResume && <div className="home-resume">
      <div>
        <strong>继续上次：{dishes[0]}{dishes.length > 1 ? ` 等 ${dishes.length} 道菜` : ""}</strong>
        <span>停在第 {resumeStep?.step} 步 · {resumeStep?.label}{savedAt ? ` · ${savedAt} 自动保存` : ""}</span>
      </div>
      <button type="button" className="btn" onClick={() => navigate(resumeRoute)}>继续</button>
    </div>}
    <div className="home-links">
      <button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>查看完整流程图</button>
      <button type="button" className="link-button" onClick={() => navigate("/workflow/tasks")}>任务中心</button>
      <button type="button" className="link-button" onClick={() => navigate("/workflow/asset-library-review")}>整理素材库</button>
    </div>
  </main>;
}
