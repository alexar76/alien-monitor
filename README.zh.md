# 👽 Alien Monitor — AIMarket 生态脉搏可视化器

> 🌍 **语言：** [English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · **中文**
>
> 术语遵循[本地化术语表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)。
> 完整的环境变量与部署参考见[英文 README](README.md)。

> **生态：** [AICOM 总览与在线演示](https://modeldev.modelmarket.dev) · **社区：** [Telegram · Castor](https://t.me/just_for_agents) · [Discord · Pollux](https://discord.gg/aimarket)

**地图：** **UNI** [https://monitor-uni.modelmarket.dev/](https://monitor-uni.modelmarket.dev/)（`ALIEN_MODE=universe`）· **LIVE** [https://monitor.modelmarket.dev/](https://monitor.modelmarket.dev/)（`ALIEN_MODE=real`）。划分：[uni-and-live.zh.md](https://github.com/alexar76/aicom/blob/main/docs/uni-and-live.zh.md)。

**Pulse Terminal (ACEX)** 运行在同一主机：**[https://magic-ai-factory.com/pulse/](https://magic-ai-factory.com/pulse/)**。

把每一个组件 —— 枢纽、合约、智能体、桌面应用、插件、区块链 —— 看作一片会呼吸的活体星空。点击任意节点即可放大、查看指标，并看到数据在网络中实时流动。

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="docs/recordings/alien-monitor-hero.gif" alt="运行中的 Alien Monitor —— 实时生态图谱、节点指标与内置 AI 助手" width="820">
  </a>
  <br>
  <sub>实时生态图谱 · 节点检视器 · 内置 AI 助手 —— <a href="https://monitor.modelmarket.dev/"><b>打开在线演示 →</b></a></sub>
</p>

---

## 三种模式

### 🟢 UNI 模式
本地链 + 对已部署的 Hub、Mesh、Factory 与 Prometheus 的**实时轮询** —— 界面与 LIVE 完全一致，不含任何模拟指标。

- 内嵌 EVM（Anvil），可选 Solana 验证者
- 在本地链上自动部署托管（escrow）与 NFT
- 工厂 webhook：`POST /api/universe/materialize`

### 🟡 TEST 模式
带有虚构智能体、支付通道与交易的模拟生态。此模式下的指标是合成的，界面与 AI 助手都会明确说明这一点。

### 🟢 LIVE 模式
连接真实基础设施（Hub、Mesh、Prometheus）**以及链上 RPC**：

- EVM：`BASE_RPC_URL` / `ETHEREUM_RPC_URL` 等，按 `AIMARKET_PAYMENT_CHAIN` 选择
- 合约：`AIMARKET_ESCROW_EVM_ADDRESS`、`AIMARKET_NFT_CONTRACT`、`AIMARKET_ESCROW_SOLANA_PROGRAM_ID`
- 若存在上层 `aicom/.env`，会自动加载
- 调试：`GET /api/chain/status`

---

## 你会看到什么

一个**属于你的可观测宇宙**，每个天体都是一个活着的组件：

| 视觉元素 | 代表什么 |
|----------|----------|
| ☀️ **恒星式枢纽**，带日冕与引力环 | AIMarket Hub —— 中心 |
| 🪐 **环绕的行星**，带摆动物理 | 核心服务：Factory、Mesh、ACEX |
| 💎 **晶体节点**，带轨道环 | 智能合约（EVM 与 Solana） |
| 🌌 **星云** | 相关组件的聚簇 |
| 🕳️ **虫洞通道** | 服务之间正在发生的数据流 |
| 💫 **小行星带** | 区块链网络活动 |
| ✨ **宇宙尘埃** | 智能体的背景活动 |
| 🌟 **星座连线** | 固定连接 |
| 🆕 **正在成形的行星** | 工厂新产品实时出现 |

## 功能

- **UNI 运行时** —— 本地链加各层实时轮询，没有伪造指标
- **产品成形** —— 工厂产品经 webhook 化为新的行星
- **3D 力导向宇宙** —— 缩放、旋转、平移、飞向节点
- **Bloom 后处理** —— 发光、暗角与噪点
- **实时 WebSocket** —— 每 1.5 秒推送实时数据
- **AI 助手** —— 多提供方 LLM（默认 **DeepSeek `deepseek-v4-pro`**，与 aicom 共用同一注册表），每次提问都附带**监视器实时状态**：tick、模式、节点指标、活动
- **3 套主题** —— 青、洋红、绿，附脉动强度滑块
- **5 种语言** —— EN / RU / ES / FR / ZH；AI 以所选语言作答

### 本地化

| 语言 | 界面文案 | README |
|------|----------|--------|
| English | `frontend/src/i18n/locales/en.json` | [README.md](README.md) |
| Русский | `frontend/src/i18n/locales/ru.json` | [README.ru.md](README.ru.md) |
| Español | `frontend/src/i18n/locales/es.json` | [README.es.md](README.es.md) |
| Français | `frontend/src/i18n/locales/fr.json` | [README.fr.md](README.fr.md) |
| 中文 | `frontend/src/i18n/locales/zh.json` | [README.zh.md](README.zh.md) |

语言选择保存在 `localStorage`（`alien-monitor-locale`）。AI 请求会把 `locale` 一并发往
`POST /api/ai/ask`。五个文件拥有相同的 344 个键：键的一致性、非空文案与术语表合规都由测试
（`frontend/src/__tests__/glossary.test.ts`）守住，因此任何一种语言都不会悄悄落后。

### AI 提供方

读取上层 **aicom** 仓库中的 `data/config/model_providers.yaml`（或 `ALIEN_LLM_CONFIG`）。
默认：`deepseek_api` / `deepseek-v4-pro`。

| 端点 | 用途 |
|------|------|
| `GET /api/ai/providers` | 列出已启用的提供方与模型 |
| `POST /api/ai/ask` | `{ question, locale, provider?, model_role?, state?, selected_node_id? }` |

前端在每次提问时发送当前的 WebSocket `state`，因此模型看到的正是你眼前那片 3D 星空的数据。

**助手知道什么。** 除了实时快照，它还会收到
[生态中心知识库](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md)以及来自 `scripts/satellite-map.yaml`
的卫星注册表。凡是被中心化记录的组件，助手都会自动知晓，无需在提示词里单独描述。若某个节点
不在当前快照中，助手必须回答「在这份快照里看不到」，绝不能说「该组件不存在」。

## 快速开始（本地）

```bash
git clone https://github.com/alexar76/alien-monitor.git
cd alien-monitor

# 虚拟宇宙模式（内嵌区块链 + 实体）
./start.sh --universe

# 或使用模拟数据的测试模式
./start.sh

# 打开：http://localhost:5173
```

## 宇宙模式 API

```bash
# 启动虚拟宇宙
curl -X POST http://localhost:9100/api/universe/start

# 让产品成形（从你的工厂流水线调用）
curl -X POST http://localhost:9100/api/universe/materialize \
  -H 'Content-Type: application/json' \
  -d '{"name": "MyAgent", "type": "ai-agent", "category": "fullstack-app"}'

# 获取宇宙状态
curl http://localhost:9100/api/universe/state

# 停止宇宙
curl -X POST http://localhost:9100/api/universe/stop
```

## 操作

| 操作 | 方式 |
|------|------|
| 旋转视角 | 按住并拖动 |
| 缩放 | 鼠标滚轮 |
| 平移 | 右键拖动 |
| 打开节点 | 点击节点 |
| 切换主题 | 控制栏的 CY / MG / GR 按钮 |
| 切换语言 | 控制栏的语言切换器 |
| 询问 AI | **AI** 按钮 → 用你的语言提问 |

## 生产部署

在服务器上，从 **aicom** 仓库根目录执行：

```bash
./scripts/deploy_alien_monitor.sh
# 或：cd alien-monitor && docker compose -f docker-compose.prod.yml up -d --build
```

默认 **`ALIEN_MODE=universe`**：启动时在**容器内**部署 Anvil、FakeUSDT、托管合约与 NFT。
完整的环境变量表以及 UNI 排障指南见
[英文 README](README.md#production-deploy-magic-ai-factorycom)。

公开地址（经 nginx）：**UNI** https://monitor-uni.modelmarket.dev/ · **LIVE** https://monitor.modelmarket.dev/

## 许可证

MIT —— [AICOM 开放智能体经济](https://github.com/alexar76/aicom)的一部分。
