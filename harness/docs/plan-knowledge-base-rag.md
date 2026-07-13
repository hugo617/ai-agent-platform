# 计划:知识库/RAG(激活 pgvector,文档检索增强 Agent)

> 对应 feature_list.json 的 `id`: `knowledge-base-rag`
> 状态: not_started
> 优先级: 57(V2 大投入)
> 前置: `file-upload-storage`(56,文档上传)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:pgvector 声明了但从没用过,Agent 只能空聊

### 现状(2026-07-12 取证)

- **pgvector 声明**:`requirements.txt:19` 有 `pgvector==0.3.6`;`docker-compose.yml` 用 `pgvector/pgvector:pg16`;`.env.example` 提到 pgvector
- **零使用**:搜 `app/` 的 `embedding|chunk|retriev|knowledge|document|rag|vector` **全是假阳性**(JWTS documents、SSE chunk、AIMessageChunk)。无 embedding 模型、无分块、无检索、无向量列。
- **Agent 工具**:`app/agents/graph.py` 的 `_build_tenant_tools` 只有 `get_my_agents`,无检索工具
- **后果**:Agent 只能基于通用知识聊天,不能查企业知识库(产品手册/FAQ/话术库)。从「能聊」到「懂业务」缺了关键一环。

### 目标

激活 pgvector,实现完整 RAG 管线:
1. 文档上传 → 分块 → embedding → 向量入库
2. Agent 对话时检索相关知识 → 注入 prompt
3. 知识库管理 UI(文档 CRUD + 检索调试)

---

## 前置条件

- `file-upload-storage`(56,文档上传)完成

---

## 实施步骤

### 第一阶段:向量扩展 + 模型

#### Step 1:启用 pgvector 扩展

- **迁移**:`CREATE EXTENSION IF NOT EXISTS vector;`
- **注意**:SQLite 不支持 vector,测试需 mock embedding 或跳过向量测试(用 Postgres 测)
- **检查**:`SELECT * FROM pg_extension` 有 vector

#### Step 2:Document + DocumentChunk 模型

- **新建**(`app/models/knowledge.py`):
  ```python
  class Document(Base):
      __tablename__ = "documents"
      id, tenant_id (FK), name, source_type (upload/text/url),
      content (Text, 原文), file_url (String, 若上传),
      chunk_count (int), status (pending/indexed/failed),
      is_deleted, created_at, updated_at

  class DocumentChunk(Base):
      __tablename__ = "document_chunks"
      id, document_id (FK), tenant_id, chunk_index (int),
      content (Text, 分块文本),
      embedding: Mapped[list[float]] = mapped_column(Vector(1536))  # 维度按 embedding 模型
  ```
- **注册** + **迁移**
- **检查**:`alembic upgrade head && alembic check`(PG)

### 第二阶段:Embedding 管线

#### Step 3:Embedding 服务

- **新建**(`app/services/embedding_service.py`):
  ```python
  class EmbeddingService:
      async def embed(self, texts: list[str]) -> list[list[float]]:
          # 调 embedding 模型(DeepSeek/OpenAI text-embedding-3-small 等)
          # 返回向量列表
  ```
- **配置**(`config.py`):`embedding_model`/`embedding_api_key`/`embedding_base_url`(复用 LLM 配置或独立)
- **维度**:text-embedding-3-small = 1536 维(可配)
- **检查**:输入文本 → 返回向量

#### Step 4:分块 + 索引

- **新建**(`app/services/knowledge_service.py`):
  ```python
  class KnowledgeService:
      async def ingest(self, document_id):
          # 1. 读 document.content
          # 2. 分块(RecursiveCharacterTextSplitter, chunk=500, overlap=50)
          # 3. batch embed
          # 4. 存 DocumentChunk(含 embedding)
          # 5. 更新 document.status = indexed

      async def retrieve(self, query, tenant_id, top_k=4) -> list[str]:
          # 1. embed(query)
          # 2. SELECT content FROM document_chunks
          #    WHERE tenant_id=? ORDER BY embedding <-> query_vec LIMIT top_k
          # 3. 返回最相关 chunks
  ```
- **分块策略**:按字符递归分(LangChain RecursiveCharacterTextSplitter),中文友好
- **检查**:文档上传后 → ingest → chunks 有 embedding;retrieve 返回相关 chunks

### 第三阶段:Agent 检索工具

#### Step 5:retrieve_knowledge 工具

- **改什么**(`app/agents/graph.py` `_build_tenant_tools` 加工具):
  ```python
  @tool
  async def retrieve_knowledge(query: str) -> str:
      """检索知识库找相关信息。用户问业务问题时调用。"""
      chunks = await knowledge_service.retrieve(query, tenant_id, top_k=4)
      if not chunks:
          return "未找到相关知识"
      return "\n---\n".join(chunks)
  ```
- **工具加入 agent**:`_build_tenant_tools` 返回列表加 `retrieve_knowledge`
- **双重校验**:工具内部按 tenant_id 隔离(只检索本租户文档)
- **检查**:Agent 对话问业务问题 → 触发检索 → 回答含知识库内容

#### Step 6:Agent 配置知识库关联

- **改**(`app/models/agent.py` Agent 加字段):`knowledge_base_id`(可空,关联某知识库;NULL=不检索)
- **或**:租户级知识库(所有 Agent 共享本租户文档)
- **检查**:Agent 可配置是否启用 RAG

### 第四阶段:知识库管理 UI

#### Step 7:知识库管理页

- **新建**(`frontend/src/pages/knowledge-page.tsx`):
  - 文档列表(表格:name/状态/chunk 数/时间)
  - 上传文档(FileUpload 组件,依赖 56)→ POST /documents
  - 手动录入文档(textarea)→ POST /documents
  - 删除文档(软删 + 清 chunks)
  - **检索调试**:输入 query → 显示召回的 chunks(高亮 + 相似度分数)→ 验证检索效果
- **侧边栏** + **路由**:`/knowledge`
- **权限**:`require_permission("knowledge", "manage")`(owner/admin)

#### Step 8:后端知识库 API

- **新建**(`app/api/v1/knowledge.py`):
  - `POST /documents`(上传/录入)→ 触发 ingest(异步或同步)
  - `GET /documents`(列表)
  - `DELETE /documents/{id}`
  - `POST /documents/retrieve`(调试检索,body: query → 返回 chunks + 分数)
- **DEFAULT_*_PERMS** 加 `knowledge:manage`(owner/admin)

### 第五阶段:验证

#### Step 9:测试 + 总验证

- **后端**(`tests/test_knowledge_rag.py`,需 PG):
  - 分块正确(边界/overlap)
  - embedding 入库
  - retrieve 返回相关 chunks(cosine 相似度排序)
  - 租户隔离(门店 A 检索不到门店 B 文档)
  - 端到端:上传文档 → Agent 对话问文档内容 → 回答正确
- **命令**:`./init.sh`(SQLite 跳过向量测试)+ PG 手动验证 + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. pgvector 扩展启用;Document + DocumentChunk(含 Vector 列)模型 + 迁移
2. EmbeddingService(embed 文本)+ KnowledgeService(分块/ingest/retrieve)
3. Agent `retrieve_knowledge` 工具 + 租户隔离
4. 知识库管理 UI(文档 CRUD + 检索调试)
5. 端到端:上传文档 → 对话问文档内容 → 回答含知识库信息
6. `./init.sh`(向量测试 PG only)+ `npm run build` + `alembic check`

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| pgvector 生产性能 | 加 ivfflat/hnsw 索引;向量维度选小(1536 或 768) |
| embedding API 成本 | 批量 embed;缓存;可选本地模型 |
| SQLite 不支持 vector | 向量测试标 PG-only(@pytest.mark.pg);SQLite 跳过 |
| 检索质量差 | 调分块大小/overlap;top_k;加重排(rerank,后续) |
| 文档格式(只支持文本/PDF) | MVP 支持纯文本 + PDF;Word/Excel 后续 |

### 不做的事(边界)

- 不做混合检索(向量 + 关键词 BM25,后续)
- 不做 rerank 重排模型(后续)
- 不做多模态 embedding(图片/表格,后续)
- 不做知识图谱

---

## 参考文件

| 参照 | 路径 |
|------|------|
| pgvector 声明 | `requirements.txt:19` + `docker-compose.yml` |
| stream_agent(加检索工具) | `app/agents/graph.py` `_build_tenant_tools` |
| Agent 模型(加 KB 关联) | `app/models/agent.py` |
| 文件上传(前置) | `harness/docs/plan-file-upload-storage.md` |
| 双重校验文档 | `项目指南/02-后端架构/06-权限模型RBAC.md` 双重校验节 |
