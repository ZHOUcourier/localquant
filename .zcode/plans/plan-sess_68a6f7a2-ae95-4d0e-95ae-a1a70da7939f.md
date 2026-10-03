# 实施方案：QUBE 附件 + 技能参数表单 + 密钥入系统凭据库

探索结论：三个功能的挂接点全部确认。`python-multipart` 已是依赖；QUBE 已有用户技能 CRUD（缺的只是参数表单）；两个配置 GET 已返回掩码而非明文（「永不回显」只差去掉掩码展示），主要工作是 keyring 迁移。

---

## 功能 1：文档附件进 QUBE 会话

### 后端

**新依赖**（pyproject.toml + `uv sync`）：`pypdf`（PDF）、`python-docx`（Word）、`openpyxl`（Excel，pandas 引擎）、`python-pptx`（PPT）。

**存储与解析** — 新建 `backend/services/qube_attachments.py`：
- 文件落 `data/qube_attachments/<session_id>/<attachment_id>_<filename>`；表格类（csv/xlsx）另存规范 CSV `<id>.csv` 供沙箱使用
- 解析：pdf→pypdf 逐页 extract_text；docx→python-docx 段落+表格文本；pptx→python-pptx 逐页形状文本；txt/md/csv 直接读；xlsx→pandas 读入后转规范 CSV，记录行数/列名/head 预览
- 限制：单文件 ≤25MiB；提取文本截断 40 万字符（尾部标注「已截断」）；解析放 `run_in_threadpool`（失败返回 400 带原因）

**数据库**（database.py，照既有 PRAGMA/ALTER 迁移惯例）：
- 新表 `qube_attachments(id TEXT PK, session_id, filename, kind text|table, mime, size, extracted_chars, preview, table_meta_json, created_at)`；提取全文存 `<id>.txt` 文件（不进 DB，避免膨胀）
- `qube_messages` 加列 `attachments_json TEXT DEFAULT ''`

**路由**（routes/qube.py）：
- `POST /sessions/{session_id}/attachments`（multipart，参考 comfy/routes.py:345 的 UploadFile 先例）
- `GET /attachments/{id}/file`（原文件下载）
- `ChatRequest` 加 `attachment_ids: list[str]`；校验归属会话后随消息存 `attachments_json`
- **LLM 注入**：`_stream_reply` 里每条带附件的 user 消息在喂给模型时拼一段清单（附件 id/类型/大小/前 1200 字预览；表格类附 shape+列名），API 与 CLI 引擎两条分支都注入；落库的 content 保持原文（清单不污染导出/重试逻辑）；`_load_history` 带出 attachments 供 regenerate/edit 重建清单
- `DELETE /sessions`（单个/批量）时清理附件目录
- `TOOL_DISPLAY_NAMES` 补 `read_attachment`→「读取附件」；`QUBE_SYSTEM`（qube.py:42）补两句附件使用说明

**agent 工具**（services/qube_agent.py）：
- 新工具 `read_attachment`：参数 `{attachment_id?, name?, keyword?, offset}`，仿 `_tool_read_doc`（qube_agent.py:282）的关键词窗口模式；单次返回 ≤3200 字符（工具结果全局截断 4000 字符、ensure_ascii=False，qube_agent.py:224），用 offset 分页
- `run_research_code` 扩展：会话内表格附件的规范 CSV 以 `WriteEntry` 写入容器（现成机制，sandbox.py:140），runner 模板（sandbox.py:73-95）注入 `attachments = {文件名: DataFrame}` 命名空间变量，进程内降级路径同样注入；工具描述说明用法——不改变 `run_experiment(data)` 签名，向后兼容

### 前端

- `types.ts`：`ChatMsg.attachments`；`jsonFetch` 旁新增 `uploadFetch`（FormData，全前端首个上传用例）
- `Qube.vue` 输入区工具栏行（1002-1031，ModelBar 左侧）：回形针按钮 + 隐藏 file input（multiple）+ 待发送 chips（名称/大小/删除）+ 上传中状态；错误显示在输入区上方（复用 chatError 样式）；`sendText` payload 加 `attachment_ids`；发送后清空
- `ChatMessage.vue`：用户消息气泡渲染附件 chips（图标+文件名，可点击下载）

## 功能 2：用户技能参数表单

### 后端（routes/qube.py，复用现有 CRUD）
- `SkillParam` 模型：`{name, label, type: text|number|select, required, default, options[], placeholder}`；校验 ≤12 个、name 唯一且 `^[a-z_][a-z0-9_]*$`、select 必有 options
- `SkillCreate`/`SkillUpdate` 加 `params` 字段，写现有 `params_json` 列（`_skill_row` 已解析返回，无需改）

### 前端
- `types.ts`：`Skill.params: SkillParam[]`（现为 string[]）
- `Skills.vue`：新建表单加「参数定义」repeater（加行/删行/每行 name/label/type/required/default/options）；用户技能补「编辑」入口（复用表单，走现有 PUT）；卡片参数胶囊渲染 `p.label`
- 新组件 `components/skills/SkillParamsDialog.vue`（ui/Dialog + Input + Select）：有参数的技能点「在 QUBE 中使用」时弹表单（default 预填、required 校验）→ 确认后 `{{name}}` 模板替换 → `router.push` 预填输入框（沿用 Qube.vue:681 的 query.prompt 链路）；无参数技能行为不变。Skills.vue 与 SkillDetailDialog 共用
- **agent 内自建**：qube_agent.py 新工具 `create_skill`（display_name/description/category/prompt/params，同套校验，落 user 技能）——对齐 QuantStudio 的对话式技能创作

## 功能 3：密钥入系统凭据库 + 界面永不回显

### 后端
- 新依赖 `keyring`（macOS Keychain / Windows 凭据管理器内置支持）
- 新建 `backend/secrets.py`：`SERVICE = "localquant"`；`is_available()`（探测后端，不可用返回 False）；`get/set/delete_secret`；`SECRET_ENV_KEYS = {OPENAI_API_KEY, QUBE_API_KEY, QZ_ACCESS_KEY, QZ_SIGN_SECRET, PANDA_TOKEN}`；`migrate_env_secrets()`——启动时把 .env 中非空密钥写入 keychain **成功后**才从 .env 删行（保留注释，需给 `_write_env` 补删键语义，settings.py:102-126）；幂等；keyring 不可用则完全跳过（.env 行为不变，Docker/CI 自动降级）
- `config.py`：Settings 加 `panda_token` 字段；`settings = Settings()` 后从 keyring overlay 回填空缺密钥字段（lifespan 迁移后再次 overlay）
- PUT 路由（settings.py:83-99、qube.py:190-203）：密钥字段非空时 → keyring 可用则 `set_secret` + 内存 setattr + 确保 .env 无该键；不可用则走现有 .env 路径。「空=不修改」语义不变
- **永不回显**：GET /api/config（settings.py:58-80）删 `openai_api_key_masked`、GET /api/qube/config（qube.py:176-177）删 `qube_api_key_masked`（保留 `*_set` 布尔）；新增 `qz_access_key_set`/`qz_sign_secret_set` 与对应 PUT 字段；quantzone.py:28 的「请在 .env 设置」文案更新
- main.py lifespan（init_db 之后，main.py:32）调用迁移；`scripts/scrape_factors.py` 改用 `settings.panda_token`
- 新测试 `tests/test_secrets.py`：fake keyring backend（`keyring.set_keyring`）验证迁移幂等/删键保留注释/GET 无掩码/PUT 落 keyring/降级路径

### 前端
- `Settings.vue`：API Key 状态展示由「已配置 (sk-1\*\*\*\*abcd)」改为纯状态点「已配置/未配置」（不展示任何掩码字符，Settings.vue:286-295）；新增「QuantZone（分钟因子对拍）」小节：两个只写 password 输入 + 已配置状态，同「留空不修改」模式
- `EngineConfigDrawer.vue`：同样去掩码改状态展示（106-116）

## 文档与收尾
- `docs/功能模块.md` QUBE/数据管理节、`README.md` 功能总览 QUBE 行补一句；`.env.example` 注释说明密钥首次启动自动迁入系统凭据库
- 全程不触碰投资边界与会话生命周期（功能 4 未批准，本次不做）

## 验证
1. `uv sync` 后 `pytest` + `ruff check backend`（含新增测试）
2. 前端 `npm run build` + type check
3. `make dev` 手测：上传 txt/PDF/xlsx → 对话清单与 read_attachment 分页 → run_research_code 读 attachments 变量；技能带参数创建/编辑/填参使用；macOS 钥匙串出现 localquant 条目、.env 密钥行被清除、设置页无掩码显示

涉及文件：后端约 9 个（config.py、database.py、routes/qube.py、routes/settings.py、routes/quantzone.py、routes/data 无关不动、services/qube_agent.py、services/qube_attachments.py（新）、secrets.py（新）、main.py、pyproject.toml），前端 6 个（Qube.vue、ChatMessage.vue、Skills.vue、SkillDetailDialog.vue、Settings.vue、EngineConfigDrawer.vue、types.ts、SkillParamsDialog.vue（新））。