# Excel 智能清洗工具

一个基于 Streamlit 的在线 Excel 清洗工具，支持：
- 删除括号内容（英文/中文）
- 删除指定关键词（全局）
- 条件性删除文本（例如：当分类为“产品关键词”且词组包含“A Line”时，删除“A Line”）
- 根据关键词删除整行
- 根据字符长度删除整行
- 删除纯英文行
- 
## 本地运行（可选）
如果你想在本地运行：
```bash
pip install -r requirements.txt
streamlit run excel_cleaner_app.py
