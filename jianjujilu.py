import streamlit as st
import datetime
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


# === 2. 飞书 API 工具函数 (保持不变) ===

def get_feishu_token():
    """获取飞书访问凭证"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
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

    progress_text = st.empty()

    for i, file_obj in enumerate(file_list):
        progress_text.text(f"正在上传第 {i + 1}/{len(file_list)} 张图片...")
        files = {
            'file_name': ('image.jpg', file_obj, file_obj.type),
            'parent_type': (None, 'bitable_image'),
            'parent_node': (None, st.secrets["feishu"]["app_token"]),
            'size': (None, str(file_obj.size))
        }
        try:
            r = requests.post(upload_url, headers=headers, files=files)
            res = r.json()
            if res.get("code") == 0:
                tokens.append({"file_token": res["data"]["file_token"]})
            else:
                st.warning(f"图片上传失败: {res.get('msg')}")
        except Exception:
            pass

    progress_text.empty()
    return tokens


def submit_to_feishu(data_fields):
    """提交数据"""
    token = get_feishu_token()
    if not token: return False

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


# === 3. 数据录入表单 (已更新) ===
with st.form("gauge_form", clear_on_submit=True):
    st.subheader("📝 基础信息")

    # 👇 更新点：改为3列布局，加入记录人
    col1, col2, col3 = st.columns(3)
    with col1:
        model = st.text_input("检具型号", placeholder="必填，如 T-2025")
    with col2:
        mat_num = st.text_input("物料编号", placeholder="选填")
    with col3:
        recorder = st.text_input("记录人", placeholder="必填，请输入姓名")

    # 修改说明区域
    desc = st.text_area("修改位置及说明", height=100, placeholder="请详细描述修改内容...")

    st.write("---")
    st.subheader("📸 现场影像")

    col_before, col_after = st.columns(2)
    with col_before:
        st.write("🔻 **修改前 (Before)**")
        files_before = st.file_uploader("上传修改前", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True,
                                        key="before")

    with col_after:
        st.write("✅ **修改后 (After)**")
        files_after = st.file_uploader("上传修改后", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True,
                                       key="after")

    st.write("")
    submitted = st.form_submit_button("🚀 提交记录")

    if submitted:
        # 👇 校验逻辑增加“记录人”
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
                    tokens_before = upload_images(files_before, token)
                    tokens_after = upload_images(files_after, token)

                    # 👇 组装数据，增加“记录人”字段
                    fields = {
                        "检具型号": model,
                        "物料编号": mat_num if mat_num else "-",
                        "记录人": recorder,  # 新增字段
                        "修改说明": desc,
                        "提交时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    if tokens_before: fields["修改前图片"] = tokens_before
                    if tokens_after: fields["修改后图片"] = tokens_after

                    res = submit_to_feishu(fields)

                    if res.get("code") == 0:
                        st.success(f"✅ 提交成功！\n记录人：{recorder}\n型号：{model}")
                        st.balloons()
                    else:
                        st.error(f"❌ 提交失败: {res.get('msg')}")