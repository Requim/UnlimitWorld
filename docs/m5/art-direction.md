# M5 原创国风怪诞漫画美术方向

## 状态与来源

2026-10-09：已确认视觉方向，尚未生成正式素材。
当前会话没有内置 ImageGen 工具，CLI 路径等待用户授权与本机 API Key。
不得把本文件、提示词或程序化占位图当作正式美术完成证据。
所有最终资源必须保存到 `web-client/public/assets/`，生成提示和来源随交付记录。

## 统一风格

- 二维粗墨线漫画，清晰而有表现力的脸，轻微木版印刷质感。
- 黑、灰、白为中性色，朱红、青绿、亮黄分别承担危险、生机、资源强调。
- 怪诞来自人物表情、法宝和天道官僚意象，不靠模糊、脏暗背景或泛用粒子。
- 人物采用完整轮廓、明确武器与衣服层次，战斗缩小后仍能认出动作。
- 场景为可辨认的山门、古树、石阶、祭坛；中间为角色活动留空间。
- 画面不包含 UI、文字、水印、已有作品或知名角色。
- 卡牌插画用同一笔触，边框、费用、文本由真实 UI 绘制，不让模型生成文字。

## 资产清单

| Key | 输出位置 | 内容与构图 |
|---|---|---|
| cultivator | characters/cultivator.png | 瘦削白衣修士、朱红披带、歪髻、破木剑，带桀骜笑意，完整身体朝右 |
| paper_soldier | characters/paper_soldier.png | 折纸天兵、青绿纸甲、钝刀和认真过头的表情，完整身体朝左 |
| incense_guest | characters/incense_guest.png | 香火客，携带过大的香炉，头戴小冠，脸被烟线围绕但仍清晰 |
| fallen_monk | characters/fallen_monk.png | 破戒僧，斜披灰袍、红念珠、一把不合身份的巨剑，荒诞神态 |
| debt_immortal | characters/debt_immortal.png | 讨债仙，官袖内掏出长账单，腰挂算盘、表情油滑 |
| heaven_tax_collector | characters/heaven_tax_collector.png | 天税总管，红官印、成叠卷宗、夸张官帽，清晰精英轮廓 |
| heaven_judge | characters/heaven_judge.png | 监天判官，黑白官袍、青绿冠、巨大判笔和法令牌，威严却滑稽 |
| battle | backgrounds/battle.webp | 山门石阶和松林，日光，横版宽景，中心及下方可站人物 |
| boss | backgrounds/boss.webp | 云上天劫祭坛、破裂石台、红印旗，清楚而非暗糊的 Boss 场地 |
| card-* | cards/*.webp | 十八张独立法术插图，见下方清单，统一比例且留出边缘 |

角色推荐生成尺寸 1024x1536，游戏内使用经检查的透明 PNG；
场景推荐 1536x1024，保留原构图后输出 WebP；
法术插图推荐方形生成后统一裁切为 4:3 展示，不裁掉主要法术。
透明资产若使用不支持 alpha 的生成路径，先输出单色底再做可验证的去底，
必须检查衣袍内白色、发丝边缘和武器是否被误删。

## 共享生成提示

```text
Use case: stylized-concept
Asset type: original asset for a Chinese cultivation deckbuilding roguelike game
Style/medium: expressive hand-inked comic illustration; bold black brush outlines,
  restrained woodblock print texture, clear silhouette, readable hand-painted details
Palette: neutral black, gray and white with cinnabar red, jade teal and small bright yellow accents
Constraints: original character and composition, no existing franchises, no text,
  no logos, no watermark, no embedded UI, no photorealistic or 3D CGI rendering
```

每个角色追加：完整身体、不裁头脚、正面三分之四角度、统一站立基线、
手中物品清晰、纯色背景以便透明化、不额外添加背景人物。
每个场景追加：宽景、镜头固定、平整战斗地面、主舞台可读、两侧和中间可站人物。
每个卡牌追加：主体居中、明确法术与笔触、无文字、无卡牌边框。

## 十八张法术图

| 卡牌 | 原创法术主体 |
|---|---|
| 飞剑 | 一柄带青绿剑气的破木飞剑，急转向前 |
| 护体 | 围绕修士的白墨盾形法阵与红印结点 |
| 凝神 | 双手结印的安静剪影，青绿灵力沿经络流动 |
| 蓄剑 | 数柄墨线飞剑汇入一枚明亮剑意印 |
| 连斩 | 两道交错剑弧、飞散的红色纸符 |
| 剑引 | 飞剑牵出一条蜿蜒青绿灵线 |
| 万剑归宗 | 向中心汇聚的飞剑群和明确的巨大主剑 |
| 藏锋 | 收剑入鞘，鞘周围盘旋的护身剑意 |
| 火种 | 一粒朱红业火落在黑色符纸上 |
| 煽风 | 长袖送风，朱红火焰被吹成夸张法术轮廓 |
| 焚天 | 一道清晰的业火柱冲破墨云 |
| 借火 | 修士伸手从天雷与红印之间借取火焰 |
| 余烬 | 灰烬化成护盾，中心残留小块朱红炭火 |
| 金钟符 | 黄墨纸符化成一尊金钟护罩 |
| 照妖镜 | 旧铜镜反射来袭法术，红印与青绿光形成方向 |
| 封口符 | 有夸张嘴形的墨云被一道红色符箓封住 |
| 疾书 | 毛笔迅速画出一道青绿符咒，纸边飘动 |
| 引雷符 | 黄纸符将一道红色雷霆折向另一侧 |

## 验收

逐张检查：主体、风格、轮廓、边缘、背景、尺寸、透明性、资源引用和来源记录。
在真实战斗中检查缩小可读性与人物站立基线；在手机卡牌中检查插图主体完整。
所有资源加载通过、场景与角色可辨认、用户认可方向后才标记正式美术通过。
