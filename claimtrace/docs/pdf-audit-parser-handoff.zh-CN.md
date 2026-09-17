# PDF Audit：给 Zheng Fu 的 Parser 交接

> 进度更新：PR23 的 `b65f8e3` 已提供下面的元数据字段。PR20 分支已整合该提交并补上后端保存、读取和 Scholar 输入映射；本文件下面的字段需求保留作接口说明，不再是待开发任务。PR23 尚未合并 main，已知的两个 Parser 问题本次不处理。实际支持范围以 PR23 为准：APA 7 和标准 IEEE 元数据，其他格式保留原文、字段可为 null。

本周目标：上传论文 PDF → 提取文末 Reference List → Google Scholar 搜索 → 网页显示 Audit 结果。不调用 LLM，也不需要上传引用原论文。正文 claims 的工作独立进行，不是这条 Audit 链路的前置条件。

## 请 Parser 补充的内容

目前参考文献只有 `raw_text`，而 Sichen 的 `search_scholar(title, authors, year)` 需要独立标题。请在现有每条 reference 上增加以下字段，保留原文、编号和页码。

建议输出格式（请先确认字段名，并给一份真实 PDF 的样例）：

```json
{
  "source_file": "manuscript.pdf",
  "references": [
    {
      "raw_text": "[1] 原始完整引用文本",
      "number": 1,
      "page_start": 8,
      "page_end": 8,
      "title": "提取出的论文标题",
      "authors": ["Surname, Given name"],
      "year": 2020,
      "venue": "期刊或会议名称",
      "doi": ""
    }
  ],
  "warnings": []
}
```

- `title` 是搜索必需字段；提取不到时留空，不把整条引用当标题。
- `authors` 为字符串数组，建议使用 `姓, 名`；`year` 为整数或 `null`。
- `venue`、`doi` 能提取则提供，否则留空；不要用搜索结果反填原始输入字段。
- 提取失败的条目也保留 `raw_text`，便于显示和排查。
- 请同时更新 `extract_references()` 返回的 reference 对象和导出的 JSON，确保字段一致。

## 后端由 Hongyang 完成

后端负责保存和读取新增字段，传给 Scholar 搜索，再将结果返回前端。无需 Parser 实现搜索或五种 Audit 状态。

交付时请提供：代码分支/commit、一份真实 PDF 及对应 JSON，至少展示一条成功提取标题的引用和缺失字段的处理。之后一起验证网页端 PDF Audit。
