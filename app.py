import streamlit as st
import os
import json
import time
from io import BytesIO
from datetime import datetime
import openai
from pypdf import PdfReader

# --- 配置 ---
HISTORY_DIR = "history_data"
HISTORY_FILE = os.path.join(HISTORY_DIR, "index.json")

# 初始化历史目录
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

# 设置页面
st.set_page_config(page_title="ScholarListener", page_icon="🎓", layout="wide")

# 获取 API Key (优先从 Secrets 获取，本地运行时可手动填)
api_key = st.secrets.get("OPENAI_API_KEY")
if not api_key:
    api_key = st.sidebar.text_input("请输入 OpenAI API Key", type="password")

if api_key:
    client = openai.OpenAI(api_key=api_key)
else:
    st.warning("请在侧边栏输入 API Key 或在 Streamlit Secrets 中配置。")
    st.stop()

# --- 核心函数 ---

def extract_text_from_pdf(uploaded_file):
    pdf_reader = PdfReader(uploaded_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def split_text_smart(text, max_chars=3000):
    """简单切分，防止超过 API 限制"""
    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n')
    
    for para in paragraphs:
        if len(current_chunk) + len(para) < max_chars:
            current_chunk += para + "\n"
        else:
            chunks.append(current_chunk)
            current_chunk = para + "\n"
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

def generate_podcast_script(text):
    """生成播客风格脚本"""
    prompt = f"""
    你是一位风趣幽默的学术播主。请根据以下论文内容，生成一段中文播客讲解稿。
    要求：
    1. 像给朋友讲故事一样，口语化，轻松。
    2. 解释核心贡献、方法和结论。
    3. 把引用如 (Deci, 2020) 改为 "Deci在2020年提到..."。
    4. 长度控制在 800 字以内。
    
    论文内容片段：
    {text[:8000]} 
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def text_to_speech(text):
    """调用 OpenAI TTS"""
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text
    )
    return BytesIO(response.content)

def save_to_history(filename, text_content, audio_bytes, mode):
    """保存到本地历史"""
    timestamp = int(time.time())
    base_name = f"{timestamp}_{filename}"
    
    # 保存文本
    text_path = os.path.join(HISTORY_DIR, f"{base_name}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
        
    # 保存音频
    audio_path = os.path.join(HISTORY_DIR, f"{base_name}.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes.read())
        audio_bytes.seek(0) # 重置指针以便播放
        
    # 更新索引
    new_record = {
        "id": timestamp,
        "filename": filename,
        "mode": mode,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "text_path": text_path,
        "audio_path": audio_path
    }
    
    with open(HISTORY_FILE, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data.insert(0, new_record) # 最新在最前
        f.seek(0)
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 界面逻辑 ---

# 初始化 Session State
if "current_view" not in st.session_state:
    st.session_state.current_view = "upload"
if "selected_record" not in st.session_state:
    st.session_state.selected_record = None

# 侧边栏：历史记录
with st.sidebar:
    st.title("📚 听书历史")
    if st.button("➕ 上传新文献", use_container_width=True):
        st.session_state.current_view = "upload"
    
    st.divider()
    
    # 加载历史
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history_data = json.load(f)
            
        for record in history_data:
            label = f"{'🎙️' if record['mode']=='podcast' else '📖'} {record['filename'][:15]}..."
            if st.button(label, key=record['id'], help=record['date']):
                st.session_state.current_view = "history"
                st.session_state.selected_record = record

# 主界面
if st.session_state.current_view == "upload":
    st.title("📄 学术文献听书馆")
    st.write("上传 PDF，自动生成中文讲解或朗读。")
    
    uploaded_file = st.file_uploader("上传 PDF 文件", type=["pdf"])
    
    if uploaded_file:
        col1, col2 = st.columns(2)
        
        # 模式 1: 播客讲解
        if col1.button("🎙️ 生成播客讲解", type="primary", use_container_width=True):
            with st.spinner("正在阅读论文并生成脚本..."):
                raw_text = extract_text_from_pdf(uploaded_file)
                podcast_script = generate_podcast_script(raw_text)
                
            with st.spinner("正在录制音频..."):
                audio_data = text_to_speech(podcast_script)
                save_to_history(uploaded_file.name, podcast_script, audio_data, "podcast")
                st.success("生成完成！请在侧边栏查看历史记录或直接播放。")
                st.audio(audio_data)
                with st.expander("查看播客文稿"):
                    st.write(podcast_script)

        # 模式 2: 全文朗读 (这里简化为朗读摘要，防止 API 超时)
        if col2.button("📖 朗读摘要/前3000字", use_container_width=True):
            with st.spinner("正在提取文本..."):
                raw_text = extract_text_from_pdf(uploaded_file)
                # 简单处理：只取前 3000 字演示，实际使用可循环切片
                short_text = raw_text[:3000]
                # 这里可以加一步 GPT 改写引用，为了演示直接朗读
            
            with st.spinner("正在转为语音..."):
                audio_data = text_to_speech(short_text)
                save_to_history(uploaded_file.name, short_text, audio_data, "read")
                st.success("生成完成！")
                st.audio(audio_data)

elif st.session_state.current_view == "history":
    record = st.session_state.selected_record
    if record:
        st.title(f"{'🎙️' if record['mode']=='podcast' else '📖'} {record['filename']}")
        st.caption(f"处理时间: {record['date']}")
        
        # 读取本地音频
        if os.path.exists(record['audio_path']):
            st.audio(record['audio_path'])
        else:
            st.error("音频文件丢失")
            
        # 读取本地文本
        if os.path.exists(record['text_path']):
            with open(record['text_path'], "r", encoding="utf-8") as f:
                content = f.read()
            with st.expander("查看文本内容", expanded=True):
                st.write(content)