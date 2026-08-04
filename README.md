# DR2C-SaveEditor

Death Road to Canada 的简体中文存档转换与编辑工具。用于在英文原版和简体中文汉化版之间转移存档，也可以直接编辑已开局存档、自建角色和全局升级记录。

当前版本：**1.0.0 · 旅途启程**

## 功能

- 英文版与中文版活动存档互转：支持 `0`、`1`、`2` 三个存档位，并同步复制对应的 `.slot` 菜单摘要文件；
- 自建角色存档互转：支持 `custchars.save` 与 `custchars-mod.save`；
- 转换前预览、目标覆盖确认、自动备份、原子替换和写入校验；
- 已开局存档编辑：物资、角色名字、HP、生命上限、基础属性、`bonus`、属性显示状态、PERK、TRAIT、手持武器、后备箱武器、剩余天数、车辆底盘与引擎；
- 武器资料选择器：中文/英文名称搜索、TIER 筛选、详细参数页、Wiki 地点与事件资料；
- 全局升级存档：`gstats.save` 与 `gstats-mod.save` 互转，一键解锁模式，或把 PERK / TRAIT 升至 3 级；
- 自动定位 `%APPDATA%\.madgarden\DR2C`，一键打开存档目录；
- 像素风界面、物资图标、刻晴彩蛋和图片轮播。

## 下载与运行

Windows 用户优先从 GitHub Releases 下载打包好的 `DR2C-Save-Station-*.exe`，无需安装 Python。

从源码运行：

```powershell
python -m pip install -r requirements.txt
python app.py
```

运行前请完全退出游戏。游戏运行时可能重新写回旧存档，覆盖工具的修改。

## 从源码构建

在 Windows PowerShell 中运行：

```powershell
.\build_release.ps1
```

成品输出到 `release/DR2C-Save-Station-1.0.0.exe`；PyInstaller 的构建缓存和隔离环境全部放在 `.temp/`。这些目录不会进入 Git。

## 安全与兼容性

活动存档混有 Deathforth 原始控制字节，不是普通 UTF-8 文本。本工具只对已识别字段做二进制定点替换，避免整份文件被文本编辑器重新编码。每次覆盖前会自动备份目标文件。

全局升级页面的高风险操作需要确认：

- 模式解锁会把所有 `wins-*` 字段设为 `1`。这会覆盖已有模式的真实通关次数，也会覆盖名称带 `wins` 的连胜记录；
- PERK / TRAIT 全解锁会把 `perk-*` 和 `trait-*` 设为最高等级 `3`，可能降低游戏的长期探索乐趣。

已测试：

- 原版游戏：`20260727`
- 简体中文汉化补丁：`906.2`

其他游戏、补丁或 Mod 版本未经测试，不保证兼容。

## 开发者与社区

- 开发者：绯海·三代
- B站主页：<https://space.bilibili.com/1418606>
- 加拿大维修之路 QQ 频道：<https://pd.qq.com/s/nfetjmmb>
- 汉化补丁与攻略：<https://www.bilibili.com/opus/852265599123849222>
- 全新 Mod 版本资源站：<https://dr2c.top/>
- Death Road to Canada Wiki：<https://deathroadtocanada.fandom.com/wiki/Death_Road_to_Canada_Wiki>

QQ群：1 群 `748853148`（快满了）、2 群 `634638288`、3 群 `923508276`、4 群 `908091369`。群会定时清理 1 级水友；频道不会清人，推荐同步加入 QQ 频道，尽量不要重复添加群。

## 许可与资源说明

项目代码使用 MIT License，详见 [LICENSE](LICENSE)。

仓库中的字体、Wiki 整理数据、像素图标和刻晴相关图片属于随项目附带的第三方或生成资源，不应被理解为全部受 MIT 授权。字体和 Wiki 数据请以各自来源的授权与署名要求为准；刻晴及相关作品知识产权归原权利人所有，本项目与 HoYoverse 无关联。

武器资料来源：Death Road to Canada Wiki。武器 ID 规则、版本限制和开发者注意事项见 [readme.txt](readme.txt)。
