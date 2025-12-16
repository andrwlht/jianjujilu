import streamlit as st
import time  # 导入 time 库用于生成时间戳
import requests
import json

# === 1. 页面配置 ===
st.set_page_config(page_title="检具修改记录", layout="centered")
st.markdown("""<style>
    div.stButton>button:first-child {
        width: 100%; height: 3em; font-size: 18px; 
        background-color: #00D6B9; color: white; border-radius: 8px; border: none;
    }
    .block-container { padding-top: 2rem; }
</style>""", unsafe_allow_html=True)

st.title("🛠️ 检具修改录入系统")


# === 2. 飞书 API 工具函数 ===

def get_feishu_token():
    """获取飞书访问凭证"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    # 从 secrets 获取配置
    data = {
        "app_id": st.secrets["feishu"]["app_id"],
        "app_secret": st.secrets["feishu"]["app_secret"]
    }
    try:
        r = requests.post(url, json=data)
        return r.json().get("tenant_access_token")
    except Exception as e:
        st.error(f"连接飞书失败: {e}")
        return None


def upload_images(file_list, access_token):
    """批量上传图片并获取 file_token 列表"""
    if not file_list:
        return []

    tokens = []
    upload_url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 进度条
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, file_obj in enumerate(file_list):
        status_text.text(f"正在上传第 {i + 1}/{len(file_list)} 张图片...")
        
        # === 核心修正 ===
        data_payload = {
            'parent_type': 'bitable_image',
            'parent_node': st.secrets["feishu"]["app_token"],
            'size': str(file_obj.size)  # ❌ 之前是数字，必须转为字符串！
        }
        
        # 为了防止中文文件名在 HTTP 传输中乱码导致 params error，
        # 我们在传输层统一命名为 "image.png/jpg"，飞书主要看 file_obj 的内容
        files_payload = {
            'file': ("image_upload", file_obj, file_obj.type) 
        }
        
        try:
            r = requests.post(upload_url, headers=headers, data=data_payload, files=files_payload)
            res = r.json()
            if res.get("code") == 0:
                tokens.append({"file_token": res["data"]["file_token"]})
            else:
                # 打印出具体的错误信息以便调试
                st.warning(f"图片上传失败: {res}")
                print(f"DEBUG Error: {res}") 
        except Exception as e:
            st.error(f"网络错误: {e}")
            
        # 更新进度
        progress_bar.progress((i + 1) / len(file_list))

    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()
    return tokens


def submit_to_feishu(data_fields):
    """提交数据"""
    token = get_feishu_token()
    if not token: return {"code": -1, "msg": "Token获取失败"}

    app_token = st.secrets["feishu"]["app_token"]
    table_id = st.secrets["feishu"]["table_id"]

    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }

    payload = {"fields": data_fields}
    r = requests.post(url, headers=headers, json=payload)
    return r.json()


# === 3. 数据录入表单 ===
with st.form("gauge_form", clear_on_submit=True):
    st.subheader("📝 基础信息")

    col1, col2, col3 = st.columns(3)
    with col1:
        model = st.text_input("检具型号", placeholder="必填，如 T-2025")
    with col2:
        mat_num = st.text_input("物料编号", placeholder="选填")
    with col3:
        recorder = st.text_input("记录人", placeholder="必填，请输入姓名")

    desc = st.text_area("修改位置及说明", height=100, placeholder="请详细描述修改内容...")

    st.write("---")
    st.subheader("📸 现场影像")

    col_before, col_after = st.columns(2)
    with col_before:
        st.write("🔻 **修改前 (Before)**")
        files_before = st.file_uploader("上传修改前", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True, key="before")

    with col_after:
        st.write("✅ **修改后 (After)**")
        files_after = st.file_uploader("上传修改后", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True, key="after")

    st.write("")
    submitted = st.form_submit_button("🚀 提交记录")

    if submitted:
        if not model:
            st.warning("⚠️ 请填写【检具型号】")
        elif not recorder:
            st.warning("⚠️ 请填写【记录人】")
        elif not desc:
            st.warning("⚠️ 请填写【修改位置及说明】")
        else:
            with st.spinner("正在同步数据到飞书..."):
                token = get_feishu_token()
                if token:
                    # 上传图片
                    tokens_before = upload_images(files_before, token)
                    tokens_after = upload_images(files_after, token)

                    # === 关键修正 2：日期时间处理 ===
                    # 使用毫秒级时间戳，防止 DatetimeFieldConvFail 错误
                    current_timestamp = int(time.time() * 1000)

                    fields = {
                        "检具型号": model,
                        "物料编号": mat_num if mat_num else "-",
                        "记录人": recorder,
                        "修改说明": desc,
                        "提交时间": current_timestamp  # 传数字，飞书自动转日期
                    }

                    if tokens_before: fields["修改前图片"] = tokens_before
                    if tokens_after: fields["修改后图片"] = tokens_after

                    res = submit_to_feishu(fields)

                    if res.get("code") == 0:
                        st.success(f"✅ 提交成功！\n记录人：{recorder}\n型号：{model}")
                        st.balloons()
                    else:
                        st.error(f"❌ 提交失败: {res.get('msg')}")

