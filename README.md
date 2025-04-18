# 📅 日报 & 周报整理助手（AI加持）

一个用于生成、优化日报和自动生成周报的小工具，支持调用 DeepSeek 和 豆包 API 进行智能润色。

## 🚀 功能特点

- 输入原始今日进展 & 明日计划，调用 AI 进行润色
- 自动存储到本地 SQLite 数据库
- 每周五自动汇总生成周报
- 支持 DeepSeek / 豆包 模型

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

## ▶️ 使用方式

```bash
python main.py
```

## 🛠 配置说明

在 `main.py` 中修改以下变量以配置你的 API Key：

```python
DEEPSEEK_API_KEY = "你的 Key"
DOUBAO_API_KEY = "你的 Key"
```

切换模型：

```python
USE_DEEPSEEK = False  # True 为 DeepSeek，False 为豆包
```

## 📄 License

MIT