#!/usr/bin/env bash
# init.sh —— 标准化启动 + 验证入口(Harness Stage 1)
# --------------------------------------------------------------------------
# agent 每轮会话开工和收尾都跑它。设计目标:在裸环境也能跑起来、快、失败可见。
#
# 它做三件事:
#   1. 装后端依赖(requirements-dev.txt,含 pytest/ruff + typer/rich/click)
#   2. 跑基础验证(ruff check + pytest,SQLite 内存库,不依赖 docker/postgres)
#   3. 打印启动指引(不自动启动,除非 RUN_START_COMMAND=1)
#
# 为什么只跑后端快速验证:
#   - pytest 用 SQLite 内存库(conftest.py 自动 setdefault 测试环境),秒级、无需外部服务
#   - agent 每轮都跑,必须快且能在裸环境跑起来
#   - 前端验证(npm run build)、完整迁移验证(需真实 Postgres)用单独命令,见文末启动指引
# --------------------------------------------------------------------------
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# 标准化命令
# INSTALL_CMD 用 bash 数组(单条命令,安全处理参数)。
# 验证是两条命令用 && 串联,数组无法承载 shell 控制操作符,所以 VERIFY 用字符串 + bash -c。
INSTALL_CMD=(pip install -r requirements-dev.txt)
VERIFY_CMD="ruff check app/ cli/ tests/ scripts/ alembic/ && pytest -ra --strict-markers"

echo "==> 当前目录: $PWD"

# ---- 0. 激活虚拟环境(若存在)----
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "==> 已激活虚拟环境: $(which python)"
else
  echo "==> ⚠️ 未找到 .venv/。建议先创建:"
  echo "    python -m venv .venv && source .venv/bin/activate"
  echo "    (继续用当前 python: $(which python))"
fi

# ---- 1. 同步依赖 ----
echo "==> [1/2] 同步依赖: ${INSTALL_CMD[*]}"
"${INSTALL_CMD[@]}"

# ---- 2. 运行基础验证 ----
echo "==> [2/2] 运行基础验证: ruff check + pytest"
# VERIFY_CMD 是含 && 的字符串,用 bash -c 执行
bash -c "$VERIFY_CMD"

# ---- 3. 打印启动指引 ----
echo ""
echo "=== ✅ 基础验证通过(ruff + pytest 全绿)==="
echo ""
echo "==> 启动完整应用(需 docker 提供 Postgres + Logto):"
echo "    docker-compose up -d            # 起 PostgreSQL(pgvector)+ Logto"
echo "    alembic upgrade head            # 建表/迁移"
echo "    uvicorn app.main:app --reload   # 启动后端 → http://localhost:8000/docs"
echo "    python scripts/init_admin.py    # 创建首个本地超管(首次运行)"
echo "    cd frontend && npm install && npm run dev  # 启动前端 → http://localhost:3000"
echo ""
echo "==> 完整验证(非 init.sh 职责,按需手动跑):"
echo "    alembic upgrade head && alembic check   # 迁移链(需真实 Postgres)"
echo "    cd frontend && npm run build            # 前端类型检查 + 构建"
echo ""
if [ "${RUN_START_COMMAND:-0}" = "1" ]; then
  echo "==> RUN_START_COMMAND=1,启动后端(需先 docker-compose up + alembic upgrade)"
  exec uvicorn app.main:app --reload
fi
echo "完成。若要直接启动后端:RUN_START_COMMAND=1 ./init.sh"
