import streamlit as st
import pandas as pd
import re
from io import BytesIO
#在控制台输入指令：streamlit run excel_cleaner_app.py

# ---------- 辅助函数 ----------
def remove_brackets_from_text(text):
    """删除文本中的英文括号()或中文括号（）及括号内内容"""
    if not isinstance(text, str):
        return text
    pattern = r'\(.*?\)|（.*?）'
    return re.sub(pattern, '', text)

def remove_keywords_from_text(text, keywords, case_insensitive=True):
    """删除文本中出现的指定关键词（子串匹配）"""
    if not isinstance(text, str):
        return text
    result = text
    for kw in keywords:
        if case_insensitive:
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            result = pattern.sub('', result)
        else:
            result = result.replace(kw, '')
    return result

def remove_colon_and_before(text, handle_english=False):
    """
    删除第一个中文冒号“：”及其之前的所有字符，保留冒号后的内容。
    若 handle_english=True，同时处理英文冒号“:”。
    如果没有冒号，返回原文本。
    """
    if not isinstance(text, str):
        return text
    idx = text.find('：')
    if idx == -1 and handle_english:
        idx = text.find(':')
    if idx != -1:
        return text[idx+1:]
    return text

def contains_keyword(text, keywords, case_insensitive=True):
    if not isinstance(text, str):
        return False
    if case_insensitive:
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
    else:
        for kw in keywords:
            if kw in text:
                return True
    return False

def is_pure_english(text):
    """判断是否为纯英文（不含任何中文字符）"""
    if not isinstance(text, str):
        return False
    if re.search(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text):
        return False
    return True

def apply_conditional_removal(df, rules):
    """
    根据规则列表对 DataFrame 进行条件性文本删除
    """
    for rule in rules:
        cond_col = rule['condition_col']
        cond_val = rule['condition_value']
        check_col = rule['check_col']
        check_kw = rule['check_keyword']
        target_col = rule['target_col']
        remove_txt = rule['remove_text']
        case_ins = rule.get('case_insensitive', True)

        if cond_col not in df.columns or check_col not in df.columns or target_col not in df.columns:
            st.warning(f"规则跳过：列 '{cond_col}', '{check_col}', '{target_col}' 中有不存在的列")
            continue

        cond_mask = (df[cond_col] == cond_val)
        check_mask = df[check_col].astype(str).apply(
            lambda x: contains_keyword(x, [check_kw], case_ins)
        )
        mask = cond_mask & check_mask

        if mask.any():
            def remove_func(text):
                if not isinstance(text, str):
                    return text
                if case_ins:
                    pattern = re.compile(re.escape(remove_txt), re.IGNORECASE)
                    return pattern.sub('', text)
                else:
                    return text.replace(remove_txt, '')
            df.loc[mask, target_col] = df.loc[mask, target_col].apply(remove_func)
    return df

def remove_duplicates(df, col_name, keep='first'):
    """
    基于指定列删除重复行，比较时不区分大小写。
    keep: 'first' 或 'last'，保留第一次或最后一次出现的行。
    返回 (去重后的df, 删除的行数)
    """
    if col_name not in df.columns:
        st.warning(f"列 '{col_name}' 不存在，跳过重复行删除。")
        return df, 0

    # 创建临时小写列（不修改原始列）
    temp_col = '_temp_lower_' + col_name
    df[temp_col] = df[col_name].astype(str).str.lower()
    
    # 基于临时列去重，保留索引
    if keep == 'first':
        keep_idx = df.groupby(temp_col, as_index=False).first().index
    else:  # 'last'
        keep_idx = df.groupby(temp_col, as_index=False).last().index
    
    result_df = df.loc[keep_idx].drop(columns=[temp_col])
    removed = len(df) - len(result_df)
    return result_df, removed

def process_excel(df, target_col, options, conditional_rules):
    """
    主处理流程
    """
    if target_col not in df.columns:
        st.error(f"主目标列 '{target_col}' 不存在于表格中")
        return df, 0, 0

    original_rows = len(df)

    # 1. 文本清理（不删行）
    if options['clean_brackets']:
        df[target_col] = df[target_col].apply(remove_brackets_from_text)

    if options['remove_keywords']:
        kw_list = options['remove_keywords']
        case_ins = options['remove_keywords_case_insensitive']
        df[target_col] = df[target_col].apply(lambda x: remove_keywords_from_text(x, kw_list, case_ins))

    if conditional_rules:
        df = apply_conditional_removal(df, conditional_rules)

    if options['remove_colon_col'] and options['remove_colon_col'] in df.columns:
        col = options['remove_colon_col']
        df[col] = df[col].apply(lambda x: remove_colon_and_before(x, options['remove_colon_english']))
        st.info(f"已对列 '{col}' 执行删除冒号及之前字符的操作。")

    # 2. 删除整行的条件
    delete_mask = pd.Series([False] * len(df))

    if options['delete_keywords']:
        kw_mask = df[target_col].apply(
            lambda x: contains_keyword(x, options['delete_keywords'], options['delete_case_insensitive'])
        )
        delete_mask |= kw_mask

    if options['max_length'] is not None and options['max_length'] > 0:
        len_mask = df[target_col].astype(str).apply(lambda x: len(x) > options['max_length'])
        delete_mask |= len_mask

    if options['remove_pure_english']:
        eng_mask = df[target_col].apply(is_pure_english)
        delete_mask |= eng_mask

    df_temp = df[~delete_mask]
    deleted_by_mask = delete_mask.sum()

    # 3. 删除重复行（基于指定列，不区分大小写）
    deleted_by_dup = 0
    if options['deduplicate_col'] and options['deduplicate_col'] in df_temp.columns:
        df_temp, deleted_by_dup = remove_duplicates(df_temp, options['deduplicate_col'], options['deduplicate_keep'])
        if deleted_by_dup > 0:
            st.info(f"基于列 '{options['deduplicate_col']}' 删除了 {deleted_by_dup} 行重复数据（保留 {options['deduplicate_keep']}，不区分大小写）。")

    deleted_rows = deleted_by_mask + deleted_by_dup
    return df_temp, deleted_rows, original_rows

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Excel 智能清洗工具", layout="wide")
st.title("📎 Excel 行清洗工具")
st.markdown("支持：删除括号内容、全局删除关键词、条件性删除文本、删除冒号及之前字符、关键词删行、长度删行、纯英文删行、删除重复行（不区分大小写）")

uploaded_file = st.file_uploader("上传 Excel 文件 (.xlsx 或 .xls)", type=['xlsx', 'xls'])

# 初始化 session_state 存储条件规则
if 'conditional_rules' not in st.session_state:
    st.session_state.conditional_rules = []

def add_rule():
    st.session_state.conditional_rules.append({
        'condition_col': '',
        'condition_value': '',
        'check_col': '',
        'check_keyword': '',
        'target_col': '',
        'remove_text': '',
        'case_insensitive': True
    })

def remove_rule(index):
    st.session_state.conditional_rules.pop(index)

if uploaded_file:
    try:
        excel_data = pd.ExcelFile(uploaded_file)
        sheet_names = excel_data.sheet_names
        sheet_name = st.selectbox("选择工作表", sheet_names)
        df = pd.read_excel(uploaded_file, sheet_name=sheet_name, dtype=str, keep_default_na=False)
        st.success(f"成功加载工作表 '{sheet_name}'，共 {df.shape[0]} 行，{df.shape[1]} 列")
    except Exception as e:
        st.error(f"读取文件失败：{e}")
        st.stop()

    columns = df.columns.tolist()
    target_col = st.selectbox("选择要操作的主目标列（用于关键词/长度/纯英文判断）", columns)

    # 侧边栏设置
    st.sidebar.header("单元格文本清理（不删行）")
    clean_brackets = st.sidebar.checkbox("删除括号内容（英文/中文括号及内部文本）", value=False)

    st.sidebar.subheader("全局删除指定关键词（仅修改文本）")
    use_remove_keywords = st.sidebar.checkbox("启用全局删除关键词")
    remove_keywords_list = []
    remove_case_insensitive = True
    if use_remove_keywords:
        kw_remove_str = st.sidebar.text_input("要删除的关键词（多个用英文逗号分隔）", placeholder="例如：test,测试,删除")
        if kw_remove_str.strip():
            remove_keywords_list = [k.strip() for k in kw_remove_str.split(',') if k.strip()]
        remove_case_insensitive = st.sidebar.checkbox("不区分大小写", value=True)

    # 条件性删除文本
    st.sidebar.header("条件性删除文本（仅修改文本）")
    st.sidebar.markdown("例如：如果【分类】列等于“产品关键词”，且【词组】列包含“A Line”，则从【词组】列中删除“A Line”")
    
    for i, rule in enumerate(st.session_state.conditional_rules):
        with st.sidebar.expander(f"规则 {i+1}"):
            col1, col2 = st.columns(2)
            with col1:
                rule['condition_col'] = st.selectbox("条件列", options=columns, key=f"cond_col_{i}", index=columns.index(rule['condition_col']) if rule['condition_col'] in columns else 0)
                rule['condition_value'] = st.text_input("条件值", value=rule['condition_value'], key=f"cond_val_{i}")
                rule['check_col'] = st.selectbox("检查列（包含关键词）", options=columns, key=f"check_col_{i}", index=columns.index(rule['check_col']) if rule['check_col'] in columns else 0)
                rule['check_keyword'] = st.text_input("检查关键词", value=rule['check_keyword'], key=f"check_kw_{i}")
            with col2:
                rule['target_col'] = st.selectbox("目标列（删除文本的列）", options=columns, key=f"target_col_{i}", index=columns.index(rule['target_col']) if rule['target_col'] in columns else 0)
                rule['remove_text'] = st.text_input("要删除的文本", value=rule['remove_text'], key=f"remove_txt_{i}")
                rule['case_insensitive'] = st.checkbox("不区分大小写", value=rule['case_insensitive'], key=f"case_ins_{i}")
            if st.button("删除此规则", key=f"del_rule_{i}"):
                remove_rule(i)
                st.rerun()
    if st.sidebar.button("➕ 添加条件规则"):
        add_rule()
        st.rerun()

    # 删除冒号及之前字符
    st.sidebar.subheader("删除冒号及之前字符（仅修改文本）")
    use_colon_remove = st.sidebar.checkbox("启用删除冒号及之前字符")
    colon_col = None
    colon_english = False
    if use_colon_remove:
        colon_col = st.sidebar.selectbox("选择要处理的列（例如 B 列）", columns, index=min(1, len(columns)-1) if len(columns)>1 else 0)
        colon_english = st.sidebar.checkbox("同时处理英文冒号 ':'", value=False)
        st.sidebar.caption("将删除第一个中文冒号'：'及其之前的所有字符，保留冒号后的内容。")

    # 删除整行的条件
    st.sidebar.header("删除整行的条件（满足任一即删除）")
    use_delete_keywords = st.sidebar.checkbox("根据关键词删除整行")
    delete_keywords_list = []
    delete_case_insensitive = True
    if use_delete_keywords:
        kw_delete_str = st.sidebar.text_input("关键词（多个用英文逗号分隔）", placeholder="例如：不合格,error")
        if kw_delete_str.strip():
            delete_keywords_list = [k.strip() for k in kw_delete_str.split(',') if k.strip()]
        delete_case_insensitive = st.sidebar.checkbox("不区分大小写", value=True)

    use_length = st.sidebar.checkbox("根据字符长度删除整行")
    max_len = None
    if use_length:
        max_len = st.sidebar.number_input("最大允许长度（超过则删除）", min_value=1, value=10, step=1)

    remove_pure_english = st.sidebar.checkbox("删除纯英文行（不含任何中文字符）")

    # 删除重复行（不区分大小写）
    st.sidebar.subheader("删除重复行（不区分大小写）")
    use_deduplicate = st.sidebar.checkbox("启用基于某列删除重复行")
    dedup_col = None
    dedup_keep = 'first'
    if use_deduplicate:
        dedup_col = st.sidebar.selectbox("选择用于判断重复的列（例如 A 列）", columns)
        dedup_keep = st.sidebar.radio("保留哪一行", options=['first', 'last'], index=0, horizontal=True)
        st.sidebar.caption("比较时将忽略大小写（例如 'abc' 和 'ABC' 视为重复）。")

    if st.button("🚀 开始处理"):
        options = {
            'clean_brackets': clean_brackets,
            'remove_keywords': remove_keywords_list if remove_keywords_list else None,
            'remove_keywords_case_insensitive': remove_case_insensitive,
            'delete_keywords': delete_keywords_list if delete_keywords_list else None,
            'delete_case_insensitive': delete_case_insensitive,
            'max_length': max_len if use_length else None,
            'remove_pure_english': remove_pure_english,
            'remove_colon_col': colon_col if use_colon_remove else None,
            'remove_colon_english': colon_english,
            'deduplicate_col': dedup_col if use_deduplicate else None,
            'deduplicate_keep': dedup_keep
        }
        # 过滤条件规则中不完整的
        valid_rules = []
        for rule in st.session_state.conditional_rules:
            if (rule['condition_col'] and rule['condition_value'] and rule['check_col'] and
                rule['check_keyword'] and rule['target_col'] and rule['remove_text']):
                valid_rules.append(rule)
            else:
                st.warning(f"跳过不完整的条件规则：所有字段都必须填写")

        try:
            result_df, deleted_rows, original_rows = process_excel(df.copy(), target_col, options, valid_rules)

            st.subheader("处理结果")
            col1, col2, col3 = st.columns(3)
            col1.metric("原始行数", original_rows)
            col2.metric("删除行数", deleted_rows, delta=f"-{deleted_rows}")
            col3.metric("剩余行数", len(result_df))

            st.subheader("预览处理后的数据（前5行）")
            st.dataframe(result_df.head())

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                result_df.to_excel(writer, index=False, sheet_name=sheet_name)
            output.seek(0)

            st.download_button(
                label="📥 下载处理后的 Excel 文件",
                data=output,
                file_name=f"cleaned_{uploaded_file.name}",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"处理出错：{e}")
