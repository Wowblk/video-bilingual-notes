# 提取与图文编排

## 依赖与提取

先检查 `summarize --help`、`summarize slides --help`、`ffmpeg`、`ffprobe`、`yt-dlp` 的当前可用性；不自动安装缺失依赖。现有 summarize skill 的摘要截断规则不适用于本流程的全文翻译。

```bash
mkdir -p '/task/output/video-notes'
summarize 'VIDEO_URL_OR_LOCAL_PATH' --extract --timestamps --json --video-mode transcript --no-slides > '/task/output/video-notes/extraction.json'
summarize slides 'VIDEO_URL_OR_LOCAL_PATH' --slides-dir '/task/output/video-notes/candidates' --slides-max 30 --json > '/task/output/video-notes/slides-result.json'
```

`--extract` 跳过摘要模型，但媒体转录仍可能使用已配置的远程服务。私有视频先核对当前 provider；需要纯本地处理时使用本地转录能力，不默认把私有视频上传。候选截图数量按视频长度和内容调整；默认 6 张不等于完整覆盖。字幕与截图的时间原点必须相同，剪辑片段的偏移要显式校正。

如果 summarize 没有返回 timed segments，检查它是否仅提取了简介或纯文本。YouTube 可通过 yt-dlp 获取原语言字幕，先 `yt-dlp --list-subs 'URL'`，再按真实语言获取字幕；保留人工/自动字幕身份。字幕失败且无配置好的转录能力时报告阻碍。

需要精确补帧时，使用用户提供的本地视频或已正常取得的视频。远程视频处理可以用 yt-dlp 下载到本任务目录，限定单视频 `--no-playlist`，采用合理分辨率，不扩大到账号/播放列表。遇到访问限制时不要自动导出浏览器 cookie 或绕过登录；使用已授权方法或报告缺失。此下载用于用户明确要求的视频处理，不是绕过聊天远程媒体显示限制。

## 记录格式

`source.json` 是规范化 timed transcript；保留 `extraction.json` 为原始证据。

```json
{"title":"示例","url":"https://example.com/video","language":"en","transcript_source":"auto captions; not human verified","duration":120,"cues":[{"id":"c0001","start":0,"end":4,"text":"A model learns from data."}]}
```

start/end/duration 单位为秒。end 可为 null（未知），不能用下一 cue 时间冒充实际语音结束。normalize 只读取提取结果的 transcriptSegments，不推断转录来源/时长；助手从真实元数据补齐。

`notes.json` 由助手编写；每条 section 对应一句完整原文及其译文，不是章节概述：

```json
{"kind":"sentence_translation","unit":"sentence","sections":[{"title":"模型学习","source_ids":["c0001"],"original":"A model learns from data.","translation":"模型从数据中学习。","frames":[{"file":"frames/frame-000002000.jpg","time":2,"reason":"该时间点的幻灯片显示模型与数据的关系"}]}]}
```

original 必须为源 cue 按顺序拼接的原文，只可调整空白；校订另写 `correction`，不可替换原文。每个 cue 在全文中恰好出现一次；同一段可以无截图，也可以多图。帧路径相对记录目录，必须为真实本地截图。若截图位于邻近说明之外，调整有证据的段落分组或单独编写画面段落，不伪造截图时间。

## 脚本

```bash
python3 scripts/video_notes.py normalize --input '/task/output/video-notes/extraction.json' --output '/task/output/video-notes/source.json' --language en --title '真实标题' --url '真实URL'
python3 scripts/video_notes.py frames --video '/task/output/video-notes/video.mp4' --out '/task/output/video-notes/frames' --times 12.5 78 135.2
python3 scripts/video_notes.py build --source '/task/output/video-notes/source.json' --notes '/task/output/video-notes/notes.json' --extraction '/task/output/video-notes/extraction.json' --out '/task/output/video-notes/reading'
```

frames 的时间点由助手根据转录/画面选择，它不自动理解视频。build 复制被选中的截图到 reading/frames，同时生成 notes.md、notes.html、checks.json。HTML 图片内嵌，可独立打开；Markdown 需连同 frames 文件夹一起交付。

build 检查 cue 顺序与完整覆盖、原文保真、翻译非空、时间合法和图像存在；翻译准确性、字幕遗漏、截图内容对应需人工/助手核查。确认 duration 后再交付，未知时明确标为未知。检查报告不能代替内容检查。

## 官方参考

- 提取：https://summarize.sh/docs/extract-only
- 时间戳：https://summarize.sh/docs/timestamps.html
- 视频截图：https://summarize.sh/docs/commands/summarize.html
- yt-dlp：https://github.com/yt-dlp/yt-dlp#usage-and-options

## 句子级 source 与覆盖验证

无标点的自动字幕先按语义合并断行，再逐句翻译。若一个 cue 内含多个句子，创建句子级 `source.json`，各句写 `cue_spans: [{"cue_id":"c0001","start":0,"end":28}]`，字符位置为 Python 字符串索引、左闭右开。每句 `text` 必须等于相应原文字符切片依次拼接（跨 cue 用空格连接）；各 cue 的字符区间从 0 连续覆盖到原文长度，不能删掉口头语或把原文换成摘要。start/end 来自其首尾原 cue；cue 内的句子没有独立精确时间，标记 `timing_precision: "source cue range"`，不得按字数伪造语音时间。无需 cue 内拆句时保持规范化 source 原样，按连续 cue 合并成句子记录。

完整编排必须传 `--extraction`，脚本比较完整原始 cue 的文本与时间，或验证 `cue_spans` 的字符覆盖。`--partial` 仅用于显式部分稿，成品和 checks.json 会显示“部分翻译，未完成全文”。不得为通过验证而将 source 缩为几个摘录。

长视频每批保持原文顺序，保存句子/译文与 checkpoint；最终合并检查全文，而不是仅在每批的子集上检查。句子边界与翻译准确性需要助手逐句核对，结构验证不自动判断语义。
