# 计划:文件上传 + 对象存储抽象(头像/照片/文档,本地/S3/OSS 可切)

> 对应 feature_list.json 的 `id`: `file-upload-storage`
> 状态: not_started
> 优先级: 56
> 前置: 无(本任务是地基,被 user-profile 49/tenant-branding 52/knowledge-base-rag 57 依赖)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:无上传能力,Customer.avatar 是死字段

### 现状

- 搜 `UploadFile|multipart|FormData|.filename` 在 `app/` **零命中**——无上传端点
- 无 S3/OSS/blob 配置
- `Customer.avatar`(`String(255)`)是死字段,无上传路径填充
- 无 Agent avatar 字段

### 地位:多个功能的地基

被依赖:
- user-profile(49)头像上传
- tenant-branding(52)logo 上传
- knowledge-base-rag(57)文档上传

### 目标

1. 存储抽象层(LocalStorage / AmazonS3 / AliyunOSS,config 切换)
2. 上传端点(POST /upload,multipart,大小/类型限制)
3. 前端上传组件

---

## 前置条件

- 无。

---

## 实施步骤

### 第一阶段:存储抽象层

#### Step 1:StorageBackend 抽象

- **新建**(`app/core/storage.py`):
  ```python
  class StorageBackend(ABC):
      @abstractmethod
      async def save(self, file: UploadFile, key: str) -> str:  # 返回访问 URL
          ...
      @abstractmethod
      async def delete(self, key: str): ...

  class LocalStorage(StorageBackend):
      """本地磁盘(dev)。存到 /uploads/,通过 /static 访问。"""
      async def save(self, file, key):
          path = UPLOAD_DIR / key
          async with aiofiles.open(path, "wb") as f:
              await f.write(await file.read())
          return f"/static/{key}"

  class AmazonS3Storage(StorageBackend):
      """S3(生产)。boto3 异步上传。"""
      async def save(self, file, key): ...

  class AliyunOSSStorage(StorageBackend):
      """阿里云 OSS(生产)。oss2 库。"""
      ...
  ```
- **配置**(`app/core/config.py`):
  ```python
  storage_backend: str = "local"  # local / s3 / oss
  storage_local_dir: str = "uploads"
  s3_bucket: str | None = None
  s3_region: str | None = None
  oss_bucket: str | None = None
  oss_endpoint: str | None = None
  ```
- **工厂**:`get_storage() -> StorageBackend`(按 config 返回实例)
- **检查**:local 后端能存文件返回 URL

### 第二阶段:上传端点

#### Step 2:POST /upload

- **新建**(`app/api/v1/uploads.py`):
  ```python
  @router.post("/upload")
  async def upload_file(user: CurrentUser, file: UploadFile = File(...)):
      # 校验:类型(image/*, application/pdf, text/*) + 大小(≤ 10MB)
      if file.content_type not in ALLOWED_TYPES:
          raise HTTPException(400, "file type not allowed")
      if file.size > MAX_SIZE:
          raise HTTPException(413, "file too large")
      # 生成 key:tenant_id/user_id/uuid.ext
      key = f"{user.tenant_id}/{uuid.uuid4().hex}.{ext}"
      url = await get_storage().save(file, key)
      return {"url": url, "key": key}
  ```
- **权限**:登录即可(有 user);可按用途细分(avatar/document)
- **静态文件服务**(`app/main.py`):mount `/static` → 本地 uploads 目录(local 模式)
- **检查**:上传图片返回 URL;访问 URL 能取到文件

#### Step 3:文件校验 + 安全

- **类型白名单**:image/png, image/jpeg, image/webp, application/pdf, text/plain
- **大小限制**:10MB(可配)
- **文件名安全**:用 uuid 生成 key,不用原文件名(防路径穿越)
- **检查**:非法类型 → 400;超大 → 413

### 第三阶段:前端上传组件

#### Step 4:通用上传组件

- **新建**(`frontend/src/components/ui/file-upload.tsx`):
  - FileInput + 拖拽区 + 预览(图片缩略图)+ 进度条
  - 调 `/upload` 端点(multipart FormData)
  - 返回 url 给父组件
- **检查**:组件可复用;上传显示进度;返回 url

#### Step 5:接入消费方

- **user-profile(49)**:头像上传 → 调 FileUpload → 返回 url → 存 User.avatar_url
- **tenant-branding(52)**:logo 上传 → 同理 → TenantConfig.logo_url
- **检查**:各消费方接入(可在各自任务做,本任务只提供组件)

### 第四阶段:验证

#### Step 6:测试 + 总验证

- **后端**(`tests/test_upload.py`):
  - 上传图片 → 返回 url → 访问 200
  - 类型校验(非法 → 400)
  - 大小校验(超大 → 413)
  - 存储后端切换(local;mock s3)
  - 权限(需登录)
- **命令**:`./init.sh` + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. StorageBackend 抽象(Local/S3/OSS)+ config 切换
2. `POST /upload`(multipart,类型/大小校验,uuid key 防穿越)
3. /static 静态服务(local 模式)
4. 前端 FileUpload 组件(拖拽 + 预览 + 进度)
5. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 本地存储生产不可用 | 抽象层 + config 切换;生产配 S3/OSS |
| 文件名路径穿越 | uuid 生成 key,不用原文件名 |
| 恶意文件上传 | 类型白名单 + 大小限制 + (可选)杀毒扫描 |
| S3/OSS 凭证管理 | 从环境变量读;不入库 |

### 不做的事(边界)

- 不做断点续传(后续)
- 不做图片处理(压缩/裁剪/水印,后续)
- 不做 CDN(生产部署层)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| config | `app/core/config.py` |
| app 启动(mount /static) | `app/main.py` |
| Customer.avatar(死字段,待激活) | `app/models/customer.py` L74 |
| 前端组件目录 | `frontend/src/components/ui/` |
