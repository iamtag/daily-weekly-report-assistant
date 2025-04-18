import sqlite3
import datetime
import os
import openai
import requests

# ========== 配置部分 ==========
DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxxxxx"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

DOUBAO_API_KEY = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

USE_DEEPSEEK = False  # 如果为 False，则使用豆包

DB_FILE = "daily_report.db"

# ========== 初始化数据库 ==========
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            original_today TEXT,
            original_tomorrow TEXT,
            optimized_raw TEXT,
            optimized_today TEXT,
            optimized_tomorrow TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT,
            week_end TEXT,
            report TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ========== 调用大模型优化内容 ==========
def call_llm(prompt: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY if USE_DEEPSEEK else DOUBAO_API_KEY}"
    }

    body = {
        "model": "deepseek-chat" if USE_DEEPSEEK else "doubao-lite-32k-240828",
        "messages": [
            {"role": "system", "content": "你是一个资深的日报优化助手，帮助用户润色日报内容，使其更加专业清晰。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(DEEPSEEK_API_URL if USE_DEEPSEEK else DOUBAO_API_URL,
                             headers=headers, json=body)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'].strip()

# ========== 拆分优化内容 ==========
def extract_sections(text: str):
    today_part = ""
    tomorrow_part = ""

    try:
        if "（一）今日进展" in text and "（二）明日计划" in text:
            today_part = text.split("（一）今日进展")[1].split("（二）明日计划")[0].strip()
            tomorrow_part = text.split("（二）明日计划")[1].strip()
    except Exception:
        pass

    return today_part, tomorrow_part

# ========== 保存日报到数据库 ==========
def save_daily_log(date, original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_logs (
            date, original_today, original_tomorrow,
            optimized_raw, optimized_today, optimized_tomorrow
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow))
    conn.commit()
    conn.close()

# ========== 生成日报 ==========
def generate_daily_report():
    today = datetime.date.today().isoformat()
    print("请输入今日进展：")
    original_today = input("1. ")
    print("请输入明日计划：")
    original_tomorrow = input("1. ")

    prompt = f"请优化以下内容并输出成如下格式：\n“（一）今日进展\n1. xxx。\n（二）明日计划\n1.xxx。”\n\n今日进展：{original_today}\n明日计划：{original_tomorrow}"
    optimized_raw = call_llm(prompt)

    optimized_today, optimized_tomorrow = extract_sections(optimized_raw)

    print("\n✅ 优化后的日报内容如下：\n")
    print(optimized_raw)

    save_daily_log(
        today,
        original_today,
        original_tomorrow,
        optimized_raw,
        optimized_today,
        optimized_tomorrow
    )

# ========== 获取日报内容优先级 ==========
def get_final_content(row):
    original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow = row

    final_today = optimized_today or extract_sections(optimized_raw)[0] or original_today
    final_tomorrow = optimized_tomorrow or extract_sections(optimized_raw)[1] or original_tomorrow

    return final_today.strip(), final_tomorrow.strip()

# ========== 生成周报 ==========
def generate_weekly_report():
    today = datetime.date.today()
    if today.weekday() != 4:
        return  # 仅限周五生成

    week_start = today - datetime.timedelta(days=4)
    week_end = today

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow
        FROM daily_logs
        WHERE date BETWEEN ? AND ?
        ORDER BY date ASC
    ''', (week_start.isoformat(), week_end.isoformat()))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("⚠️ 本周没有日报记录，无法生成周报。")
        return

    daily_summaries = ""
    for i, row in enumerate(rows):
        today_final, tomorrow_final = get_final_content(row)
        daily_summaries += f"第{i+1}天：\n今日进展：{today_final}\n明日计划：{tomorrow_final}\n\n"

    prompt = f"请根据以下5天的日报内容，生成一份周报，格式如下：\n“（一）本周进展\n1. xxx\n（二）下周计划\n1. xxx”\n\n日报内容：\n{daily_summaries}"

    report = call_llm(prompt)

    print("\n📘 本周周报如下：\n")
    print(report)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO weekly_reports (week_start, week_end, report)
        VALUES (?, ?, ?)
    ''', (week_start.isoformat(), week_end.isoformat(), report))
    conn.commit()
    conn.close()

# ========== 主程序 ==========
def main():
    init_db()
    generate_daily_report()
    generate_weekly_report()

if __name__ == "__main__":
    main()
