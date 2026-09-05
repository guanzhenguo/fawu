# FAWU 合同管理系统

面向企业法务的合同全生命周期管理 MVP。当前版本实现模板与条款版本化、合同快照、确定性风险分级、分级审批、不可变审批动作和哈希链审计，并将 DOCX/AI 处理隔离为独立 FastAPI 服务。

## 已实现

- 模板、条款、变量与版本基线；发布后生成 SHA-256 指纹
- 合同及不可变定稿版本，支持原始 DOCX 附件
- 三级风险路由：无偏离自动通过、普通偏离法务单审、核心偏离双人会签
- 必选条款缺失、新增条款、必填变量缺失检测
- 审批角色、任务、动作记录与驳回取消并行任务
- 追加式审计事件及前后事件哈希链
- Token API 登录、对象级数据范围与管理后台
- FastAPI 文档服务：DOCX 安全检查/抽取、结构化 Diff、脱敏预览
- Vue 3 工作台：总览、合同、风险、审批、模板
- SQLite 本地零配置启动，MySQL/Redis/Docker 生产拓扑

## 本地启动（Windows PowerShell）

要求安装 `uv`、Node.js 20+。仓库已经锁定 Python 与前端依赖。

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv sync --extra dev --python 3.13
uv run python backend/manage.py migrate
$env:FAWU_BOOTSTRAP_PASSWORD="请替换为至少10位密码"
uv run python backend/manage.py bootstrap_demo
uv run python backend/manage.py runserver
```

另开一个终端启动文档服务：

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run uvicorn services.document_api.main:app --reload --port 8001
```

另开一个终端启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

访问地址：

- Web 工作台：<http://localhost:5173>
- Django 管理后台：<http://localhost:8000/admin/>
- 文档服务接口文档：<http://localhost:8001/docs>

演示管理员用户名默认为 `admin`，密码是运行 `bootstrap_demo` 时设置的环境变量值。

## 验证

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run ruff check backend services
uv run pytest
uv run python backend/manage.py verify_audit_chain
Set-Location frontend
npm run build
```

## API 主流程

1. 管理员创建条款、条款版本、模板版本和模板条款。
2. `POST /api/template-versions/{id}/publish/` 发布不可变基线。
3. `POST /api/contracts/` 创建合同。
4. `POST /api/contracts/{id}/versions/` 创建合同快照。
5. `POST /api/contract-versions/{id}/submit/` 运行确定性审查与风险路由。
6. `POST /api/approval-tasks/{id}/decide/` 审批或驳回。

完整模型与边界见 [架构说明](docs/architecture.md)，部署前检查见 [安全清单](docs/security-checklist.md)。

## 当前边界

这是可运行的第一阶段 MVP，不把下列能力伪装成已完成：

- 商业版 Word 高保真比较：代码已保留异步边界，需购买/配置 Aspose.Words 授权后接入。
- 外部大模型：只提供本地脱敏预览；可逆映射必须接入企业 KMS/密钥库后才能调用外网。
- 电子签章、可信时间戳、OA/SSO、短信邮件：需根据企业现有供应商实现适配器。
- 履约任务和纠纷反哺：属于下一阶段业务模块。

未经专项数据合规评估，不应将真实合同原文发送到外部模型。
