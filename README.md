<div align="center">

# NovelWriter / NovWr

**让代码组装上下文，让模型负责生成，让作者保留最终判断权。**

一个面向**长篇小说创作 / 续写**的 AI 写作工具。  
它不只是“续写下一段”，而是通过可维护的**世界模型**（实体、关系、体系）和可审计的工作流，让生成结果更一致、更可控。

[![Stars](https://img.shields.io/github/stars/Hurricane0698/novelwriter?style=flat-square)](https://github.com/Hurricane0698/novelwriter/stargazers)
[![License](https://img.shields.io/badge/license-AGPLv3-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/backend-FastAPI-009688?style=flat-square)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-React%2019-61DAFB?style=flat-square)](https://react.dev/)
[![Deploy](https://img.shields.io/badge/deploy-Docker-2496ED?style=flat-square)](https://www.docker.com/)

</div>

![NovelWriter screenshot](docs/screenshot.png)

## 为什么做这个项目

在 AI 写作里，一种常见做法是把剧情分析、走向规划、质量评审等环节尽量交给模型。  
但我觉得在长篇小说里，真正棘手的往往不是“生成速度”，而是：

- 这段内容要不要？
- 它有没有偏离世界观？
- 角色说话还像不像他自己？
- 当作品写到几十万字时，应该把**哪些上下文**喂给模型？

NovelWriter 更关注的是把这些问题拆开处理：

- **代码做确定性的事**：上下文组织、索引、状态管理、写入流程
- **LLM 做擅长的事**：自然语言生成、阅读、归纳
- **人保留决定权**：AI 输出永远是草稿，最终是否采纳由作者判断

换句话说，它不是想“替你写小说”，而是想把**试、看、改、再试**这个循环做得足够快、足够便宜、足够可控。

---

## 核心亮点

### 1. 世界模型驱动的上下文组织

NovelWriter 不把“全书大总结”当成唯一依赖，而是维护一套可编辑的世界模型：

- **实体**：角色、地点、物品、概念……
- **关系**：人物关系、组织从属、因果联系……
- **体系**：势力结构、修炼系统、规则约束……

续写时，系统会按当前章节和指令，自动注入**真正相关**的设定，尽量减少无关信息干扰。

### 2. Studio 写正文，Atlas 管设定

长篇创作里，写正文和改设定本来就是交替发生的。

- **Studio**：围绕当前章节工作。适合看正文、写续写指令、生成多个版本、快速比较结果，也适合顺手检查和当前内容直接相关的实体、关系、体系信息。
- **Atlas**：围绕世界模型工作。适合集中整理实体、关系与体系，处理草稿审核、结构调整、设定补全和一致性治理。

前者更偏“写作现场”，后者更偏“设定治理”，对应的是长篇创作里最常来回切换的两类工作。

### 3. 只读的 Novel Copilot：以建议流协作

Novel Copilot 不会先做一个覆盖全书的一次性总括，而是更接近人工查阅资料时的过程：

- **Find**：先找相关内容出现在哪里
- **Open**：再打开最可能有设定变化的内容包
- **Read**：最后只精读关键段落

Copilot 只负责**阅读、检索、归纳和提出建议**，不会静默改库。  
你看到的是一张张待审核建议卡，可以逐条确认、采纳或忽略。

### 4. 自部署优先，BYOK

- 支持 Docker 部署
- 支持任意 OpenAI 兼容接口
- 你可以使用 OpenAI / Gemini / DeepSeek / 本地转发服务等
- 数据留在你自己的环境里

目前项目更偏向 **self-host / BYOK** 使用方式，而不是 SaaS 托管。

---

## 功能概览

| 模块 | 说明 |
|---|---|
| 世界模型 | 实体 / 关系 / 体系统一建模，支撑长篇创作 |
| 章节续写 | 流式生成，多版本对比，快速试错 |
| 从设定集生成世界模型 | 从已有文本提取世界模型，降低冷启动成本 |
| 从章节提取 | 直接从原文提取实体和关系，LLM推断|
| 世界模型编辑器 | 可视化管理设定、关系、结构体系 |
| 小说助手 | 基于 Find / Open / Read 的渐进式披露建议流 |
| 叙事约束 | 用体系级规则约束输出风格与世界观 |
| 连接预检 | 检查流式输出 / JSON 模式兼容性，提前暴露问题 |

---

## 典型工作流

1. 在 Library 里新建作品，或者先打开内置的《西游记》示例熟悉界面
2. 导入已有正文、设定集，或从空白项目开始写作
3. 用 **从设定集生成世界模型** 建立初始实体、关系和体系；如果已经有章节内容，也可以继续用 **从章节提取** 补全设定
4. 在 **Studio** 里选择章节、输入续写指令，生成多个版本并快速对比
5. 在 **Atlas** 里集中整理实体 / 关系 / 体系，修正冲突、补全缺口、审核草稿
6. 需要查设定、核对上下文或发现遗漏时，用 **小说助手** 做查阅、归纳和建议审阅
7. 按“写正文 → 提取设定 → 治理世界模型 → 再续写”的方式循环迭代

---

## 适合什么人

- 在写**长篇小说 / 网文 / 同人 / 系列故事**
- 觉得“AI 很会写，但老是设定漂移”
- 不想把创作决策全部交给自动 Agent
- 希望自己掌控世界观，同时降低维护摩擦
- 想自部署，或希望使用自己的模型 API

如果你更偏好高度自动化、尽量少介入的写作流程，这个项目可能不一定适合你。  
如果你更看重**上下文、设定一致性、可控性**，那它也许会比较合适。

---

## 快速开始

### Docker 部署（推荐）

```bash
git clone https://github.com/Hurricane0698/novelwriter.git
cd novelwriter
cp .env.example .env
# 编辑 .env，填入你的 LLM API 配置
docker compose up -d
```

然后打开：

```text
http://localhost:8000
```

### 部署说明

- 推荐使用 Docker / Docker Compose
- 默认以 **selfhost** 模式启动，前后端已经打包在同一个服务里
- `docker-compose.yml` 默认只监听 `127.0.0.1:8000`，更适合本机自用
- 首次进入 selfhost 实例时，系统会自动准备本地默认管理员上下文，并附带《西游记》示例项目，方便直接体验 Bootstrap、续写、Atlas 和 Copilot
- 至少需要一个可用的 LLM API Key
- 支持任意 OpenAI 兼容接口
- 设置页里的“测试连接”会检测基础连通性、流式输出和 JSON 模式兼容性

> 注：目前**没有长期维护的官方托管版**，README 以自部署 / BYOK 为准。

---

## 本地开发

### 后端

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd web
npm install
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`。

---

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | 是 | LLM API 密钥 |
| `OPENAI_BASE_URL` | 否 | API 地址，可替换为任意兼容接口 |
| `OPENAI_MODEL` | 否 | 默认使用的模型名称 |
| `JWT_SECRET_KEY` | 生产环境必填 | JWT 签名密钥，请使用随机长字符串 |
| `DATABASE_URL` | 否 | 数据库地址，默认 SQLite |

完整配置见 [`.env.example`](.env.example)。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI · SQLAlchemy · SQLite / PostgreSQL |
| 前端 | React 19 · TypeScript · Tailwind CSS · React Query |
| AI 集成 | OpenAI 兼容 API |
| 部署 | Docker · Docker Compose |

---

## 项目结构

```text
app/              # FastAPI 后端
  api/            # 路由层
  core/           # 业务逻辑（生成、上下文组装、Bootstrap）
  models.py       # SQLAlchemy 数据模型
  config.py       # 配置管理
web/              # React 前端
  src/pages/      # 页面组件
  src/components/ # UI 组件
data/             # 数据文件（Worldpack、演示数据）
tests/            # 后端测试
scripts/          # 工具脚本
```

---

## 公开仓说明

这个 GitHub 仓库主要用于**公开发布稳定版本**和接收反馈，不是私有主仓的实时开发镜像。  
如果你在反馈问题，尽量附上使用的版本标签（`v*`）或当前 commit。  
更详细的发布说明见 [`docs/public-release-repo.md`](docs/public-release-repo.md)。

---

## 反馈与协作

- **提 Issue 前**：建议先搜索一下是否已有同类问题，并尽量直接使用仓库里的 Issue 模板
- **Bug 报告**：请尽量附上版本号、部署方式、模型接口类型、复现步骤、报错信息、日志或截图
- **功能建议**：欢迎说明你的创作场景、当前痛点、理想行为，以及为什么现有流程不够顺手
- **Pull Request**：小范围修复欢迎直接提；较大改动建议先开 Issue 对齐方向

如果你觉得这个项目有点意思，欢迎点个 **Star**。  
对独立开发者来说，这类反馈非常重要。

---

## License

本项目基于 [AGPLv3](LICENSE) 许可证开源。

## 友情链接
[Linux.do](https://linux.do)
