# 04 - 实战走读:用户管理 CRUD 是怎么跑通的

📍 相关文档:[01-分层架构](../02-后端架构/01-分层架构与依赖方向.md) · [04-TanStack Query](../03-前端架构/04-数据获取TanStackQuery.md) · [06-权限模型 RBAC](../02-后端架构/06-权限模型RBAC.md)

> 这一篇带你「从零看懂」用户管理页面是怎么实现的。把你当完全的新手——不需要你已经读过
> 其他文档,但假设你知道这个项目是「FastAPI 后端 + React 前端」。
>
> 读完后你会知道:**当你在「用户管理」页面点了「新增用户」,这个动作是怎么一路传到
> 数据库、又怎么把新用户渲染到表格里的。**每一跳对应哪段代码,在哪一行。

---

## 先看全貌:一次「新增用户」的完整旅程

不用记住下面所有细节,先有个「哦,原来是这么几跳」的感觉就行:

```
你在页面点「新增用户」按钮 (前端 React)
  │
  │  ① 前端:按钮 → 表单 → hook → API 函数
  ▼
发起 HTTP 请求: POST /api/v1/users/ (带 JSON 数据)
  │
  │  ② 后端:路由 → 权限校验 → Service → Repository
  ▼
写入数据库: INSERT INTO users ... (PostgreSQL)
  │
  │  ③ 返回:数据库 → ORM 对象 → JSON 响应
  ▼
前端收到响应 → 自动刷新列表 → 表格里出现新用户
```

**一共涉及 3 个世界、7 层代码**。别怕,我们一层一层拆。每层只做一件事,职责单一。

| 层 | 在哪 | 干什么 | 类比 |
|----|------|--------|------|
| 数据库 | PostgreSQL | 存数据 | 仓库 |
| Model | `app/models/tenant.py` | 描述表长什么样 | 仓库货架的图纸 |
| Repository | `app/repositories/` | 拼装 SQL、读写数据库 | 仓库管理员 |
| Service | `app/services/user_service.py` | 业务逻辑(校验、权限、组合步骤) | 业务经理 |
| Schema | `app/schemas/user.py` | 校验入参、定义返回格式 | 收发货清单 |
| Controller/路由 | `app/api/v1/users.py` | 接 HTTP 请求,调 Service | 前台接待 |
| 前端 | `frontend/src/` | 界面、发请求、展示数据 | 顾客看到的店面 |

> 💡 **核心铁律:依赖单向流动**。前端 → 路由 → Service → Repository → Model → 数据库。
> **绝对不能反过来**(比如 Repository 去调 Service)。每一层只认识下一层,不认识上一层。
> 详见 [01-分层架构](../02-后端架构/01-分层架构与依赖方向.md)。

---

## 第一站:数据库与 Model(数据长什么样)

### 数据库表

用户数据主要在两张表里(数据库是 PostgreSQL 16):

```
users 表          ——  存用户的基本资料(用户名、邮箱、密码哈希、状态…)
  └─ user_tenants 表  ——  存「哪个用户在哪个租户里是什么角色」(多租户的关键)
```

为什么分两张?因为这是**多租户 SaaS**:同一个用户(比如张三)可以属于多个租户,在每个
租户里的角色不同(在 A 公司是 admin,在 B 公司是 member)。所以「角色」不能放在 `users`
表里,要放在 `user_tenants` 这张「关系表」里。

### Model:用 Python 描述表结构

ORM(Object-Relational Mapping)就是「用 Python 类描述数据库表」。看代码:

**文件:`app/models/tenant.py`**

```python
class User(Base):                          # ← 第 43 行
    __tablename__ = "users"                 # 对应数据库里的 users 表

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)  # bcrypt 哈希,不是明文!
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_deleted: Mapped[bool] = mapped_column(default=False)  # 软删除标记
    # ... 还有 display_name / real_name / phone / avatar / created_at 等
```

> 🔑 **关键:密码不是明文存的**。`password` 字段存的是 **bcrypt 哈希**(一种不可逆的加密)。
> 所以即使数据库泄露,黑客也拿不到原始密码。详见 [05-认证体系](../02-后端架构/05-认证体系.md)。

> 🗑️ **关键:软删除**。删除用户不是真的 `DELETE FROM users`(那样数据就没了),而是把
> `is_deleted` 改成 `True`。查询时永远带 `WHERE is_deleted = False`,所以用户「看不见」了,
> 但数据还在,需要时能恢复。

### Model 和数据库怎么同步?

用 **Alembic** 迁移工具。改了 Model 后,跑 `alembic revision --autogenerate` 生成迁移脚本,
再跑 `alembic upgrade head` 应用到数据库。详见 [03-数据库与ORM](../02-后端架构/03-数据库与ORM.md)。

---

## 第二站:Schema(收发货清单)

Schema 用 **Pydantic** 定义,负责两件事:**校验前端传来的数据对不对** + **定义返回给前端的数据长什么样**。

**文件:`app/schemas/user.py`**

```python
class UserCreate(BaseModel):                # ← 第 52 行,「创建用户」的入参清单
    username: str = Field(..., min_length=2, max_length=50)   # 必填,2-50 字符
    email: EmailStr                          # 必填,且必须是合法邮箱格式
    password: str = Field(..., min_length=6)  # 必填,至少 6 位
    role: str = Field(default="member")       # 可选,默认 member
    status: str = "active"                    # 可选,默认 active
    # ...

class UserRead(BaseModel):                  # ← 第 29 行,返回给前端的格式
    id: str
    username: str | None = None
    email: str | None = None
    role: RoleBrief | None = None            # 角色是一个嵌套对象 {id, name, code}
    # ...
    # 注意:没有 password 字段!密码永远不会返回给前端
```

> 💡 **Schema 的魔法**:FastAPI 拿到前端 POST 来的 JSON,会自动用 `UserCreate` 校验。
> 如果邮箱格式不对、密码太短,**FastAPI 直接返回 422 错误**,根本不用你写校验代码。
> 同理,返回时用 `UserRead` 过滤——`password` 不在里面,所以绝不会泄露。

---

## 第三站:Repository(仓库管理员,拼装 SQL)

Repository 层直接操作数据库,把「业务需求」翻译成「SQL 查询」。用户管理有两个 Repository:

- **`UserRepository`**(`app/repositories/tenant.py`):单行查询(按 id/username/email 找用户)
- **`UserListRepository`**(`app/repositories/user.py`):列表查询(分页、筛选、排序、统计)

看列表查询的核心:

**文件:`app/repositories/user.py`**

```python
class UserListRepository:                    # ← 第 47 行
    def _base(self, tenant_id: str):         # ← 第 57 行,「基础查询」
        return (
            select(User)                     # 查 users 表
            .join(UserTenant, UserTenant.user_id == User.id)  # 关联成员关系表
            .where(
                UserTenant.tenant_id == tenant_id,    # ← 只看本租户(多租户隔离!)
                UserTenant.valid_to.is_(None),         # 只看当前生效的成员关系(SCD2)
                User.is_deleted.is_(False),            # 排除已删除的
            )
        )

    def _apply_filters(self, stmt, f: UserFilters):  # ← 第 88 行,叠加搜索/筛选条件
        if f.search:                                  # 搜索关键词
            like = f"%{f.search}%"
            stmt = stmt.where(or_(
                User.username.ilike(like), User.email.ilike(like), ...
            ))
        if f.status:                                  # 按状态筛选
            stmt = stmt.where(User.status == f.status)
        if f.role:                                    # 按角色筛选
            stmt = stmt.where(UserTenant.role == f.role)
        return stmt

    async def list(self, tenant_id, f: UserFilters, super_admin=False):  # ← 第 121 行
        stmt = self._apply_sort(self._apply_filters(self._base(tenant_id), f), f)
        stmt = stmt.limit(f.limit).offset(f.offset)   # 分页
        users = list((await self.db.execute(stmt)).scalars().all())  # 执行查询
        # 再算一下总数(用于分页器)
        counted = self._apply_filters(self._base(tenant_id), f).subquery()
        total = (await self.db.execute(select(func.count()).select_from(counted))).scalar_one()
        return users, int(total)
```

> 🔑 **多租户隔离就在这里**:`_base()` 里的 `UserTenant.tenant_id == tenant_id` 这一行,
> 保证了「A 租户的管理员永远查不到 B 租户的用户」。这是在 **Repository 层**强制的,
> 不靠 Service「记得加 where」。详见 [04-多租户隔离](../02-后端架构/04-多租户隔离.md)。

> 💡 **`scalars().all()` 是什么**:SQLAlchemy 查询返回的是「行」,每行可能含多个对象
> (因为 JOIN 了)。`scalars()` 把第一列(User)取出来,`all()` 转成列表。

---

## 第四站:Service(业务经理,组合步骤)

Service 层是「业务逻辑」的大本营。它不直接写 SQL(那是 Repository 的事),而是**编排**:
先校验权限 → 再查重 → 再加密密码 → 再写库 → 再同步角色 → 再记日志。

**文件:`app/services/user_service.py`**

以「创建用户」为例,这是最长的一个方法,但逻辑清晰:

```python
class UserService:                           # ← 第 47 行
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)              # 单行查询
        self.memberships = UserTenantRepository(db)  # 成员关系
        self.list_repo = UserListRepository(db)      # 列表查询
        # ...还有 logs / sessions / login_methods

    async def create(self, actor_id, tenant_id, payload: UserCreate):  # ← 第 182 行
        # ① 校验权限:当前操作者(actor)有没有 users:create 权限?
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "create")

        # ② 业务校验:用户名/邮箱不能重复(全局唯一,因为登录是跨租户的)
        if await self.users.get_by_username(payload.username):
            raise BizError("用户名已存在")
        if payload.email and await self.users.get_by_email(str(payload.email)):
            raise BizError("邮箱已存在")

        # ③ 加密密码(bcrypt),构造 User 对象
        user = User(
            id=uuid.uuid4().hex,
            username=payload.username,
            email=str(payload.email),
            password=hash_password(payload.password),   # ← 明文 → 哈希
            status=payload.status,
            # ...
        )
        self.db.add(user)
        await self.db.flush()                            # 先写进库(拿自增的默认值)

        # ④ 同步成员关系 + casbin 角色策略(SCD2 写路径)
        await self.memberships.assign_role(user.id, tenant_id, payload.role)
        await permission_service.add_role_for_user_in_domain(user.id, payload.role, tenant_id)

        # ⑤ 记审计日志
        await self.logs.record(action="user.create", ...)

        # ⑥ 提交事务
        await self.db.commit()
        return await self._read(tenant_id, user)         # 返回完整的 UserRead
```

> 💡 **为什么有这么多步?** 因为创建一个用户不止是「插一行数据」那么简单——还要建立租户
> 成员关系、同步权限策略、记日志。Service 层把这些步骤编排在一起,保证数据一致性。

**更新**(`update`,第 248 行)和**删除**(`delete`,第 347 行)的结构类似,但有个关键区别:
- **更新**:逐字段比对,只改变化的字段;如果是超级管理员,跳过角色/组织修改(跨租户含义不明)
- **删除**:软删除(`is_deleted=True`),并**撤销所有租户的成员关系 + casbin 角色 + 所有登录会话**

> 🗑️ **删除为什么这么「重」?** 因为要保证安全:删了的用户,他的 token 立刻失效(撤会话),
> 权限策略也立刻清掉(撤 casbin)。不能让一个「已删除」的用户还能登录或操作。

---

## 第五站:Controller / 路由(前台接待)

路由层负责:接 HTTP 请求 → **校验权限** → 调 Service → 把结果转成 HTTP 响应。

**文件:`app/api/v1/users.py`**

```python
router = APIRouter(prefix="/users", tags=["users"])    # ← 第 26 行,所有路由都有 /users 前缀

@router.post(                                           # ← 第 116 行,创建用户
    "/",
    response_model=UserRead,                            # 返回格式
    status_code=status.HTTP_201_CREATED,                # 成功返回 201
    dependencies=[Depends(require_permission("users", "create"))],  # ← 权限校验!
)
async def create_user(
    payload: UserCreate,                                # ← FastAPI 自动用 Schema 校验入参
    user: CurrentUser = Depends(get_current_user),      # ← 从 token 解出当前登录者
    db: AsyncSession = Depends(get_db),                 # ← 注入数据库会话
) -> UserRead:
    try:
        return await UserService(db).create(user.user_id, user.tenant_id, payload)
    except ValueError as e:
        raise _http_exc(e) from e    # BizError→400, NotFoundError→404
```

**全部 8 个端点一览**(都在 `users.py` 里):

| 操作 | 方法 | 路径 | 权限 | 行号 |
|------|------|------|------|------|
| 统计 | GET | `/users/statistics` | users:read | 第 40 行 |
| 列表 | GET | `/users/?page=1&limit=10&search=...` | users:read | 第 55 行 |
| 详情 | GET | `/users/{user_id}` | users:read | 第 98 行 |
| **创建** | POST | `/users/` | users:create | 第 116 行 |
| **更新** | PUT | `/users/{user_id}` | users:update | 第 133 行 |
| **删除** | DELETE | `/users/{user_id}` | users:delete | 第 156 行 |
| 改状态 | PATCH | `/users/{user_id}/status` | users:update | 第 177 行 |
| 重置密码 | POST | `/users/{user_id}/reset-password` | users:update | 第 200 行 |

> 🔐 **权限校验在哪?** 就是 `dependencies=[Depends(require_permission("users", "create"))]`
> 这一行。`require_permission` 是个依赖注入(详情见 [06-权限模型RBAC](../02-后端架构/06-权限模型RBAC.md)),
> 它会在进函数体之前先检查:当前用户有没有 `users:create` 权限?没有就直接返回 **403 Forbidden**。
>
> **三种角色的权限矩阵**(针对 users 资源):
> - 超级管理员(super_admin):绕过一切,跨租户全权
> - 租户所有者(owner) / 管理员(admin):本租户内增删改查(admin 不能 delete)
> - 普通成员(member):**全部 403**,看不到用户管理

---

## 第六站:前端(顾客看到的店面)

现在数据已经能从数据库取出来了。**但用户看到的不是 JSON,是一个漂亮的表格。** 前端负责
「发请求拿数据」+「把数据画成界面」。前端分了清晰的几层:

```
界面(users-page.tsx)  ——  按钮、表格、弹窗、表单
  ↓ 调用
Hooks(queries.ts)     ——  数据缓存 + 自动刷新(TanStack Query)
  ↓ 调用
API 函数(endpoints.ts) ——  拼装 HTTP 请求
  ↓ 调用
HTTP 客户端(client.ts) ——  axios,发请求 + 自动带 token
```

> 💡 **为什么要分这么多层?** 每层只做一件事,好维护、好替换。比如以后想换掉 axios 换成
> fetch,只改 `client.ts` 一处,上面全不动。

### 6.1 类型定义(前后端的「契约」)

**文件:`frontend/src/api/types.ts`**

前端用 TypeScript,每个数据都有类型。这些类型和后端的 Schema **手工对齐**(字段名一致):

```typescript
export interface UserFull {              // ← 第 58 行,对应后端的 UserRead
  id: string;
  username: string | null;
  email: string | null;
  status: "active" | "inactive" | "locked";
  role: { id: string; name: string; code: string } | null;  // 角色对象
  organizations: { id: string; name: string }[];
  created_at: string;
  // ...
}

export interface UserFormData {          // ← 第 77 行,表单提交的数据
  username: string;
  email: string;
  password?: string;                     // 创建时填,更新时没有
  role: string;                          // 角色代码(member/admin/owner)
  status: "active" | "inactive" | "locked";
  // ...
}

export interface UserFilters {           // ← 第 90 行,列表筛选条件
  search?: string;
  status?: "all" | "active" | "inactive" | "locked";
  role?: "all" | string;
  page?: number;
  limit?: number;
  sort_by?: "created_at" | "username" | "email";
  sort_order?: "asc" | "desc";
}
```

> 💡 **注意命名风格**:后端 Python 用 `snake_case`(下划线),前端 TS 也跟着用 `snake_case`
> (如 `created_at`)。项目里**没有自动转换层**,所以前后端字段名要手工保持一致。

### 6.2 HTTP 客户端(自动带 token 的小秘书)

**文件:`frontend/src/api/client.ts`**

```typescript
export const api = axios.create({           // ← 第 24 行
  baseURL: "/api/v1",                        // 所有请求自动加 /api/v1 前缀
  timeout: 30000,
});

// 请求拦截器:每个请求自动加上 token(第 30 行)
api.interceptors.request.use((config) => {
  const token = getStoredToken();            // 从 localStorage 拿 token
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

> 💡 **`/api/v1` 怎么到后端的?** 开发时,Vite 配了代理(proxy),把 `/api` 开头的请求转发到
> `http://localhost:8000`(后端)。所以前端写 `/api/v1/users/`,实际打到后端的
> `http://localhost:8000/api/v1/users/`。生产环境用 Nginx 做同样的事。

### 6.3 API 函数(拼装请求)

**文件:`frontend/src/api/endpoints.ts`**

每个操作对应一个函数,就是「发个 HTTP 请求」:

```typescript
// ---------- users (full profile CRUD) ----------  // ← 第 154 行

export async function fetchUsers(filters: UserFilters): Promise<UserListResponse> {
  const { data } = await api.get<UserListResponse>("/users/", {  // ← 第 155 行
    params: {
      search: filters.search,
      status: filters.status === "all" ? undefined : filters.status,  // "all" 不发给后端
      role: filters.role === "all" ? undefined : filters.role,
      sort_by: filters.sort_by,
      sort_order: filters.sort_order,
      page: filters.page ?? 1,
      limit: filters.limit ?? 10,
    },
  });
  return data;
}

export async function createUser(payload: UserFormData): Promise<UserFull> {
  const { data } = await api.post<UserFull>("/users/", payload);  // ← 第 177 行
  return data;
}

export async function updateUser(id: string, payload: Partial<UserFormData>): Promise<UserFull> {
  const { data } = await api.put<UserFull>(`/users/${id}`, payload);  // ← 第 182 行
  return data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);                                // ← 第 190 行
}

export async function changeUserStatus(id: string, status: UserStatus): Promise<UserFull> {
  const { data } = await api.patch<UserFull>(`/users/${id}/status`, { status });  // ← 第 194 行
  return data;
}

export async function resetUserPassword(id: string, newPassword: string): Promise<void> {
  await api.post(`/users/${id}/reset-password`, { new_password: newPassword });  // ← 第 202 行
}
```

> 💡 **注意 `resetUserPassword`**:前端参数叫 `newPassword`(camelCase),但发给后端的 body
> key 是 `new_password`(snake_case)——这里是手工转换的点,和后端 Schema 的 `PasswordReset`
> 对齐。

### 6.4 TanStack Query Hooks(数据缓存 + 自动刷新)⭐

这是前端最「魔法」的一层,也是**最值得理解的一层**。

**文件:`frontend/src/hooks/queries.ts`**

**先理解问题**:如果没有缓存,每次切到用户管理页都要重新请求列表;新增用户后,还得手动
重新请求才能看到新用户。TanStack Query 帮你自动管这些。

**核心机制:queryKey(缓存钥匙)**

```typescript
export const qk = {                                   // ← 第 46 行
  users: (filters: UserFilters) => ["users", filters] as const,  // 列表,每个筛选条件一份
  user: (id: string) => ["users", id] as const,                  // 单个用户详情
  userStats: ["users", "statistics"] as const,                   // 统计
};
```

每个查询有一个「钥匙」(数组)。钥匙一样就复用缓存。比如 `["users", {page:1}]` 和
`["users", {page:2}]` 是两份不同的缓存。

**查询 hooks(读数据)**

```typescript
export function useUsers(filters: UserFilters) {      // ← 第 134 行
  return useQuery({
    queryKey: qk.users(filters),                       // 用筛选条件当钥匙
    queryFn: () => fetchUsers(filters),                // 实际发请求的函数
  });
}
```

组件里调 `useUsers(filters)`,TanStack 自动:首次加载 → 发请求 → 缓存结果 → 返回
`{data, isLoading}`。再切回来,直接用缓存(秒开)。

**Mutation hooks(写数据)+ 自动刷新** ⭐

```typescript
export function useCreateUser() {                     // ← 第 146 行
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserFormData) => createUser(payload),
    onSuccess: () => invalidateUsers(qc),              // ← 创建成功后,让列表缓存「失效」
  });
}

function invalidateUsers(qc) {                         // ← 第 142 行
  qc.invalidateQueries({ queryKey: ["users"] });       // 让所有 ["users", ...] 开头的缓存失效
}
```

> 🎯 **这就是「新增后列表自动刷新」的秘密!**
> 1. `invalidateQueries({ queryKey: ["users"] })` 把所有以 `["users"]` 开头的缓存标记为「过期」。
> 2. 因为 `useUsers` 的 key 是 `["users", filters]`、`useUserStatistics` 的 key 是
>    `["users", "statistics"]`,它们都以 `["users"]` 开头——**全被标记过期**。
> 3. TanStack 自动重新请求这些查询 → **列表和统计卡片同时刷新**,你立刻看到新用户。
>
> 你完全不用手写「创建成功后调 fetchUsers()」,TanStack 全自动搞定。这就是「前缀失效」模式。

5 个 mutation hook 结构完全一样,只是换了 `mutationFn`:

| Hook | 行号 | 做什么 | 成功后 |
|------|------|--------|--------|
| `useCreateUser` | 第 146 行 | POST 新建 | invalidateUsers |
| `useUpdateUser` | 第 154 行 | PUT 更新 | invalidateUsers |
| `useDeleteUser` | 第 163 行 | DELETE 删除 | invalidateUsers |
| `useChangeUserStatus` | 第 171 行 | PATCH 改状态 | invalidateUsers |
| `useResetUserPassword` | 第 180 行 | POST 重置密码 | invalidateUsers |

> 💡 **为什么用 `invalidate`(失效重查)而不是「乐观更新」?** 乐观更新是「不等服务器确认就
> 先改界面」,体验更快但复杂(还要处理失败回滚)。这里用失效重查更简单可靠——服务器返回什么
> 就显示什么。对于用户管理这种操作不频繁的场景,完全够用。

### 6.5 页面组件(用户看到的界面)

**文件:`frontend/src/pages/users-page.tsx`**

这是最大的文件(721 行),但结构清晰。我们跟着「用户做了什么操作」来看代码:

**路由挂载(怎么进入这个页面)**

`App.tsx` 第 50 行:`<Route path="/users" element={<UsersPage />} />`
(包在 `ProtectedRoute` + `RequireUserManagement` 守卫里——普通成员进不来,详见
[03-认证与路由守卫](../03-前端架构/03-认证与路由守卫.md))

**页面主结构**

```tsx
export function UsersPage() {                          // ← 第 122 行
  const toast = useToast();                             // 提示框
  const { me } = useAuth();
  const isSuperAdmin = me?.platform_role === "super_admin";  // 超管才显示「所属租户」列

  const [filters, setFilters] = useState<UserFilters>({...});  // ← 第 128 行,筛选状态
  const { data, isLoading } = useUsers(filters);        // ← 第 141 行,列表数据(自动缓存)
  const { data: stats } = useUserStatistics();          // ← 第 142 行,统计卡片

  const createMut = useCreateUser();                    // ← 第 145 行,5 个 mutation
  const updateMut = useUpdateUser();
  const deleteMut = useDeleteUser();
  // ...

  const users = data?.items ?? [];                      // ← 第 160 行,从响应取列表
```

**(A) 列表渲染** —— `useUsers` 返回的 data,渲染成表格:

```tsx
<Table>                                                // ← 第 319 行
  <TableHeader>
    <TableRow>
      <TableHead>用户</TableHead>
      <TableHead>邮箱</TableHead>
      <TableHead>角色</TableHead>
      {isSuperAdmin && <TableHead>所属租户</TableHead>}   {/* 超管才显示 */}
      <TableHead>状态</TableHead>
      <TableHead className="text-right">操作</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {users.map((u) => (                                 // ← 第 336 行,遍历渲染每行
      <TableRow key={u.id}>
        <TableCell>{u.username}</TableCell>
        <TableCell>{u.email}</TableCell>
        <TableCell><Badge>{u.role?.name}</Badge></TableCell>
        {/* ...操作列:编辑/删除/改状态/重置密码(第 372 行的 DropdownMenu) */}
      </TableRow>
    ))}
  </TableBody>
</Table>
<Pagination ... />                                      // ← 第 418 行,分页器
```

**(B) 新增用户** —— 按钮 → 弹窗 → 表单 → 提交:

```tsx
// 1. 点「新增用户」按钮 → 打开弹窗,重置表单
function openCreate() {                                 // ← 第 192 行
  setEditing(null);
  form.reset(EMPTY_FORM);                               // 清空表单为默认值
  setFormOpen(true);                                    // 打开弹窗
}

// 2. 弹窗里的表单(第 431 行),用 react-hook-form + zod 校验
<form onSubmit={form.handleSubmit(onSubmit)}>           // ← 第 441 行
  <Field label="用户名" error={...}>
    <input {...form.register("username")} />
  </Field>
  {/* 邮箱、密码(仅新增)、真实姓名、手机、角色下拉、状态下拉 */}
  <Button type="submit">创建</Button>
</form>

// 3. 提交时的处理
async function onSubmit(values: FormValues) {           // ← 第 212 行
  if (!editing) {
    // 创建:校验密码 → 调 mutation
    await createMut.mutateAsync({                       // ← 第 228 行
      ...values,
      organization_ids: [],                             // 手动补这个字段
    });
    toast.success("已创建用户");
    setFormOpen(false);
  } else {
    // 更新:剔除密码(改密走专用端点)→ 调 mutation
    const { password: _pw, ...rest } = values;          // ← 第 217 行,密码不在这里改
    await updateMut.mutateAsync({ id: editing.id, payload: rest });
  }
}
```

> 💡 **表单校验用 zod**(`formSchema`,第 101 行):`username` 至少 2 字符、`email` 要合法格式。
> 校验不过,react-hook-form 不会触发 `onSubmit`,直接在字段下显示红字错误。

**(C) 删除用户** —— 点删除 → 确认弹窗 → 确认:

```tsx
// 操作菜单里的「删除」→ 打开确认弹窗
<DropdownMenuItem onClick={() => setDeleteTarget(u)}>   // ← 第 407 行
  删除
</DropdownMenuItem>

// 确认弹窗(第 548 行),文案说明是软删除
<Dialog open={!!deleteTarget}>
  <p>该操作为软删除,可在数据库恢复</p>
  <Button onClick={handleDelete}>确认删除</Button>
</Dialog>

async function handleDelete() {                         // ← 第 246 行
  await deleteMut.mutateAsync(deleteTarget.id);
  toast.success("已删除用户");
  setDeleteTarget(null);
}
```

**(D) 改状态 / (E) 重置密码** —— 结构类似,都是「菜单项 → 处理函数 → mutation」:

```tsx
async function handleStatus(u, status) {                // ← 第 257 行
  await statusMut.mutateAsync({ id: u.id, status });
}
async function handleResetPassword() {                  // ← 第 266 行
  await resetPwMut.mutateAsync({ id: resetTarget.id, password: newPassword });
}
```

**(F) 搜索 / 筛选 / 分页** —— 改 `filters` 状态,`useUsers` 自动重新请求:

```tsx
// 搜索:回车提交
function applySearch() {                                // ← 第 282 行
  setFilters((f) => ({ ...f, search: searchInput, page: 1 }));  // 重置到第 1 页
}

// 状态筛选:选下拉
<Select onValueChange={(v) => setFilters((f) => ({ ...f, status: v, page: 1 }))}>
```

> 🎯 **筛选怎么触发重新请求的?** `filters` 是 React state,一改 → 组件重新渲染 →
> `useUsers(filters)` 的 queryKey `["users", filters]` 变了 → TanStack 认为是「新查询」
> → 自动发请求。**你完全不用手写「筛选变化时调接口」**,React + TanStack 全自动。

---

## 串起来:一次「新增用户」的完整时序

现在把所有层串起来,看一个完整的请求生命周期:

```
┌─ 前端 ──────────────────────────────────────────────────────────────┐
│ ① 你点「新增用户」→ openCreate() → 填表单 → 点「创建」              │
│    users-page.tsx:192 / :441                                        │
│ ② form.handleSubmit(onSubmit) → zod 校验通过                        │
│    users-page.tsx:212                                               │
│ ③ createMut.mutateAsync(payload)                                    │
│    users-page.tsx:228 → queries.ts:146                              │
│ ④ createUser(payload)                                               │
│    endpoints.ts:177                                                 │
│ ⑤ api.post("/users/", payload) → axios 加 Bearer token              │
│    client.ts:24 / :30                                               │
│    → POST http://localhost:8000/api/v1/users/  (Vite proxy 转发)    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ HTTP 请求
┌─ 后端 ──────────────────────────────────────────────────────────────┐
│ ⑥ FastAPI 路由匹配 POST /users/                                     │
│    users.py:116                                                     │
│ ⑦ 依赖注入依次执行:                                                 │
│    - get_current_user:验 token → 解出 user_id / tenant_id           │
│      deps.py:57                                                     │
│    - require_permission("users","create"):查 casbin → 有权限?✅     │
│      deps.py:151                                                    │
│    - UserCreate Schema:校验 JSON → 字段合法?✅                      │
│      schemas/user.py:52                                             │
│ ⑧ UserService(db).create(actor_id, tenant_id, payload)              │
│    user_service.py:182                                              │
│ ⑨ Service 内部:                                                     │
│    - permission_service.require() 再校验一次(双重校验)             │
│    - get_by_username / get_by_email 查重                            │
│    - hash_password(payload.password) 加密                            │
│    - db.add(user) + flush 写库                                      │
│    - memberships.assign_role() 建租户成员关系                        │
│    - permission_service.add_role_for_user_in_domain() 同步 casbin   │
│    - logs.record() 记审计日志                                       │
│    - db.commit() 提交事务                                           │
│ ⑩ INSERT INTO users ... → PostgreSQL 执行                           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ 返回响应
┌─ 前端 ──────────────────────────────────────────────────────────────┐
│ ⑪ 拿到返回的 UserRead JSON                                          │
│ ⑫ onSuccess: invalidateUsers(qc)                                    │
│    queries.ts:150 → :142                                            │
│    → 所有 ["users", ...] 缓存标记过期                                │
│ ⑬ TanStack 自动重新请求:                                            │
│    - useUsers(filters) → 列表刷新                                    │
│    - useUserStatistics() → 统计卡片刷新                              │
│ ⑭ 表格自动出现新用户行 + 统计数字 +1                                 │
│ ⑮ toast.success("已创建用户") → 弹出绿色提示                        │
│ ⑯ setFormOpen(false) → 关闭弹窗                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**其他操作(编辑/删除/改状态/重置密码)的结构完全一样**,只是替换:
- mutation hook(`updateMut` / `deleteMut` / `statusMut` / `resetPwMut`)
- API 函数(`updateUser` / `deleteUser` / ...)
- HTTP 方法(PUT / DELETE / PATCH / POST)
- Service 方法(`update` / `delete` / `change_status` / `reset_password`)

---

## 你可能会问的

**Q: 为什么创建用户后,统计卡片也自动刷新了?我明明只改了列表啊。**
A: 因为 `invalidateUsers` 失效的是 `["users"]` 这个前缀下**所有**缓存,包括统计
(`["users", "statistics"]`)。这是「前缀失效」模式的威力——一次操作,所有相关数据自动同步。

**Q: 删除用户后,他的数据真的从数据库消失了吗?**
A: 没有。只是 `is_deleted` 被设成 `True`(`user_service.py:370`)。所有查询都带
`WHERE is_deleted = False`,所以界面上看不到了,但数据库里还在,需要时能恢复。

**Q: 普通成员(member)能看到用户管理页面吗?**
A: 不能。有三道防线:① 侧边栏菜单对 member 隐藏(`dashboard-layout.tsx` 的 `canManageUsers`
过滤);② 直接输 URL `/users` 会被路由守卫 `RequireUserManagement` 重定向到首页;③ 即使绕过
前端,后端每个端点都有 `require_permission` 兜底返回 403。详见
[03-认证与路由守卫](../03-前端架构/03-认证与路由守卫.md) 的「权限路由守卫」节。

**Q: 前端怎么知道当前用户是谁、是什么角色?**
A: 登录后拿到 token,存 localStorage。前端用 token 调 `/auth/me` 拿到当前用户信息(含
`platform_role` 和 `roles`),存在 `AuthProvider` 里。所有组件通过 `useAuth()` 读取。详见
[03-认证与路由守卫](../03-前端架构/03-认证与路由守卫.md)。

---

## 记住三句话

1. **后端七层、单向依赖**:路由 → Service → Repository → Model → 数据库,每层只认识下一层。
2. **前端四层、各司其职**:页面(界面)→ hooks(缓存+刷新)→ endpoints(请求)→ client(发 HTTP)。
3. **自动刷新靠 queryKey 前缀失效**:写操作成功后 `invalidateQueries({queryKey:["users"]})`,
   所有 `["users", ...]` 查询自动重新拉取,列表和统计一起刷新。

---

**关键文件清单(按数据流顺序)**:

后端:
- 数据模型:`app/models/tenant.py`(`User` 第 43 行、`UserTenant` 第 129 行)
- 数据校验:`app/schemas/user.py`(`UserCreate` 第 52 行、`UserRead` 第 29 行)
- 列表查询:`app/repositories/user.py`(`UserListRepository` 第 47 行、`UserFilters` 第 20 行)
- 单行查询:`app/repositories/tenant.py`(`UserRepository`)
- 业务逻辑:`app/services/user_service.py`(`create` 第 182 行、`update` 第 248 行、`delete` 第 347 行)
- HTTP 路由:`app/api/v1/users.py`(8 个端点,第 40-220 行)
- 权限校验:`app/api/deps.py` 的 `require_permission` / `app/services/permission_service.py`

前端:
- 类型定义:`frontend/src/api/types.ts`(`UserFull` 第 58 行、`UserFormData` 第 77 行)
- HTTP 客户端:`frontend/src/api/client.ts`(axios 实例第 24 行)
- API 函数:`frontend/src/api/endpoints.ts`(第 154-212 行)
- 数据 hooks:`frontend/src/hooks/queries.ts`(`qk` 第 46 行、`useUsers` 第 134 行、`useCreateUser` 第 146 行)
- 页面组件:`frontend/src/pages/users-page.tsx`(主组件第 122 行)
- 路由配置:`frontend/src/App.tsx`(第 50 行)

**相关文档**:
- [01-分层架构](../02-后端架构/01-分层架构与依赖方向.md) — 为什么这样分层
- [04-TanStack Query](../03-前端架构/04-数据获取TanStackQuery.md) — queryKey/mutation 深入
- [06-权限模型RBAC](../02-后端架构/06-权限模型RBAC.md) — 权限是怎么判断的
- [03-认证与路由守卫](../03-前端架构/03-认证与路由守卫.md) — 登录与权限守卫
- [02-新增后端模块](02-新增后端模块.md) / [03-新增前端模块](03-新增前端模块.md) — 自己加一个 CRUD 模块
