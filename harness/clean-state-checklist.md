# 干净状态检查清单(clean-state-checklist)

> 每轮会话结束前逐项确认。**全勾才算留下干净状态。**
> 目的:堵住「假完成」——把「完成」绑定到可执行验证证据,不靠感觉。

---

## 使用方法

会话收尾时(或一个功能做完准备提交时),逐项过一遍。全部打勾 ✅ 才算干净;
有未勾项 → 要么补上,要么在 `progress.md` 里明确记录「为什么没勾、下轮风险」。

**判定原则**:任务通过验证 **且** 本清单全过,两者同时满足才算完成。

---

## 清单(9 项)

- [ ] **基础验证可用**:`./init.sh` 跑过(`ruff check` + `pytest` 全绿)
- [ ] **进度已记录**:`progress.md` 已追加本轮 Session 记录(目标/已完成/验证/下一步)
- [ ] **功能状态真实**:`feature_list.json` 的状态真实反映 passing 和「未验证」的边界
  —— 没跑完整验证的绝不能标 passing(没有假 passing)。多切片 feature **EP2 完成 + 依赖满足(当前 frontier)即 `in_progress`**;EP2 完成但依赖未满足(排队)保持 `not_started` + `plan` 字段已填(区分「已规划待实施」vs plan 为空的「未规划」)
- [ ] **active 视图已同步**:若本期有 feature 状态变化(新增/状态流转/归档),跑过
  `./scripts/sync-active-features.sh` 刷新 `feature_list.active.json`
  —— 漏跑代价:active.json 过时,token 节省失效;**无数据丢失**,agent 兜底可读完整 `feature_list.json`
- [ ] **无半成品**:没有任何已开始但未记录的功能步骤(WIP=1,当前只一个 in_progress)
- [ ] **无调试残留**:没有遗留的 `print()` / `breakpoint()` / `debugger` / 临时文件
- [ ] **遵守架构铁律**:改动符合分层约束(Controller → Service → Repository → Model 单向)、
  多租户过滤在 Repository 层(`TenantScopedRepository`)、软删除带 `is_deleted=False`
- [ ] **可无缝接手**:下一轮会话无需人工修复即可 `./init.sh` 继续工作
- [ ] **切片 checklist 已勾选**:若本次完成(或推进)了某 `plan-<feature>.md` 的切片,
  `/code-review` 通过后、commit 前已把该切片的 acceptance criteria 从 `- [ ]` 改 `- [x]`,
  并在切片标题行追加 `✅ PR #NN commit <hash>`(切片级真相源,见
  [`docs/three-tier-workflow.md`](docs/three-tier-workflow.md) §4/§5)。**末切片完成时,另跑 feature 收尾仪式**(evidence + status=passing + sync)

---

## 如果某项没勾怎么办

| 没勾的项 | 处理方式 |
|---------|---------|
| 基础验证失败 | **先修基础**,不要在坏起点上提交。修不了就在 progress.md 标 blocker。 |
| 进度没记录 | 现在就补 Session 记录,别指望下轮还记得。 |
| 状态不真实 | 把没跑完验证的功能从 passing 改回 in_progress 或 not_started。 |
| active 视图未同步 | 跑 `./scripts/sync-active-features.sh`。不跑也不会丢数据(agent 兜底读完整版),但下轮开工 token 节省失效。 |
| 有半成品 | 要么推到 passing,要么明确记录「做到哪、差什么」。 |
| 有调试残留 | 现在删掉。`git diff` 检查一遍。 |
| 违反铁律 | 回退改动,重走分层。铁律见 `AGENTS.md`。 |
| 不可接手 | 把「下轮需要手动做什么」写进 progress.md 的风险段。 |
| 切片 checklist 未勾 | 现在就勾(`/code-review` 通过的切片 acceptance criteria 改 `- [x]` + 标题追加 `✅ PR #NN commit`)。不勾 = 切片状态真相源失真,下轮 agent 会误判进度。 |

---

## 与其他 harness 工件的关系

- **`./init.sh`**:本清单第 1 项的执行入口
- **`progress.md`**:本清单第 2、8 项的落点
- **`feature_list.json`**:本清单第 3、4 项的真相源(完整版,CI/审计用)
- **`feature_list.active.json`**:本清单第 4 项的刷新对象(派生视图,agent 开工读)
- **`AGENTS.md` 的铁律**:本清单第 7 项的判定依据
