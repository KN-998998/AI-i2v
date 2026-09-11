#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# macOS / Linux 全量验证脚本
#
# 对应 Windows 的 scripts\verify.bat：前端构建（含 TypeScript 检查）->
# 前端单元测试 -> 后端测试。提交前请先跑通这个脚本。
#
# 兼容 macOS 自带的 bash 3.2：所有变量一律写成 ${VAR}，不使用 compgen。
# ---------------------------------------------------------------------------
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# 后端测试需要的模块（pytest 之外，还要能真正 import 起 web 与 pipeline）
REQUIRED_MODULES="pytest fastapi uvicorn colorama PIL numpy requests urllib3 jwt multipart"

info() { printf '\033[36m[信息]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[注意]\033[0m %s\n' "$*"; }
fail() { printf '\033[31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }
pass() { printf '\033[32m[通过]\033[0m %s\n' "$*"; }

# frontend/node_modules 里的原生依赖是否匹配当前平台，不用 compgen，兼容 bash 3.2
platform_deps_ok() {
  set -- frontend/node_modules/@rollup/rollup-"${PLATFORM}"*
  [ -e "$1" ]
}

# --- 选择 Python 解释器 -----------------------------------------------------
if [ -n "${PYTHON_EXE:-}" ]; then
  :
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "${VIRTUAL_ENV}/bin/python" ]; then
  PYTHON_EXE="${VIRTUAL_ENV}/bin/python"
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "${CONDA_PREFIX}/bin/python" ]; then
  PYTHON_EXE="${CONDA_PREFIX}/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="$(command -v python3)"
else
  fail "未找到 Python，请安装 Python 3.11 或设置环境变量 PYTHON_EXE。"
fi
PYTHON_VERSION="$("${PYTHON_EXE}" -V 2>&1 || echo 'unknown')"
info "使用 Python: ${PYTHON_EXE}  [${PYTHON_VERSION}]"

# --- Python 环境体检（放在最前，别等跑完构建才发现依赖缺失）-----------------
PY_MM="$("${PYTHON_EXE}" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
if [ "${PY_MM}" != "3.11" ]; then
  warn "当前 Python 是 ${PY_MM}，而 CI 和线上容器用的是 3.11。"
  warn "版本不一致时本地通过不代表 CI 通过。建议建专用环境:"
  warn "  conda create -n PY3_11 python=3.11 && conda activate PY3_11"
fi

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

# --- 前端依赖 ---------------------------------------------------------------
command -v node >/dev/null 2>&1 || fail "未找到 node。请安装 Node.js 20 或更高版本。"
command -v npm  >/dev/null 2>&1 || fail "未找到 npm。请安装 Node.js 20 或更高版本。"

PLATFORM="$(node -p 'process.platform + "-" + process.arch')"
if [ ! -d frontend/node_modules ] || ! platform_deps_ok; then
  warn "前端依赖缺失，或与当前平台不匹配（当前平台: ${PLATFORM}）。正在重新安装..."
  rm -rf frontend/node_modules
  (cd frontend && npm install --no-audit --no-fund) || fail "前端依赖安装失败。"
fi

info "1/3 前端构建与 TypeScript 检查"
(cd frontend && npm run build) || fail "前端构建失败。"
pass "前端构建通过"

info "2/3 前端单元测试"
(cd frontend && npm test) || fail "前端单元测试失败。"
pass "前端单元测试通过"

info "3/3 后端测试"
mkdir -p .tmp
"${PYTHON_EXE}" -X utf8 -m pytest || fail "后端测试失败。"
pass "后端测试通过"

echo
pass "全部验证通过，可以提交。"
