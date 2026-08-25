# 合肥大学生命健康与环境工程学院 通知监控机器人

自动监控学院官网最新通知，AI 智能总结后通过飞书机器人推送给你。

## 功能

- 定时爬取学院通知公告列表页
- 自动去重，只推送新通知
- 抓取通知详情页正文和附件
- AI 智能总结（豆包大模型，未配置 key 时降级为规则摘要）
- 飞书消息卡片推送（含标题、摘要、附件、原文链接）
- 日志记录 + 已推送记录持久化

## 文件说明

```
hfuu_notice_monitor/
├── config.json      # 配置文件（飞书webhook、AI key等）
├── monitor.py       # 主程序
├── README.md        # 本说明
├── seen_notices.json  # 已推送记录（运行后自动生成）
└── monitor.log      # 运行日志（运行后自动生成）
```

## 快速开始

### 1. 安装依赖

```bash
pip install requests beautifulsoup4
```

### 2. 配置飞书机器人

1. 在飞书群聊中 → 设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 复制 Webhook 地址，填入 `config.json` 的 `feishu_webhook`
3. 如果开启了"签名校验"，把密钥填入 `feishu_secret`（没开启就留空）

### 3. 配置 AI 总结（可选）

- 在 `config.json` 中填入 `ai_api_key`（火山引擎方舟平台的 API Key）
- 不填也能用，会自动降级为截取正文关键段落

### 4. 初始化（首次运行）

首次运行先初始化，把现有通知标记为已读，不会一股脑推送历史通知：

```bash
python monitor.py --init
```

### 5. 运行

**方式一：持续运行（脚本内定时）**

```bash
python monitor.py
```

默认每 30 分钟检查一次，可在 `config.json` 修改 `check_interval_minutes`。

**方式二：Windows 任务计划程序（推荐，开机自启）**

1. Win+R 输入 `taskschd.msc` 打开任务计划程序
2. 创建基本任务 → 触发器选"每天" → 操作选"启动程序"
3. 程序填 `python.exe` 的完整路径，参数填 `monitor.py --once`
4. 起始位置填脚本所在目录
5. 完成后右键任务 → 属性 → 触发器 → 编辑 → 勾选"重复任务间隔"设为 30 分钟

## 配置项说明

| 配置项 | 说明 |
|--------|------|
| `feishu_webhook` | 飞书自定义机器人 Webhook 地址 |
| `feishu_secret` | 飞书机器人签名密钥（开启签名校验时填） |
| `ai_api_key` | 火山引擎方舟 API Key（可选，不填用规则摘要） |
| `ai_api_base` | AI API 地址，默认火山引擎 |
| `ai_model` | AI 模型名称 |
| `check_interval_minutes` | 检查间隔（分钟），默认 30 |
| `list_url` | 学院通知列表页地址 |
| `max_summary_length` | 摘要最大字数 |

## 常见问题

**Q: 飞书收不到消息？**
A: 检查 webhook 是否正确复制完整，机器人是否在群里，是否开启了签名校验但没填 secret。

**Q: 会重复推送吗？**
A: 不会。每条通知用 URL 的 MD5 作为唯一标识，记录在 `seen_notices.json` 中。

**Q: 学院改了页面结构怎么办？**
A: 脚本用 CSS 选择器解析，如果页面改版导致解析不到通知，会在日志中提示。

**Q: 想监控其他栏目？**
A: 修改 `config.json` 中的 `list_url` 为对应栏目列表页即可（解析逻辑通用）。
