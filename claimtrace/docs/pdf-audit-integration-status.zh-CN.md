# PR20：PDF Audit 接线进度

## 已完成

- 网页现有的 PDF 上传 / Manage papers / Run audit 入口接入后端 Audit。
- 保存并读取 Parser 的 title、authors、year、venue、doi，同时保留原文、编号、页码。
- 旧版 raw-text 缓存通过 Parser 补元数据，不重新转换 PDF；显式 null 保留。
- 元数据交给 Sichen 的 Scholar 搜索，再通过现有比对逻辑生成五种状态并保存报告。
- IEEE 作者首字母格式在查询边界转换为姓氏，原始作者字段不变。
- 缺标题条目保留为 Needs review；空引用列表不显示全部匹配成功。
- 固定 bibtexparser 为兼容 scholarly 的 1.x，避免新安装环境导入失败。

## 依赖与范围

PR20 分支已整合 PR23 的 b65f8e3 作为依赖，PR23 本身没有合并到 main。
因此当前 PR20 diff 包含 Parser 依赖代码；不要绕过 PR23 的审核直接合并 PR20。
之前讨论的两个 Parser 问题暂不修复。本轮没有接入 LLM。

## 验证

- 152 项测试通过：全部 backend 测试、Scholar/适配器测试、Reference List Parser 测试。
- 合成 IEEE PDF 实际经过上传、OpenDataLoader 转换、引用提取、Audit 和报告读回；仅外部搜索响应使用替身。
- 集成测试检查真实查询构造、元数据落盘、旧缓存升级和重复读取。
- 前端 TypeScript / Vite 生产构建、ESLint、改动 Python 文件 Ruff 通过。
- 前端验证使用 pnpm 安装 package.json 范围内依赖；没有修改 package-lock.json。

## 仍待联调

一次真实 Scholar 查询（Attention is all you need，2017）在 45 秒内未返回，测试进程被终止。
这不是 NOT_FOUND，也不证明文献不存在。当前 adapter 仍同步等待 Engine 返回，45 秒限制仅用于此次探测，生产请求尚无整体截止时间。
需要与 Sichen 确认可用网络环境及超时处理后，完成真实 PDF 的浏览器端联合验收。
本次没有完成浏览器手动端到端验收，也不能将模拟搜索测试当成真实联网成功。

PR20 保持 Draft，暂不合并。
