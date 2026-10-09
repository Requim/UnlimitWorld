# 图片 API 失败诊断

2026-10-09。用户要求确认失败是否由参数导致。
首轮诊断没有发起图片生成请求、切换模型或修改工具，只核对公开资料、
实际 dry-run、只读模型查询与离线 SDK 行为。
用户随后授权解决问题，最新真实验证与修复见末节。

## 已确认

| 检查 | 实际结果 | 证明边界 |
|---|---|---|
| 请求地址 | `/v1/images/generations`，用户指定 Base URL | 与供应商配置说明一致 |
| 原装 dry-run | `gpt-image-2`、`high`、`2048x3072`、`png`、`n=1` 通过 | 仅证明本地校验通过 |
| 额外参数 | 未发送 background、input_fidelity、output_compression、response_format | 没有这些字段的误设证据 |
| 提示词 | 2078 字符；重试沿用原毕方提示词 | 没有本地改写 |
| `GET /v1/models` | 200，列出请求模型及 `gpt-image-2-4k` | 不证明余额、生成权限或像素 |
| 原装工具身份 | SHA256 与原记录一致 | 没有修改原装 CLI |
| SDK 解析 | openai 3.26.1；下述三种输入均读出 None | None 不能区分原始字段形态 |
| CLI 输出处理 | 只读取 `data[].b64_json` 并调用 Base64 解码 | 不接受仅 URL 的图片结果 |
| 供应商页面 | 同时处理 `data[].b64_json` 与 `data[].url` | 不证明前次响应实际是 URL |

本地尺寸约束检查：2048、3072 均为 16 的倍数；最大边 3072，
宽高比 1.5，总像素 6,291,456。该结果不能代替供应商的能力验证。

SDK 离线输入与结果：

```json
[
  {"input": {"url": "https://example.invalid/image.png"}, "b64_json": null, "fields_set": ["url"]},
  {"input": {"b64_json": null}, "b64_json": null, "fields_set": ["b64_json"]},
  {"input": {}, "b64_json": null, "fields_set": []}
]
```

上述地址是离线测试用示例，没有访问图片或发起生成。
旧 CLI 日志只有 SDK 属性读取值与解码异常，未保存原始 JSON、HTTP 状态、
响应字段、请求 ID 或供应商结算记录。此前「接口返回 null」表述过强，
已改为「SDK 的 Base64 读取值为 None」。

## 修复前假设

1. 返回格式不兼容：有实际工具差异支持。供应商页面支持 URL，
   原装 CLI 没有此分支；但前次响应未捕获，不能认定实际返回 URL。
2. 上游空结果或不同数据结构：仍不能排除，必须检查原始响应中的
   `data`、`url`、Base64 字段和错误信息。
3. 高分辨率路由或模型差异：供应商文档提供 `gpt-image-2-4k`，
   但没有证明原模型不支持本次尺寸，也没有参数拒绝错误可供确认。
   不能将此当成毕方失败的已证实原因，不能擅自切换模型。

## 来源

读取日期为 2026-10-09，只使用供应商公开页面与本机实际文件。

- 供应商配置说明：`https://docs.jojocode.com/zh/docs/setup/image`。
  确认用户地址、Images API、`gpt-image-2`，并提供可选 4K 型号。
- 供应商生图页面：`https://image.jojocode.com/`。
- 当次页面 JS：`https://image.jojocode.com/assets/index-DmhxslQr.js`。
  图片解析函数检查 Base64 后检查 URL；配置中的
  `responseFormatB64Json` 开关会追加 `response_format: b64_json`，
  页面明确说明并非所有网关都支持。这里只检查代码，没有在网页输入凭据。
- 本机原装 CLI：
  `C:/Users/95191/.codex/skills/.system/imagegen/scripts/image_gen.py`。
- 本机 SDK：
  `.venv/Lib/site-packages/openai/types/image.py`。

## 下一步边界

需要一次经用户授权的专用诊断请求，保留脱敏原始结构、状态和字段形态，
不将 URL 查询串、Base64 全文或凭据写入日志。该请求可能计费，
不自动重试或批量扩散，不修改原装 CLI；取得证据后再做单一变量验证。
本轮凭据仅经隐藏输入用于模型查询，结束已清理，没有进入文件或前端。

本记录不代表生成失败原因已完全确认、API 已修复或取得高清资源。

## 授权修复与真实结论

用户在单张专用诊断的提议后要求解决问题。本轮使用项目适配器
`tools/jojocode_image.py`，没有修改原装 CLI，没有增加 response_format、
更换模型或改变原提示词/质量/尺寸，只发起一次图片 POST。

实际原始响应返回 HTTP 200，`data[0]` 仅包含长度 101 的 URL，
不存在 `b64_json` 字段；已通过该 URL 下载并验证真正的 PNG。
因此此次直接原因已确认：供应商返回 URL，与原装 CLI 仅解码 Base64 的
约定不兼容。不能声称此前未捕获的每一次响应都已恢复，也不能推断其收费状态。

收到的原图为 2352×3520，9,105,945 bytes，本地未做缩放或插值。
该尺寸比请求的 2048×3072 更大，但不完全一致；精确尺寸匹配标记为 false。
这证明实际取图链路可用，不证明供应商内部原生生成方式或模型身份。

适配器支持 Base64、URL、内嵌 data URL，默认不发送请求；
下载不继承认证信息，异常与空结果都有安全错误码，保存脱敏结构。
最终报告提交失败会保留已验证图片，提示不要重新生成，并尽力保存恢复报告。
45 项离线回归与独立复审通过，相关资源工具 84 passed、2 skipped。

脱敏实际证据为 [单张响应记录](image-response-20261009-1.json)。
完整提示词仍是原毕方任务；CLI 使用方式：

```powershell
.\.venv\Scripts\python.exe tools/jojocode_image.py `
  --input .data/imagegen/myth-seeds/retry-20261009-1/bifang.jsonl `
  --out-dir .data/imagegen/myth-seeds/new-attempt
```

此命令默认只 dry-run；只有已授权后增加 `--allow-paid-request` 才会生成。
真实凭据从临时进程的 `OPENAI_API_KEY` 读取，不作为命令行参数或写入文件。
已有 attempt 目录拒绝复用，不能把调用本命令当作无成本网络测试。
