# WordPress Playground 上游分叉与发布产品档案

> 状态词只使用 PASS / FAIL / SKIP / BLOCKED / PENDING。此产品是 `web-runtime/monorepo`，不是插件或主题。该类型偏差是为了让既有 SOP 的来源锁、转换、可复现构建、Release 和公开回读门适用于浏览器运行时；插件/主题安装字段明确标为 SKIP，不伪装适用。

## 1. 产品边界

| 字段 | 值 |
|---|---|
| 产品名 | 文派 Playground |
| 产品类型 | `web-runtime/monorepo`（SOP 模板扩展；理由见上） |
| 产品负责人 | WenPai.org；执行责任人 `BLOCKED: FeiCode repository owner 尚未回读确认` |
| 产品仓库 | `https://feicode.com/WenPai-org/wordpress-playground` |
| 发布渠道 | FeiCode Release，不可变 `.tar.gz` + `.sha256` |
| code 范围 | 上游 website/self-hosted runtime 的源码构建、产品 overlay 与验证 included |
| docs 范围 | 产品档案、运维与 Release 说明 included；上游文档翻译 excluded |
| website 范围 | 产品源码中的 Playground website shell included；`play.wenpai.net` 首页、catalog、Blueprint 和插件资产由独立站点仓库维护 |
| 明确不做 | 不在镜像开发；不复制整个上游进产品仓库；不修改 hash/minified 产物；不自动直发生产；不修改 DNS、证书、数据库或账号权限 |

## 2. 来源、许可证与第三方资产

| 字段 | 值 |
|---|---|
| canonical upstream | `https://github.com/WordPress/wordpress-playground` |
| FeiCode mirror | `https://feicode.com/WPFork/wordpress-playground-upstream`（只读上游历史） |
| stable tag 规则 | 每 6 小时比较 canonical latest non-prerelease `vMAJOR.MINOR.PATCH` 与 mirror peeled target |
| tag 信任方式 | 公开 Git refs + peeled exact commit；`BLOCKED: 未建立 tag 签名/维护者 allowlist` |
| 当前 tag / commit | `v3.1.49` / `4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d`；tag object `9774d4a942f671a089a31b87ee93b81aaea64170` |
| canonical/mirror 对账 | `git ls-remote --tags <url>`；`tools/stable-watcher.py` 比较 peeled target |
| 真源 | canonical GitHub exact commit archive，剥离单一顶层目录；mirror exact tree 必须产生同一 manifest SHA |
| submodule / Git LFS | Git tree 未发现 `.gitmodules`；LFS 仍由候选源扫描门检查，发现 pointer 即 BLOCKED |
| 构建和 lockfile | upstream `package-lock.json`；Node `22.23.0`；npm `10.9.2` |
| 主许可证 | GPL-2.0-or-later，原文保存在 `LICENSE` |
| 必须保留 | `LICENSE`, `NOTICE`, `UPSTREAM.md`, `upstream-lock.json` |
| attribution/copyright | 上游与依赖贡献者保留；下游变更归 WenPai 贡献者；不得暗示 WordPress Foundation 背书 |
| 商标/再分发 | WordPress 商标需遵守官方政策；`BLOCKED: 首次公开 Release 前须完成人工商标与二进制再分发复核` |
| 第三方资产 | `BLOCKED: 字体、PHP/WASM、WordPress archives、SQLite、Node 包和生成资产的逐项 notice 尚未完成人工复核` |
| SBOM | Release 内 `sbom-summary.json`；仅 npm lock 摘要，未知 license 保留 `UNKNOWN` 并阻断审计结论 |

## 3. 产品身份与兼容模式

| 身份面 | 上游 | 产品 |
|---|---|---|
| 名称 | WordPress Playground | 文派 Playground |
| 仓库 | WordPress/wordpress-playground | WenPai-org/wordpress-playground |
| website shell locale | 上游默认/查询参数行为 | 默认 `zh_CN`，显式 `ui-language` 独立控制 |
| WordPress instance locale | `language` 参数 | 默认 `zh_CN`，与 shell locale 分开 |
| URL/下载源 | 官方 runtime/workflow artifacts | FeiCode 不可变产品 Release |
| slug/ZIP/text-domain/PHP prefix | SKIP: 非插件/主题 | SKIP: 非插件/主题 |
| REST/block/option namespace | 保留上游运行时协议 | 保留协议兼容；品牌配置不得改协议键 |

- 兼容模式：`compatibility-preserving`，保留 Blueprint、query API、worker/SW 与 runtime URL 协议。
- 并存策略：不同 origin 可并存；同 origin 替换必须通过版本化 runtime manifest 和 SW/cache 升级测试。
- 数据迁移：不迁移 WordPress 内容；旧 SW/cache 有显式清理与回滚门。
- 版本映射：upstream `X.Y.Z` -> downstream `X.Y.Z.N`，首次为 `3.1.49.1`。

## 4. 转换契约

转换不是全局品牌 `sed`。`overlays/files/` 只保存小型产品源码文件，`overlays/patches/*.patch` 保存可审阅源码补丁；`tools/apply-overlay.py` 在隔离的 exact upstream tree 上先 `git apply --check` 再应用。

允许保留上游引用：`LICENSE`、`NOTICE`、`UPSTREAM.md`、copyright、WordPress Playground 协议/API 名称、canonical/mirror 来源 URL、依赖 attribution。其他用户可见上游 shell 品牌残留必须由 residual 检查报告，不能静默放行。

保护资产：`.forgejo/workflows/**`、`config/**`、`overlays/**`、`tools/**`、`tests/**`、`docs/**`、`LICENSE`、`NOTICE`、`UPSTREAM.md`、`upstream-lock.json`。上游若新增同路径，candidate 必须 BLOCKED，不允许覆盖。

来源排除：`.git/**`、`node_modules/**`、缓存、runner 状态、凭证、本地构包；上游测试和 lockfile保留在临时构建树，不复制进产品 Git。

## 5. 确定性与锁

| 字段 | 值 |
|---|---|
| lock | `upstream-lock.json` |
| source 摘要 | SHA-256 over canonical JSON of normalized `path,type,executable,content SHA`; 当前 4977 条 |
| transform 摘要 | `config/`, `overlays/`, apply/build/security/manifest 工具；`tools/transform-hash.py` |
| mtime | `SOURCE_DATE_EPOCH=1786355284`（upstream commit timestamp） |
| 权限/排序 | 目录 0755；文件 0644；原可执行文件 0755；UTF-8 bytewise 路径顺序 |
| archive | deterministic PAX tar + gzip level 9 + empty gzip filename + fixed mtime/uid/gid |
| 双构建 | 两个隔离目录运行 `tools/build-runtime.py`，比较 tar.gz SHA 与 runtime manifest SHA |
| symlink | source manifest 仅记录树内 target；产品/runtime 构包默认全部拒绝；绝对/越界链接必 FAIL |
| 大小写/Unicode | casefold 与 NFC 冲突必 FAIL |
| 包内 SHA | `runtime.json.artifact_sha256=null`；包外 runtime.json 与 `.sha256` authoritative |
| tag 后源码 | main 后续翻译/工具变更进入下一 downstream 尾号；旧 tag 与附件不可变 |

## 6. 中文策略

| 字段 | 值 |
|---|---|
| locale | website shell `zh_CN`；WordPress `language=zh_CN`；显式 `ui-language` 可选 |
| catalog | 产品源码层结构化字典；不编辑 minified/hash JS |
| 覆盖面 | 加载页、Dock、站点管理、设置、对话框、错误、保存/下载、导航、可访问名称 |
| 提取/检查 | translations workflow 提取当前源码，报告唯一字符串、引用数、缺失与 placeholder/token |
| zh_TW | `PENDING: 首次产品只要求 zh_CN；新增前不得宣称覆盖` |
| GlotPress | `SKIP: website shell 当前使用仓库内审核字典，未接生产 GlotPress` |
| 文档翻译 | excluded |
| release 降级 | 缺失键回退上游英文并 WARN；不得伪造 100%；稳定 zh_CN 断言为阻断门 |
| 状态 | `evidence/translation-status.json` 由 workflow 生成 |

必须保护 placeholder、HTML、URL、query key、Blueprint JSON、printf/brace token、快捷键与 aria 属性结构。

## 7. CI/CD 合同

| Workflow | 触发 | runner | 权限 | 判据 |
|---|---|---|---|---|
| `ci.yml` | push/PR | `ubuntu-latest`（`BLOCKED: FeiCode runner label 待回读`） | contents read | Python 单测、source/transform/security、overlay residual、build contract |
| `translations.yml` | manual + 每日错峰 | 同上 | contents read；候选写入走 PR | catalog 非零提取、placeholder/token、zh_CN；失败 WARN且不发 Release |
| `upstream-sync.yml` | manual + 每 6 小时 | 同上 | contents/pull request write | stable detection、canonical/mirror peeled 对账、source hash、candidate PR |
| `release.yml` | tag/manual | 同上 | contents/release write | exact product SHA、双构建、非零测试、附件、匿名公开回读 SHA |

- 外部 action：`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`，禁止浮动 tag。
- secrets 仅列名：`FEICODE_TOKEN`；内容不得输出。
- 网络：连接 10–15 秒、请求 30–300 秒、有界失败；Git 操作 60 秒脚本超时。
- mutation lock：translations 与 upstream-sync 共用 `wenpai-playground-product-mutation` concurrency；机器人只建 candidate branch/PR，禁止 force push。
- schedule：upstream `17 */6 * * *`；translations `43 2 * * *`；Release 无 schedule。
- 通知：`BLOCKED: FeiCode 连续失败通知通道和阈值未配置`；workflow artifact 保留 last report。
- Release 重跑：完整同 SHA验证退出；缺附件补齐；同名不同 SHA fail closed；tag 指向不同 commit停止。
- 自动公开 Release：false；本次首次 Release 单次授权不延伸到后续版本。
- branch/tag protection：`BLOCKED: 仓库创建后须回读 main保护、禁止 force push、tag不可移动和 token 最小权限`。

## 8. web-runtime 验证矩阵

| 检查 | 命令/证据 | 状态 |
|---|---|---|
| 工具 unit | `python3 -m unittest discover -s tests -p 'test_*.py' -v`，必须非零 | PENDING |
| upstream lint/type/unit/relevant | exact upstream package scripts；逐项记录实际样本和未跑项 | PENDING |
| source/transform/protected/residual | manifest、transform hash、overlay report和冲突检查 | PENDING |
| 双构建一致 | 两个隔离 worktree tar SHA + manifest SHA | PENDING |
| runtime manifest/SHA/SBOM | `tools/build-runtime.py` | PENDING |
| HTML/worker/SW/JS/CSS/WASM MIME | staging/production HTTP probes，非零 URL | PENDING |
| WordPress 7.0/PHP WASM | exact published assets启动 | PENDING |
| Blueprint schema/真实启动 | 单插件、组合、多站点、Minimal Admin、自定义后台分层样本 | PENDING |
| locale | site/admin `zh_CN` 与 shell stable strings分别断言 | PENDING |
| browsers | Chromium desktop、390px、Firefox | PENDING |
| cache/SW | cold、old SW upgrade、clear/reload、query差异 | PENDING |
| fault UX | network、Blueprint、ZIP 404/损坏中文错误 | PENDING |
| console/pageerror | 已知 upstream warning 单列 | PENDING |
| security/supply chain | secret/path/symlink/LFS/NOTICE/dependency diff | `BLOCKED: NOTICE 全审计未完成` |
| public readback | anonymous Release artifact SHA | PENDING |
| plugin/theme install | 非此产品类型 | SKIP |

PASS 必须记录 exact product SHA、命令/run、日期和非零样本。0 样本只能 SKIP/BLOCKED。

## 9. 发布、部署与回退

| 字段 | 值 |
|---|---|
| tag | `vX.Y.Z.N`；首次 `v3.1.49.1` |
| artifact | `wenpai-wordpress-playground-X.Y.Z.N.tar.gz` + `.sha256` + runtime/SBOM metadata |
| Release | `https://feicode.com/WenPai-org/wordpress-playground/releases/tag/<tag>` |
| tag验证 | `git ls-remote <product> refs/tags/<tag> refs/tags/<tag>^{}` 对 exact product SHA |
| updater | play.wenpai.net 仅引用已验证 FeiCode Release URL + SHA |
| production | 属本次任务但仍是独立可审计 A 级变更；staging展开、显式 manifest受控切换，不对站点根盲目 delete |
| previous | 官方 runtime v3.1.49 artifact SHA `5ea2b9d227cd817d7fa1db47dc5d0a9577239b99d87e07bd4caa4f3a6effd44c`（部署前须现场回读） |
| backup/rollback | `BLOCKED: 本次时间戳生产备份和可执行回滚脚本尚未创建；旧备份不能替代` |

## 10. 运行记录

| 日期 | upstream | product | CI/Release | artifact SHA | translation | 结论 |
|---|---|---|---|---|---|---|
| 2026-08-11 | `v3.1.49@4d9c20678ca7cbd7bb881dc0cc5f4e5739f6cc2d` | `PENDING: candidate exact SHA/tag` | 本地工具实现中；公开 run `PENDING` | `PENDING` | zh_CN 源码 overlay `PENDING` | PENDING |

## 11. 偏差记录

| 日期 | 原规则 | 偏差 | 原因 | 修订/回退 | 批准/任务 |
|---|---|---|---|---|---|
| 2026-08-11 | SOP 产品类型仅 plugin/theme | 使用 web-runtime/monorepo 验证矩阵 | Playground 是浏览器 runtime + monorepo，插件门不适用 | 只扩展产品档案；保留 SOP 来源锁/转换/Release铁律 | 本次委派任务 |
