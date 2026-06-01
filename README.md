# 

将 XNBot（小雫）的核心功能移植为 AstrBot 插件，接管所有对话消息

## 插件请勿和其他聊天相关插件混用，会冲突
## 插件会覆盖Astrbot的所有普通消息流，命令会跳过插件不受影响

## 功能

- ✅ Agent 记忆检索（ReAct 循环，最多 15 步）
- ✅ 角色扮演回复
- ✅ 记忆系统（SQLite + FAISS 向量检索）
- ✅ 图记忆（Kùzu 图数据库，可选）
- ✅ XN_Core 主动行为系统（睡眠/醒来/日程/心跳/关系）
- ✅ 情绪系统
- ✅ 表情包语义匹配
- ✅ 独立 WebUI（记忆管理、图谱浏览、日志查看、配置编辑）

## 安装步骤

### 1. 复制插件
在astrbot插件管理添加插件页面中选择链接添加或者zip压缩包

### 3. 配置 AI 服务

编辑插件目录下的 `config/ai_config.toml`，填入你的 API Key：
或者前往插件webui添加AI服务配置
```toml
[servers.siliconflow]
base_url = "https://api.siliconflow.cn/v1"
api_key = "sk-你的key"

[servers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key = "sk-你的key"
```

## 启用插件

插件会自动加载，小雫 WebUI 会跟随 AstrBot 一起启动。

## 访问地址

| 小雫 WebUI | http://localhost:8081/web/app |

## 目录结构

```
XNbot_by_AstrBot/
├── main.py              # AstrBot 插件入口
├── nonebot_compat.py    # NoneBot 兼容层
├── metadata.yaml        # 插件元数据
├── requirements.txt     # Python 依赖
├── README.md            # 本文档
├── src/                 # 核心模块（Agent、记忆、情绪、表情）
├── XN_Core/             # 主动行为系统（睡眠/心跳/日程/关系）
├── ai_server/           # AI 调用层
├── config/              # 配置文件（TOML）
├── data/                # 数据目录（数据库、向量索引、日志）
├── emoji/               # 表情包文件
├── tools/               # 日志工具
└── web/                 # 小雫 WebUI
    ├── server.py        # WebUI 后端
    └── frontend/        # Vue 3 前端源码
```

## 配置文件说明

| 文件 | 用途 |
|------|------|
| `config/bot_config.toml` | 机器人基础配置、XN_Core 参数、关系阈值 |
| `config/ai_config.toml` | AI 模型和 API Key |
| `config/rey_config.toml` | System Prompt 模板 |
| `config/reply_config.toml` | 回复切分参数 |
| `config/emotion_config.toml` | 情绪系统参数 |
| `config/emoji_config.toml` | 表情包系统参数 |

## XN_Core 主动行为系统

### 睡眠机制

1. 用户说晚安 → 小雫确认 → 两步确认触发睡眠
2. Agent 生成反思摘要 + 对话打分
3. 根据打分计算睡眠时长（6-12小时）
4. 注册唤醒计时器

### 心跳机制

1. 小雫醒来 → 处理未读消息
2. Agent 生成今日日程（15-20项）
3. Agent 生成心跳计划（3-8次，随机间隔）
4. 按计划触发心跳 → Agent 决策 skip/send

### 关系系统

四维变量影响回复风格：
- `intimacy`（亲密度）：越高越亲密
- `trust`（信任度）：影响对话质量
- `awkward`（尴尬度）：重复消息/无聊对话会增加
- `fatigue`（疲劳度）：长时间对话会增加

## 常见问题

**Q: 图记忆功能不可用**
A: 需要安装 kuzu：`pip install kuzu`

**Q: 小雫 WebUI 打不开**
A: 检查是否安装了 fastapi 和 uvicorn：`pip install fastapi uvicorn`

**Q: AI 调用失败**
A: 检查 `config/ai_config.toml` 中的 API Key 是否正确

**Q: 插件加载失败**
A: 检查 AstrBot 日志，通常是依赖缺失或 Python 版本不兼容

## 与原版 XNBot 的区别

| 项目 | 原版 XNBot | 小雫 astrbot插件 |
|------|-----------|-----------------|
| 框架 | NoneBot2 | AstrBot |
| QQ 协议 | OneBot v11（直接连接） | AstrBot 平台适配器 |
| 多平台 | 仅 QQ | 支持 QQ、微信、飞书、Telegram 等 |
| WebUI | 挂载在 bot 的 FastAPI | 独立运行（端口 8081） |
| 插件管理 | 无 | AstrBot 插件系统 |

## 开发说明

如需修改插件，直接编辑目录下的文件，然后更新到 AstrBot 插件目录
