# AI 引流视频批量生产流水线（餐饮品牌）

## 项目结构
- `pipeline/` — 核心代码（6 个 Step 脚本 + 配置 + 入口）
- `_archive/` — 历史文档/旧脚本（本地保留，不入仓库）
- `output/` — 批量生产输出（按批次日期分目录）
- 素材库：本地路径，通过 `pipeline/config.py` 环境变量 `IMAGE_LIBRARY` 配置

## 核心规则
1. Pipeline：菜品图片 → 可灵 Kling 2.6 图生视频 → ffmpeg 合成 → AI 配音配乐
2. 素材主库：`IMAGE_LIBRARY`（按菜名分文件夹）
3. 生产规模：每天 ~10 条，混合模式（不同菜品组合 + 同菜变体）
4. 人工环节：仅 Step 4 片段审核
5. 面向非技术运营/品牌部：交付中文说明文档，代码供技术侧维护

## 工作流 Step
1. **Step 1** — 菜品清单 → 素材库找图 → 9:16/1080p 预处理（Pillow）
2. **Step 2** — DeepSeek 生成图生视频提示词 + 字幕文案
3. **Step 3** — Kling 2.6 API 批量图生视频（4-5s/无声/9:16，每菜 3 roll）
4. **Step 4** — 生成 HTML 审核页 + CSV 清单（人工挑选）
5. **Step 5** — ffmpeg 掐头去尾 + 硬切拼接 + 字幕 + CTA → 无声成片
6. **Step 6** — DeepSeek 文案 + edge-tts 配音 + 固定 BGM → 最终有声成片

## API Key 配置
```bash
set DEEPSEEK_API_KEY=sk-xxxx          # Step 2 + Step 6
set KLING_API_KEY=xxxx                # Step 3
```

## Git 推送授权
- 代码改动完成并经过审查后，若未发现重大泄露风险（例如 API Key、`.env`、隐私数据、大型素材库、批量输出成片等不应入仓内容），授权 Agent 直接提交并推送到当前项目已配置的远程分支，无需用户再次手动确认。
- 如平台或沙箱权限机制强制要求确认，仍按平台权限流程执行。

## 运行
```bash
python pipeline/run_batch.py --config pipeline/batch_template.yaml
```
