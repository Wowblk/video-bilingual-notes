# video-bilingual-notes

把视频、课程和访谈整理成保留完整原文的中英对照阅读文档，附时间戳与内容对应截图。

这是一个 Codex skill，加上一份 Python 编排工具。助手负责分句、翻译、选图和校核；脚本负责来源覆盖检查、抽帧和生成 Markdown、自包含 HTML。它没有内置翻译模型，也不自动下载完整视频。

## 安装

将仓库放到 Codex 的 skills 目录。若你设置了 `CODEX_HOME`，使用对应的 skills 目录；否则可以执行：

```bash
git clone https://github.com/Wowblk/video-bilingual-notes.git ~/.codex/skills/video-bilingual-notes
```

在支持 skill 的 Codex 会话中使用：

```text
使用 $video-bilingual-notes 将这个视频完整翻译成中英逐句对照，保留时间戳和内容对应截图：https://www.youtube.com/watch?v=VIDEO_ID
```

## 工作流程

1. 提取完整原语言字幕，保留原始结果和人工字幕、自动字幕或语音识别的来源身份。
2. 按句意合并字幕断行，必要时拆分一个字幕片段内的多个句子，记录来源字符范围。
3. 分批翻译，每句原文对应一句译文，保存进度和未完成范围。
4. 根据讲解内容选取实际画面，并记录截图时刻及选择原因。
5. 核对全文来源覆盖、原文保真、译文和截图时间，生成阅读文档。

默认处理完整视频。章节概述属于摘要，不能作为完整翻译。已有机器译文可以用作草稿，句界、术语和译文需要逐句核对。

## 依赖

编排工具只使用 Python 标准库，需要 Python 3.9 或更新版本。

根据输入选择外部工具：

- [summarize](https://github.com/steipete/summarize) 用于提取文本和带时间戳的字幕。
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) 用于取得公开字幕和可访问的视频。
- [FFmpeg](https://ffmpeg.org/) 与 ffprobe 用于从本地视频抽帧。

安装这些工具是独立步骤。翻译由使用 skill 的助手完成，不需要另配翻译 API。视频访问限制、字幕缺失或版权授权仍应按实际来源处理。MIT 许可证只覆盖本仓库的代码和文档，不授予视频及其字幕、截图的权利。

## 运行最小示例

仓库中的两句示例为原创合成文本，无需下载视频或配置外部服务：

```bash
python3 scripts/video_notes.py build   --source examples/source.json   --notes examples/notes.json   --extraction examples/extraction.json   --out output/example
```

输出 `notes.md`、`notes.html` 和 `checks.json`。输出目录需要为空；再次运行时换一个目录。

实际视频的提取命令、记录格式和抽帧方法见 [references/workflow.md](references/workflow.md)。助手执行规则见 [SKILL.md](SKILL.md)。

## 完整性检查

完整编排要求原始 `extraction.json`。脚本核对规范化来源与完整提取结果；拆句后的来源需通过 `cue_spans` 证明原始字符没有遗漏、重复或改序。

每个来源记录按顺序出现一次，原文保留来源文本，译文不能为空。截图必须存在，截图时刻必须落在对应字幕时间范围内。`--partial` 用于部分稿，会在文档和报告中标注未完成全文。

结构检查不能证明句子边界正确、译文准确或原字幕没有漏字。全片逐句翻译完成，需要助手另外核对这些内容。自动字幕时间超出视频时长时，当前编排器会拒绝构建，需要核实源时间并保留校订依据。

## 开发与验证

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖实际文档生成、全文遗漏、原文改写、摘要误用、拆句字符遗漏和部分稿标注。

## English

A Codex skill for complete bilingual video reading documents with original transcripts, paired English and Chinese translations, timestamps, and selected screenshots.

The assistant handles sentence boundaries, translation, visual selection, and review. The standard-library Python helper validates source coverage and renders Markdown and standalone HTML. It does not include a translation model. See the synthetic [examples](examples) for a local build and the [workflow](references/workflow.md) for real inputs.

## License

[MIT](LICENSE). Source videos and their transcripts or screenshots retain their own rights.
