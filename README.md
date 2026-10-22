# myskill

个人私有 Agent Skills 仓库 (Private Skills Repository)。

---

## 包含的 Skills (Catalog)

### 1. `sep-sop` (v1.2.0, alias: `seo-sop`)
**Description:** Plan, validate, build, and operate SEO-focused browser-game sites. Use for game-site keyword research, a single-site build, or a measured multi-site portfolio; do not treat deployment or indexing as a promise of traffic or revenue.

- **关键词双轨挖掘流水线**：
  - **新词趋势轨**：直连 Google Trends 官方接口（$0，无第三方依赖），抓取飙升榜并沉淀到持久化词库。
  - **老词长尾与竞品轨**：直连 DataForSEO v3 REST API（支持 Labs Keyword Ideas, Ranked Keywords, Google Ads Search Volume, Bulk KD, Organic SERP, Backlinks Summary）。
  - **成本透明化**：强制使用 `--allow-paid` 进行显式付费授权，自动统计并打印每次查询产生的真实美金成本，POST 请求防重试安全机制。
- **业务假说与阶段门禁 (Cohort & Stage Gates)**：
  - 拒绝盲目铺量，将“200 站”作为产能压测假说，设立 3~5 款游戏的 Small Pilot 试点。
  - 依照技术、收录、互动、广告、经济五个维度执行 Expand / Hold / Stop 决策。
- **合规性与安全风控**：
  - 开源协议与商标、美术素材独立审查。
  - 广告代码防误触（严禁置于可玩画布上，留出安全间距，遵循 GDPR/CCPA Consent）。
  - 外部危险动作（域名购买、公开 Repo 创建、生产发布）必须单独获得显式授权。
- **美学与可用性**：
  - 提供 `aesthetic-checklist.md` 与参考站点指引，消除多重卡片嵌套与臃肿排版。

---

## 目录结构 (Directory Structure)

```text
myskill/
├── .gitignore
├── README.md
└── skills/
    ├── sep-sop/
    │   ├── SKILL.md            # Skill 主入口规范
    │   ├── CHANGELOG.md        # 版本演进记录
    │   ├── assets/             # 词根库等静态资源
    │   ├── evals/              # 行为测试用例与触发词 (evals.json, triggers.json)
    │   ├── references/         # 详细 SOP、阶段门禁、美学检查表与参考站
    │   └── scripts/            # DataForSEO 原生客户端、Google Trends 抓取、流水线脚本
    └── seo-sop -> sep-sop      # 软链接别名
```

---

## 安装与配置 (Installation)

### 方式 1：使用 Skills CLI
```bash
npx skills add seraseraqqq/myskill
```

### 方式 2：Git 克隆 / 软链接
在项目工作区或全局 Agent 目录中引入：
```bash
# 全局 Agent 引入
ln -s /path/to/myskill/skills/sep-sop ~/.agents/skills/sep-sop

# 或在具体项目中引入
mkdir -p .agents/skills
ln -s /path/to/myskill/skills/sep-sop .agents/skills/sep-sop
```

### 环境变量配置 (Environment Variables)
运行 DataForSEO 付费数据挖掘脚本时需配置：
```bash
export DATAFORSEO_LOGIN="your_login"
export DATAFORSEO_PASSWORD="your_password"
export DATAFORSEO_LOCATION_CODE="2840"  # 默认美国 (US)
export DATAFORSEO_LANGUAGE_CODE="en"    # 默认英语 (en)
export KEYWORD_LEDGER="/path/to/ledger.json" # 可选，自定义持久化词库路径
```
