# DR2C 存档助手（Python 版）

当前版本：`1.0.0` · **旅途启程**

运行：

```text
python -m pip install -r requirements.txt
python app.py
```

构建 Windows 单文件版本：在 PowerShell 运行 `./build_release.ps1`，成品会输出到 `release/DR2C-Save-Station-1.0.0.exe`；PyInstaller 中间文件全部放在 `.temp/`。

开发目录中可能有已安装的 `vendor` 依赖；Git 不跟踪该目录，克隆仓库后按上面的命令安装即可。

这是 CustomTkinter 制作的像素风桌面工具。它会自动定位 `%APPDATA%\.madgarden\DR2C`；使用前请先完全退出游戏。

当前实现的功能：

- 英文与简体中文活动存档互转（0、1、2 槽，自动同步复制对应 `.slot` 菜单摘要文件）以及自建角色存档互转；
- 转换预览、覆盖确认、软件目录 `backups` 自动备份、原子替换与完整性校验；
- 活动/自建角色编辑：名字、HP 与生命上限、perk/trait 下拉选择、基础属性、bonus、已揭示开关、三格手持武器；
- 武器资料窗口：按中文/英文名搜索、按 TIER 筛选；详情页显示 Power、Cooldown、Knockback、弹药、地点和事件等 Wiki 数据。对于未收录武器可透明地手填运行时 ID；
- 活动存档编辑：带像素图标的物资、后备箱武器的添加/移除/更换/数量或充能、剩余天数、底盘与引擎当前值/上限；
- 全局升级存档：`gstats.save` 与 `gstats-mod.save` 的结构校验后互转；可一键把所有 `wins-*` 设为 1，或把全部 `perk-*` / `trait-*` 设为最高 3 级；
- 一键打开游戏存档目录；
- 内置使用说明、像素资源和刻晴彩蛋。

活动存档中混有 Forth 原始控制字节，程序只以二进制定点替换字段，绝不对整份存档做 UTF-8 重编码。遇到不在对照表内的 perk/trait 会停止转换，不会写出半转换文件。

全局升级页的一键模式解锁会覆盖原有 `wins-*` 通关次数（包括同名前缀的连胜记录）；PERK/TRAIT 全解锁也可能影响长期游玩的乐趣。两类操作均需要确认并会自动备份。

运行回归测试：

```text
python test_conversion.py
```

## 已测试版本

- 原版游戏：`20260727`
- 简体中文汉化补丁：`906.2`

其他游戏、补丁或 Mod 版本未经测试，不保证能够使用。武器 ID 偏移规则与公开发布注意事项见同目录 `readme.txt`。

## 开发者与社区

- 开发者：绯海·三代
- B站主页：[https://space.bilibili.com/1418606](https://space.bilibili.com/1418606)
- 加拿大维修之路 QQ 频道：[https://pd.qq.com/s/nfetjmmb](https://pd.qq.com/s/nfetjmmb)
- 汉化补丁与攻略：[B站动态下载页](https://www.bilibili.com/opus/852265599123849222)
- 全新 Mod 版本资源站：[https://dr2c.top/](https://dr2c.top/)

QQ群：1 群 `748853148`（快满了）、2 群 `634638288`、3 群 `923508276`、4 群 `908091369`。群会定时清理 1 级水友以留出新名额；频道不会清人，推荐优先同步加入，且请尽量不要重复添加群。
