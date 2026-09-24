# OSS 素材抽取接入说明

## 已实现的链路

`POST /api/jobs` 接收：

```json
{
  "selections": [
    {"category": "寿司", "count": 3},
    {"category": "主菜", "count": 2}
  ],
  "seed": 123
}
```

任务在后台依次执行：

1. 从配置的 OSS 前缀列出分类和直接菜品子目录；
2. 每个分类随机抽取指定数量的不同菜品目录；
3. 每个菜品目录随机选择一张支持的图片；
4. 下载到 `JOB_TEMP_DIR/<job_id>/source/`；
5. 用现有成片分辨率配置转换为 1080×1920（9:16）JPEG；
6. 进入 `awaiting_review`，等待人工确认。

查询任务：

```text
GET  /api/oss/diagnostics
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/approve
POST /api/jobs/{job_id}/regenerate   {"asset_id": "asset_001"}
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/assets/{asset_id}/normalized
```

`regenerate` 会记录单个素材需要重新生成的审查决定；实际 Kling 片段仍由现有画布生成接口提交，避免 OSS 适配层直接耦合具体节点。

## ECS 配置

ECS 实例绑定只读 RAM 角色，角色策略只允许目标 Bucket 下素材前缀的 `ListObjects` 和 `GetObject`。不要把 AK/SK 写入 `.env`、代码或 Git。

`.env` 只配置非敏感项：

```text
OSS_BUCKET=your-bucket
OSS_ENDPOINT=https://oss-cn-shenzhen.aliyuncs.com
OSS_ASSET_PREFIX=<实际素材前缀>
OSS_REGION=cn-shenzhen
OSS_ALLOWED_CATEGORIES=寿司,主菜,甜品
JOB_TEMP_DIR=output/oss_jobs
```

部署前先调用 `/api/oss/diagnostics`。只有当 `layout_ready=true` 且每个分类的 `dish_folder_count` 满足业务数量时，才允许开始生产。当前控制台中的素材如果是“单个文件夹直接放图片”，不满足本项目的分类/菜品目录规则，需要先整理成：

```text
<前缀>/<分类>/<菜品>/<图片>
```

OSS 对象 key 使用 `/`，Windows 本地临时目录才使用系统路径格式。未配置 `OSS_BUCKET` 或 `OSS_ENDPOINT` 时，任务会进入失败状态，不会回退到任意公网 URL。

## 资源和安全边界

- 默认单个生成任务并发数为 1；由 `OSS_MAX_CONCURRENT_JOBS` 控制。
- 分类数、每类图片数、总图片数和单图大小均有上限。
- `/api/jobs` 按客户端 IP 做进程内提交限流；公网部署仍应在云防火墙或 WAF 层继续限流。
- 服务端不会向浏览器返回 RAM 凭证或 OSS 签名 URL。
- 原始 OSS 图片只下载到任务临时目录，不会回写 OSS。
- 任务进入终态超过 `OSS_JOB_RETENTION_HOURS` 后，服务启动时自动清理临时目录和任务清单。
- 任务完成前不会进入视频生成，人工审查是明确的状态门禁。

## 验证

在 ECS 上配置 RAM 角色和 `.env` 后，先调用：

```powershell
Invoke-RestMethod http://127.0.0.1:8015/api/oss/categories
```

然后提交最小任务并轮询 `/api/jobs/{job_id}`。应确认：分类数量不足会失败、同一分类的菜品名不重复、标准化图片为 1080×1920，并且 RAM 角色无法上传或删除对象。
