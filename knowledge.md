# PostgreSQL 16 + pgvector 详解

> 📌 **这份文档的定位**:这是独立的 **pgvector 背景知识**参考资料,不属于
> [`项目指南/`](项目指南/) 文档体系。项目当前(pgvector 已就位、RAG 尚未启用)
> 还没实际使用向量检索;等做 RAG 向量检索时,这里是前置知识储备。
> 想了解项目整体架构,看 [`项目指南/README.md`](项目指南/README.md)。

## 一、pgvector 是什么
**pgvector 是 PostgreSQL 的开源扩展插件**，专门给原生PostgreSQL增加**向量数据库能力**，让普通PG直接能存向量、做向量相似度检索，不用额外部署Milvus、Chroma、Pinecone这类独立向量库。

简单一句话：**给PostgreSQL装上向量检索功能**。

## 二、核心能干什么
1. **新增向量类型**
新增 `vector(n)` 数据类型，n代表向量维度（比如Embedding常用1536维、768维、512维），直接在表字段里存AI生成的Embedding向量。
```sql
-- 建表示例，存储1536维文本向量
CREATE TABLE doc_embedding (
  id bigint primary key,
  content text,
  embedding vector(1536)
);
```

2. **内置相似度计算算子**
开箱即用三种主流向量距离算法，用于RAG知识库检索、语义匹配、图片特征比对：
| 运算符 | 算法 | 适用场景 |
|--------|------|----------|
| `<->` | L2欧氏距离 | 最常用，距离越小越相似 |
| `<#>` | 负内积 | OpenAI embedding推荐 |
| `<=>` | 余弦相似度 | 文本语义检索主流 |

```sql
-- 查和目标向量最相似的前5条数据
SELECT * FROM doc_embedding
ORDER BY embedding <=> '[0.1,0.2,...]'::vector(1536)
LIMIT 5;
```

3. **支持向量索引加速**
数据量大了之后全表扫描很慢，pgvector支持两种索引大幅提速检索：
- `ivfflat`：倒排索引，适合百万级数据，构建快
- `hnsw`：层级导航小世界索引，千万级向量、查询性能更强（PG16搭配体验最佳）

```sql
-- 创建HNSW余弦相似度索引
CREATE INDEX idx_embedding ON doc_embedding USING hnsw (embedding vector_cosine_ops);
```

## 三、为什么搭配 PostgreSQL 16
1. PG16 性能、并发、WAL日志、分区表、并行查询做了大幅优化，承载向量写入+查询稳定性更好；
2. pgvector 对新版PostgreSQL兼容性更好，PG14/15/16都支持，16是目前生产环境很稳妥的版本；
3. 可以**一份数据库搞定结构化业务数据 + 向量知识库**，不用维护两套存储，简化运维。

## 四、典型使用场景
- **RAG检索增强生成**：大模型知识库，文本向量化存入PG，提问时向量召回相关上下文再喂给LLM
- 图片/音频特征存储与以图搜图
- 推荐系统、用户特征相似度匹配
- 企业内部文档、工单、知识库语义搜索

## 五、安装极简说明
1. 先装好PostgreSQL16
2. 编译/包管理器安装 `pgvector` 扩展
3. 进入数据库执行开启扩展：
```sql
CREATE EXTENSION vector;
```
之后就能直接使用vector类型和向量检索语法。

## 优缺点
✅ 优点：
- 复用现有PG生态：事务、主键、索引、备份、权限、分库分表、JOIN联查（业务字段+向量一起筛选）
- 无额外中间件，架构极简
- 支持ACID，向量数据不会丢，支持增删改查事务

❌ 缺点：
- 百亿级超大向量库，性能不如专用分布式向量数据库（Milvus、Qdrant）
- 高并发海量向量写入场景不如专用库专一