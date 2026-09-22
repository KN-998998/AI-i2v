#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# macOS / Linux 本地开发启动脚本
#
# 对应 Windows 的 start_dev.bat：构建前端 -> 启动 FastAPI -> 等待就绪 -> 打开浏览器。
# 用法：
#   ./start_dev.sh              构建前端并启动服务
#   ./start_dev.sh --watch      热更新模式：起 Vite 开发服务器，改前端存盘即刷新
#   ./start_dev.sh --skip-build 跳过前端构建，只启动后端（只改了 Python 时用）
#   ./start_dev.sh --no-open    启动后不自动打开浏览器
#
# 兼容 macOS 自带的 bash 3.2：所有变量一律写成 ${VAR}（bash 3.2 会把紧跟在
# 裸 $VAR 后面的中文字符当成变量名的一部分），空参数时不直接展开 "$@"，
# 也不使用 compgen。
# ---------------------------------------------------------------------------
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SKIP_BUILD=0
OPEN_BROWSER=1
WATCH=0
# Vite 开发服务器端口，要和 frontend/vite.config.ts 里的 DEV_PORT 一致。
DEV_PORT=5174
# bash 3.2 在 set -u 下展开空的 "$@" 行为不一致，所以先判断有没有参数。
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    case "${arg}" in
      --watch)      WATCH=1 ;;
      --skip-build) SKIP_BUILD=1 ;;
      --no-open)    OPEN_BROWSER=0 ;;
      -h|--help)    sed -n '2,11p' "${BASH_SOURCE[0]}"; exit 0 ;;
      *) echo "未知参数：${arg}  可用参数：--watch、--skip-build、--no-open" >&2; exit 2 ;;
    esac
  done
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export APP_HOST="${APP_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-8015}"
export APP_RELOAD="${APP_RELOAD:-true}"

# 启动服务实际需要 import 起来的模块
REQUIRED_MODULES="fastapi uvicorn colorama PIL numpy requests urllib3 jwt multipart"

info() { printf '\033[36m[信息]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[注意]\033[0m %s\n' "$*"; }
fail() { printf '\033[31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

# frontend/node_modules 里的 esbuild / rollup 是按平台编译的原生包。
# 这个函数判断它们是否匹配当前平台，不用 compgen，兼容 bash 3.2。
platform_deps_ok() {
  set -- frontend/node_modules/@rollup/rollup-"${PLATFORM}"*
  [ -e "$1" ]
}

# 构建和热更新都要先有一份匹配当前平台的 node_modules。
ensure_frontend_deps() {
  command -v node >/dev/null 2>&1 || fail "未找到 node。请安装 Node.js 20 或更高版本。"
  command -v npm  >/dev/null 2>&1 || fail "未找到 npm。请安装 Node.js 20 或更高版本。"

  PLATFORM="$(node -p 'process.platform + "-" + process.arch')"
  if [ ! -d frontend/node_modules ]; then
    info "首次运行，正在安装前端依赖..."
    (cd frontend && npm install --no-audit --no-fund) || fail "前端依赖安装失败。"
  elif ! platform_deps_ok; then
    warn "frontend/node_modules 里没有 ${PLATFORM} 平台的原生依赖"
    warn "常见原因: 这份 node_modules 是从 Windows 机器拷贝过来的"
    info "正在重新安装前端依赖..."
    rm -rf frontend/node_modules
    (cd frontend && npm install --no-audit --no-fund) || fail "前端依赖安装失败。"
  fi
}

# --- 1. 选择 Python 解释器 -------------------------------------------------
if [ -n "${PYTHON_EXE:-}" ]; then
  :
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_EXE="${VIRTUAL_ENV}/bin/python"
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "${CONDA_PREFIX}/bin/python" ]; then
  PYTHON_EXE="${CONDA_PREFIX}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
else
  fail "未找到 Python。请安装 Python 3.11，或设置环境变量 PYTHON_EXE 指向解释器。"
fi
PYTHON_VERSION="$("${PYTHON_EXE}" -V 2>&1 || echo 'unknown')"
info "使用 Python: ${PYTHON_EXE}  [${PYTHON_VERSION}]"

# 项目 CI 与线上容器使用 Python 3.11；版本不一致时本地跑通不代表 CI 跑通。
PY_MM="$("${PYTHON_EXE}" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
if [ "${PY_MM}" != "3.11" ]; then
  warn "当前 Python 是 ${PY_MM}，而 CI 和线上容器用的是 3.11。"
  warn "建议建专用环境: conda create -n PY3_11 python=3.11 && conda activate PY3_11"
fi

# 逐个检查缺哪个模块，直接报出来，别让用户自己去猜。
MISSING="$("${PYTHON_EXE}" -c 'import importlib.util as u, sys; print(" ".join(x for x in sys.argv[1:] if u.find_spec(x) is None))' ${REQUIRED_MODULES} 2>/dev/null || echo "__check_failed__")"
if [ -n "${MISSING}" ]; then
  [ "${MISSING}" = "__check_failed__" ] && fail "无法用 ${PYTHON_EXE} 检查依赖，请确认该解释器可用。"
  warn "当前 Python 环境缺少这些模块: ${MISSING}"
  if [ "${CONDA_DEFAULT_ENV:-}" = "base" ]; then
    warn "当前是 conda 的 base 环境，直接往里装依赖可能影响你其他项目。"
    warn "推荐: conda create -n PY3_11 python=3.11 && conda activate PY3_11"
  fi
  fail "请先安装依赖: ${PYTHON_EXE} -m pip install -r requirements.txt"
fi

# --- 2. 检查媒体工具 -------------------------------------------------------
for tool in ffmpeg ffprobe; do
  command -v "${tool}" >/dev/null 2>&1 \
    || warn "未找到 ${tool}，合成与预览会失败。macOS 安装: brew install ffmpeg"
done

# ffmpeg 能不能画字要单独查：片尾卡和字幕都靠 drawtext，而它要编进 libfreetype 才有。
# 2026-09-21 实测 Homebrew 的 ffmpeg 9.0.2 就没编，不查的话要等点「合成此条」才炸。
# 先把滤镜表抓进变量再判断：脚本开着 set -o pipefail，而 `ffmpeg | grep -q` 里 grep
# 一匹配上就关管道，ffmpeg 收到 SIGPIPE，整条管道的返回码变成非 0——照抄那种写法会在
# 明明有 drawtext 的机器上报「不会画字」。
FFMPEG_FILTERS=""
command -v ffmpeg >/dev/null 2>&1 && FFMPEG_FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"
if [ -n "${FFMPEG_FILTERS}" ] && ! printf '%s' "${FFMPEG_FILTERS}" | grep drawtext >/dev/null 2>&1; then
  warn "这台机器的 ffmpeg 不会画字（没有 drawtext 滤镜），片尾卡和字幕都渲染不了。"
  warn "修法: brew install ffmpeg@7 && export PATH=\"/opt/homebrew/opt/ffmpeg@7/bin:\$PATH\"（本机实测 @8 和 9.0.x 都没有 drawtext）"
fi

# --- 3. 前端：热更新 / 生产构建 / 跳过 --------------------------------------
if [ "${WATCH}" -eq 1 ]; then
  info "热更新模式：不做生产构建，稍后启动 Vite 开发服务器"
  ensure_frontend_deps
  if [ "${APP_PORT}" != "8015" ]; then
    warn "APP_PORT 是 ${APP_PORT}，但 vite.config.ts 里的反向代理写死指向 8015"
    warn "热更新模式下请求会转发不到后端；把 vite.config.ts 的 API_TARGET 一起改掉"
  fi
elif [ "${SKIP_BUILD}" -eq 1 ]; then
  info "已跳过前端构建 (--skip-build)"
  [ -f web/static/canvas-app/index.html ] \
    || fail "web/static/canvas-app/ 里没有构建产物，首次启动请不要加 --skip-build。"
else
  ensure_frontend_deps
  info "正在构建前端，含 TypeScript 检查..."
  (cd frontend && npm run build) || fail "前端构建失败，服务未启动。"
fi

# --- 4. 释放端口 -----------------------------------------------------------
if command -v lsof >/dev/null 2>&1; then
  OLD_PIDS="$(lsof -ti "tcp:${APP_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "${OLD_PIDS}" ]; then
    warn "端口 ${APP_PORT} 被下列进程占用，将结束它们:"
    ps -o pid=,command= -p ${OLD_PIDS} 2>/dev/null | sed 's/^/       /' || true
    kill ${OLD_PIDS} 2>/dev/null || true
    sleep 1
    STILL="$(lsof -ti "tcp:${APP_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "${STILL}" ]; then
      kill -9 ${STILL} 2>/dev/null || true
    fi
  fi
fi

# --- 5. 启动 FastAPI -------------------------------------------------------
mkdir -p output logs
info "正在启动 FastAPI: http://${APP_HOST}:${APP_PORT}"
"${PYTHON_EXE}" -X utf8 -m web.run_server &
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT INT TERM

READY=0
for _ in $(seq 1 30); do
  if curl --silent --fail --max-time 2 "http://${APP_HOST}:${APP_PORT}/api/config" >/dev/null 2>&1; then
    READY=1
    break
  fi
  kill -0 "${SERVER_PID}" 2>/dev/null || fail "FastAPI 启动失败，请查看上方报错。"
  sleep 1
done

if [ "${READY}" -ne 1 ]; then
  fail "FastAPI 在 30 秒内没有就绪，请查看上方日志。"
fi

APP_URL="http://${APP_HOST}:${APP_PORT}/"

# --- 6. 热更新模式再起一个 Vite 开发服务器 ----------------------------------
if [ "${WATCH}" -eq 1 ]; then
  info "正在启动 Vite 开发服务器: http://127.0.0.1:${DEV_PORT}"
  (cd frontend && npm run dev) &
  VITE_PID=$!
  trap 'kill ${SERVER_PID} ${VITE_PID} 2>/dev/null || true' EXIT INT TERM
  VITE_READY=0
  for _ in $(seq 1 40); do
    if curl --silent --fail --max-time 2 "http://127.0.0.1:${DEV_PORT}/" >/dev/null 2>&1; then
      VITE_READY=1
      break
    fi
    kill -0 "${VITE_PID}" 2>/dev/null || fail "Vite 开发服务器启动失败，请查看上方报错。"
    sleep 1
  done
  [ "${VITE_READY}" -eq 1 ] || fail "Vite 开发服务器在 40 秒内没有就绪。"
  APP_URL="http://127.0.0.1:${DEV_PORT}/"
fi

info "服务已就绪: ${APP_URL}"
if [ "${OPEN_BROWSER}" -eq 1 ] && command -v open >/dev/null 2>&1; then
  # 打开工作台首页（两条路的入口）；流程画布在侧栏「流程画布总览」里。
  open "${APP_URL}" || true
fi
if [ "${WATCH}" -eq 1 ]; then
  info "改前端文件存盘即刷新；改 .py 后端会自动重启。按 Ctrl+C 一起停掉。"
else
  info "按 Ctrl+C 停止服务。"
fi
trap - EXIT
wait "${SERVER_PID}"
