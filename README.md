# 文派 WordPress Playground

这是文派维护的 WordPress Playground 网站运行时产品仓库。它不是
WordPress 插件或主题，也不承载 `play.wenpai.net` 的首页、Blueprint 和
插件目录。

## 仓库边界

- canonical upstream：`WordPress/wordpress-playground`
- 只读浅层镜像：`WPFork/wordpress-playground-upstream`
- 产品转换、中文外壳、构建和 Release：本仓库
- 站点业务集成与生产部署引用：`WenPai-org/play.wenpai.net`

上游许可证、版权和商标归属保持不变，见 `LICENSE`、`NOTICE`、
`UPSTREAM.md` 与 `docs/licenses/`。文派品牌配置位于 `config/brand.json`；
用户界面语言和 WordPress 实例语言是两个独立参数。

## 确定性输入

`upstream-lock.json` 固定上游 tag/commit、规范化源码摘要、转换摘要、
Node/npm、`SOURCE_DATE_EPOCH`、PHP-WASM、WP-CLI 与生成资产。构建流程从
exact upstream archive 创建两个独立源码树，分别安装依赖、应用 overlay、
构建和规范化，再比较完整 runtime manifest 与归档 SHA-256。

## 自动化

- `ci`：产品工具测试、上游 website lint/type/unit、两次独立构建、notice、
  runtime 和归档一致性。
- `translations`：中文 catalog、placeholder/token、未翻译残留检查。
- `upstream-sync`：每 6 小时对账最新非预发布稳定 tag，只生成候选分支/PR；
  tag 移动或镜像不一致时 fail closed。
- `release`：只接受四段下游 tag，从 draft Release 上传、逐附件校验、公开后
  匿名回读；同名不同 SHA 停止。

公开 Release 与生产部署不是自动 watcher 的一部分。生产只允许
`play.wenpai.net` 消费已经验证的不可变 Release artifact，并按其显式
runtime manifest 备份、切换与回滚。

## 本地工具门

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/localization_overlay.py catalog-check
python3 tools/transform-hash.py -o evidence/transform-digest.json
python3 tools/security-scan.py .
```

完整 website 构建以 `.forgejo/workflows/ci.yml` 为准；它需要锁定版本的
Node/npm 和上游 monorepo，不能用工具单测代替。
