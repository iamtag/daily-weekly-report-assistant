import sqlite3
import datetime
import os
import openai
import requests
import tkinter as tk
from tkinter import messagebox

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
        "model": "deepseek-chat" if USE_DEEPSEEK else "deepseek-v3-250324", #doubao-lite-32k-240828",
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

# ========== 根据最近日报推测今日进展和明日计划 ==========
def predict_today_and_tomorrow():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today_date = datetime.date.today().isoformat()

    # 增加日期条件，确保只查询今天之前的日志
    cursor.execute('''
        SELECT date, optimized_today, optimized_tomorrow
        FROM daily_logs
        WHERE date < ?
        ORDER BY date DESC
        LIMIT 3
    ''', (today_date,))

    rows = cursor.fetchall()  # 格式为 [(date1, today1, tomorrow1), (date2, today2, tomorrow2), ...]
    conn.close()

    if not rows:
        return "", ""  # 如果没有数据，返回空字符串

    # 拼接最近几天的日报内容，生成推测的 prompt
    recent_summaries = ""
    for row_date, row_today, row_tomorrow in rows:
        today_content = row_today or "（无内容）"
        tomorrow_content = row_tomorrow or "（无内容）"
        recent_summaries += f"日期：{row_date}\n今日进展：{today_content}\n明日计划：{tomorrow_content}\n\n"

    # 改进 Prompt，优先参考昨天的明日计划
    prompt = f"""
你是一个专业的日报生成 AI，根据提供的日报内容推测“今日进展”和“明日计划”。日报书写人是一位资深软件工程师，主要从事 AI 应用开发、核心技术研发攻关和功能产品化推进工作。请严格按照以下规则生成内容：
1. “今日进展”优先参考昨天的“明日计划”，总结出当天的主要工作内容和可能完成的任务。
2. “明日计划”基于“今日进展”推测合理的下一步操作，尽量具体化。例如：
   - 如果是研究任务，列出研究的具体步骤。
   - 如果是测试任务，列出可能的测试目标或结果。
   - 如果是长期任务，列出可能的阶段性成果。
3. 输出格式固定为：
   （一）今日进展
   1. xxx。
   （二）明日计划
   1. xxx。
4. 输出必须为纯文本，不得包含任何解释说明、编号、Markdown 或 HTML 标签等修饰。
5. 请保持语言表达简洁、专业，不要添加无关内容。

以下是用户输入的日报内容，请根据这些内容进行推测：
{recent_summaries}
"""

    print(f"[DBG] 推测今日进展和明日计划的 Prompt：\n{prompt}")  # 调试输出

    try:
        prediction = call_llm(prompt)
        predicted_today, predicted_tomorrow = extract_sections(prediction)
        return predicted_today, predicted_tomorrow
    except Exception as e:
        print(f"⚠️ 推测今日进展和明日计划时发生错误：{e}")
        return "", ""

# ========== 生成日报（GUI 版本，集成推测功能） ==========
def generate_daily_report_gui():
    today = datetime.date.today().isoformat()
    # 检查当天是否有记录
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow
        FROM daily_logs
        WHERE date = ?
    ''', (today,))
    row = cursor.fetchone()
    conn.close()

    print("[DBG] 当天记录：", row)  # 调试输出

    # 如果没有当天记录，尝试推测内容
    predicted_today, predicted_tomorrow = ("", "")
    if not row:
        predicted_today, predicted_tomorrow = predict_today_and_tomorrow()
        print(f"[DBG] 推测的今日进展：{predicted_today}")  # 调试输出

    def optimize():
        original_today = today_input.get("1.0", tk.END).strip()
        original_tomorrow = tomorrow_input.get("1.0", tk.END).strip()

        prompt = f"请优化以下内容并输出成如下格式：\n“（一）今日进展\n1. xxx。\n（二）明日计划\n1.xxx。”\n\n今日进展：{original_today}\n明日计划：{original_tomorrow}"
        try:
            engine_info = "DeepSeek" if USE_DEEPSEEK else "豆包"
            info_label.config(text=f"{engine_info} 优化中...")

            optimized_raw = call_llm(prompt)
            optimized_today, optimized_tomorrow = extract_sections(optimized_raw)

            optimized_today_output.delete("1.0", tk.END)
            optimized_tomorrow_output.delete("1.0", tk.END)
            optimized_today_output.insert(tk.END, optimized_today)
            optimized_tomorrow_output.insert(tk.END, optimized_tomorrow)

            # 显示优化引擎信息
            engine_info = "DeepSeek" if USE_DEEPSEEK else "豆包"
            info_label.config(text=f"{engine_info} 完成优化")
        except Exception as e:
            messagebox.showerror("错误", f"发生错误：{str(e)}")

    def save():
        original_today = today_input.get("1.0", tk.END).strip()
        original_tomorrow = tomorrow_input.get("1.0", tk.END).strip()
        optimized_today = optimized_today_output.get("1.0", tk.END).strip()
        optimized_tomorrow = optimized_tomorrow_output.get("1.0", tk.END).strip()
        optimized_raw = f"（一）今日进展\n{optimized_today}\n（二）明日计划\n{optimized_tomorrow}"

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if row:
            # 如果当天已有记录，则更新
            cursor.execute('''
                UPDATE daily_logs
                SET original_today = ?, original_tomorrow = ?,
                    optimized_raw = ?, optimized_today = ?, optimized_tomorrow = ?
                WHERE date = ?
            ''', (original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow, today))
        else:
            # 如果当天没有记录，则插入
            cursor.execute('''
                INSERT INTO daily_logs (
                    date, original_today, original_tomorrow,
                    optimized_raw, optimized_today, optimized_tomorrow
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (today, original_today, original_tomorrow, optimized_raw, optimized_today, optimized_tomorrow))
        conn.commit()
        conn.close()

        messagebox.showinfo("保存成功", "日报已成功保存到数据库。")
        # 同时将optimized_raw复制一份到剪切板
        root.clipboard_clear()
        root.clipboard_append(optimized_raw)
        root.update()
        if datetime.date.today().weekday() == 4:
            generate_weekly_report()
        root.destroy()

    root = tk.Tk()
    root.title("日报输入与优化")

    input_width = 60
    button_width = 15

    # 主界面分为上下两部分
    main_frame = tk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 上部：日报输入和优化区域
    top_frame = tk.Frame(main_frame)
    top_frame.pack(fill=tk.X)

    # 左边输入区域
    left_frame = tk.Frame(top_frame)
    left_frame.pack(side=tk.LEFT, padx=10, pady=10)

    tk.Label(left_frame, text="今日进展：").pack()
    today_input = tk.Text(left_frame, height=10, width=input_width)
    if row:
        today_input.insert(tk.END, row[0])
    elif predicted_today:
        today_input.insert(tk.END, predicted_today)
    today_input.pack()

    tk.Label(left_frame, text="明日计划：").pack()
    tomorrow_input = tk.Text(left_frame, height=10, width=input_width)
    if row:
        tomorrow_input.insert(tk.END, row[1])
    elif predicted_tomorrow:
        tomorrow_input.insert(tk.END, predicted_tomorrow)
    tomorrow_input.pack()

    # 中间提示信息和按钮区域
    middle_frame = tk.Frame(top_frame)
    middle_frame.pack(side=tk.LEFT, padx=10, pady=10)

    engine_info = "DeepSeek" if USE_DEEPSEEK else "豆包"
    info_label = tk.Label(middle_frame, text=f"优化引擎：{engine_info}")
    info_label.pack()

    optimize_button = tk.Button(middle_frame, text="AI 优化", command=optimize, width=button_width)
    optimize_button.pack(pady=10)

    save_button = tk.Button(middle_frame, text="保存", command=save, width=button_width)
    save_button.pack()

    # 右边优化输出区域
    right_frame = tk.Frame(top_frame)
    right_frame.pack(side=tk.LEFT, padx=10, pady=10)

    tk.Label(right_frame, text="优化后的今日进展：").pack()
    optimized_today_output = tk.Text(right_frame, height=10, width=input_width)
    if row:
        if row[3]:
            optimized_today_output.insert(tk.END, row[3])
        elif row[2]:
            optimized_today_output.insert(tk.END, extract_sections(row[2])[0])
    optimized_today_output.pack()

    tk.Label(right_frame, text="优化后的明日计划：").pack()
    optimized_tomorrow_output = tk.Text(right_frame, height=10, width=input_width)
    if row:
        if row[4]:
            optimized_tomorrow_output.insert(tk.END, row[4])
        elif row[2]:
            optimized_tomorrow_output.insert(tk.END, extract_sections(row[2])[1])
    optimized_tomorrow_output.pack()

    # 下部：本周周报显示区域
    bottom_frame = tk.Frame(main_frame)
    bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    tk.Label(bottom_frame, text="本周周报：").pack()
    weekly_report_text = tk.Text(bottom_frame, height=24, width=input_width*2)
    weekly_report_text.pack(fill=tk.BOTH, expand=True)

    # 获取本周周报内容
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=4)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT report FROM weekly_reports
        WHERE week_start = ? AND week_end = ?
    ''', (week_start.isoformat(), week_end.isoformat()))
    weekly_report = cursor.fetchone()
    conn.close()

    if weekly_report:
        weekly_report_text.insert(tk.END, weekly_report[0])
    else:
        weekly_report_text.insert(tk.END, "本周尚未生成周报")

    root.mainloop()

# ========== 主程序 ==========
def main():
    init_db()
    generate_daily_report_gui()

if __name__ == "__main__":
    main()
