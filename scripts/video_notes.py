#!/usr/bin/env python3
"""Normalize timed transcripts, capture chosen frames, build bilingual documents."""
import argparse
import base64
import html
import json
import math
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f'Invalid time: {value!r}')
    return float(value)


def stamp(t):
    t = int(seconds(t))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f'{h:02}:{m:02}:{s:02}'


def safe_url(value):
    return value if urlsplit(value).scheme in ('http', 'https') else ''


def transcript_segments(data):
    found = []
    def walk(item):
        if isinstance(item, dict):
            if isinstance(item.get('transcriptSegments'), list) and item['transcriptSegments']:
                found.append(item['transcriptSegments'])
            for v in item.values():
                walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)
    walk(data)
    if not found:
        raise ValueError('No transcriptSegments. Do not substitute a description or invent timestamps.')
    if any(x != found[0] for x in found[1:]):
        raise ValueError('Multiple different transcript segment arrays; inspect extraction before normalizing.')
    return found[0]


def normalize(a):
    segments = transcript_segments(read(a.input))
    cues = []
    for i, seg in enumerate(segments, 1):
        start = seconds(seg['startMs']) / 1000
        end = None if seg.get('endMs') is None else seconds(seg['endMs']) / 1000
        text = seg['text']
        if not isinstance(text, str) or not text.strip() or (end is not None and end < start):
            raise ValueError(f'Invalid source segment {i}')
        if cues and start < cues[-1]['start']:
            raise ValueError('Source segments are out of order.')
        cues.append(dict(id=f'c{i:04}', start=start, end=end, text=text))
    write(a.output, dict(title=a.title, url=a.url, language=a.language,
                        transcript_source='unknown; inspect raw extraction', duration=None, cues=cues))


def capture(a):
    video = Path(a.video).resolve(strict=True)
    duration = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                     'format=duration', '-of', 'default=nw=1:nk=1', str(video)], text=True))
    times = [seconds(t) for t in a.times]
    if any(t >= duration for t in times):
        raise ValueError(f'Frame time outside video duration {duration:.3f}s')
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    names = [f'frame-{round(t * 1000):09}.jpg' for t in times]
    if len(set(names)) != len(names):
        raise ValueError('Frame times collide at millisecond precision.')
    if any((out / name).exists() for name in names) or (out / 'frames.json').exists():
        raise ValueError('Output already exists; choose a fresh frame directory.')
    for t, name in zip(times, names):
        path = out / name
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-n', '-i', str(video),
                        '-ss', str(t), '-frames:v', '1', '-q:v', '2', str(path)], check=True)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f'No frame extracted at {t}')
        manifest.append(dict(file=name, time=t))
    write(out / 'frames.json', dict(video=str(video), duration=duration, frames=manifest))


def verify_full_source(src, extraction):
    raw = transcript_segments(read(extraction))
    original = {f'c{i:04}': c for i, c in enumerate(raw, 1)}
    cues = src['cues']
    if not any('cue_spans' in c for c in cues):
        expected = [(key, seg['startMs']/1000, None if seg.get('endMs') is None else seg['endMs']/1000, seg['text']) for key, seg in original.items()]
        actual = [(c['id'], c['start'], c.get('end'), c['text']) for c in cues]
        if actual != expected:
            raise ValueError('Source is not the complete unchanged extraction. Supply sentence cue_spans for split source.')
        return len(raw)
    raw_ids = list(original)
    index, offset = 0, 0
    for cue in cues:
        spans = cue.get('cue_spans', [])
        if not spans:
            raise ValueError('Each sentence requires cue_spans when using split source.')
        text_parts = []
        for span in spans:
            if index >= len(raw_ids) or span['cue_id'] != raw_ids[index]:
                raise ValueError('Sentence spans omit, duplicate, or reorder original cues.')
            text = original[raw_ids[index]]['text']
            start, end = span['start'], span['end']
            if type(start) is not int or type(end) is not int or start != offset or not start < end <= len(text):
                raise ValueError('Sentence spans must cover original characters consecutively without gaps.')
            text_parts.append(text[start:end])
            offset = end
            if offset == len(text):
                index, offset = index + 1, 0
        if cue['text'] != ' '.join(text_parts):
            raise ValueError('Sentence text differs from original character slices.')
        first, last = original[spans[0]['cue_id']], original[spans[-1]['cue_id']]
        expected_end = None if last.get('endMs') is None else last['endMs']/1000
        if cue['start'] != first['startMs']/1000 or cue.get('end') != expected_end:
            raise ValueError('Sentence timestamps must retain original cue ranges.')
    if index != len(raw_ids) or offset:
        raise ValueError('Sentence source does not cover the complete extraction.')
    return len(raw)


def build(a):
    src, notes = read(a.source), read(a.notes)
    if notes.get('kind') != 'sentence_translation' or notes.get('unit') != 'sentence':
        raise ValueError('Expected sentence_translation with unit sentence; summaries are not translations.')
    if not a.partial and not a.extraction:
        raise ValueError('Full translation requires --extraction to verify original source coverage.')
    raw_count = verify_full_source(src, a.extraction) if not a.partial else None
    cues = src['cues']
    if not cues or src['language'] not in ('en', 'zh'):
        raise ValueError('Nonempty cues and language en/zh are required.')
    by_id = {c['id']: c for c in cues}
    if len(by_id) != len(cues):
        raise ValueError('Duplicate source IDs.')
    duration = None if src.get('duration') is None else seconds(src['duration'])
    prev = -1
    for c in cues:
        start = seconds(c['start'])
        end = None if c.get('end') is None else seconds(c['end'])
        if start < prev or (end is not None and end < start):
            raise ValueError('Invalid source timeline.')
        if duration is not None and (start > duration or (end is not None and end > duration)):
            raise ValueError('Source time exceeds video duration.')
        prev = start
    covered, sections = [], []
    base = Path(a.notes).resolve().parent
    for i, s in enumerate(notes['sections'], 1):
        ids = s['source_ids']
        if not ids:
            raise ValueError(f'Empty source_ids in section {i}')
        chosen = [by_id[x] for x in ids]
        original = ' '.join(c['text'] for c in chosen)
        if ' '.join(s['original'].split()) != ' '.join(original.split()):
            raise ValueError(f'Original differs from source in section {i}')
        if not isinstance(s['translation'], str) or not s['translation'].strip():
            raise ValueError(f'Missing translation in section {i}')
        covered.extend(ids)
        start = chosen[0]['start']
        end = chosen[-1].get('end')
        # Unknown end: do not infer an actual speech endpoint; no timed frame alignment.
        frames = []
        for f in s.get('frames', []):
            t = seconds(f['time'])
            if end is None or not start <= t <= end:
                raise ValueError(f'Frame outside known section time in section {i}')
            if not str(f.get('reason', '')).strip():
                raise ValueError(f'Missing frame selection reason in section {i}')
            p = (base / f['file']).resolve(strict=True)
            if p.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
                raise ValueError('Unsupported image format.')
            frames.append((p, t, f['reason']))
        sections.append((s, start, end, frames))
    if covered != [c['id'] for c in cues]:
        raise ValueError('Source cues omitted, duplicated, or reordered.')
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory is nonempty; choose a fresh directory.')
    (out / 'frames').mkdir(parents=True, exist_ok=True)
    title = src.get('title') or '视频双语图文笔记'
    url = safe_url(src.get('url', ''))
    e = html.escape
    status = '部分翻译，未完成全文' if a.partial else '完整来源的逐句对照译稿（译文质量需核对）'
    md = [f'# {title}', '', status, '', f'来源：{url or "本地文件／未提供链接"}',
          f'转录来源：{src.get("transcript_source", "unknown")}',
          f'时长：{stamp(duration) if duration is not None else "未知"}', '',
          '原文保留提取文本；自动字幕/ASR 不代表作者校订。', '']
    body = [f'<h1>{e(title)}</h1>', f'<p>{e(status)}</p>', f'<p>来源：<a href="{e(url, quote=True)}">{e(url)}</a></p>',
            f'<p>转录来源：{e(str(src.get("transcript_source", "unknown")))}</p>',
            f'<p>时长：{stamp(duration) if duration is not None else "未知"}；原文保留提取文本。</p>']
    labels = ('英文原文', '中文译文') if src['language'] == 'en' else ('中文原文', '英文译文')
    count = 0
    for i, (s, start, end, frames) in enumerate(sections, 1):
        heading = f'{stamp(start)}–{stamp(end) if end is not None else "结束时间未知"} · {s.get("title", f"片段 {i}")}'
        md.extend([f'## {heading}', '', f'**{labels[0]}**', '', s['original'], '', f'**{labels[1]}**', '', s['translation'], ''])
        body.append(f'<section><h2>{e(heading)}</h2><div class="pair"><div><b>{labels[0]}</b><p>{e(s["original"])}</p></div><div><b>{labels[1]}</b><p>{e(s["translation"])}</p></div></div>')
        if s.get('correction'):
            md.extend(['校订说明：' + s['correction'], ''])
            body.append('<p>校订说明：' + e(s['correction']) + '</p>')
        for p, t, reason in frames:
            count += 1
            name = f'{count:04}-{p.name}'
            shutil.copyfile(p, out / 'frames' / name)
            caption = f'{stamp(t)} · {reason}'
            md.extend([f'![视频画面 {stamp(t)}](frames/{quote(name)})', '', caption, ''])
            mime = {'.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.png':'image/png', '.webp':'image/webp'}[p.suffix.lower()]
            payload = base64.b64encode(p.read_bytes()).decode('ascii')
            body.append(f'<figure><img alt="视频画面 {stamp(t)}" src="data:{mime};base64,{payload}"><figcaption>{e(caption)}</figcaption></figure>')
        body.append('</section>')
    css = 'body{max-width:1100px;margin:40px auto;padding:0 24px;font:17px/1.7 system-ui;color:#17212d}h2{margin-top:2em}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}.pair>div{background:#f3f6fa;padding:18px;min-width:0}p{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;height:auto}figure{margin:24px 0}figcaption{color:#596473}@media(max-width:700px){.pair{grid-template-columns:1fr}}'
    (out / 'notes.md').write_text('\n'.join(md), encoding='utf-8')
    (out / 'notes.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + e(title) + '</title><style>' + css + '</style><body>' + '\n'.join(body) + '</body></html>', encoding='utf-8')
    write(out / 'checks.json', dict(source_cues=len(cues), covered_cues=len(covered), sections=len(sections), frames=count,
          scope='partial' if a.partial else 'full', raw_extraction_cues=raw_count, unit='sentence', sentence_boundaries='requires review',
          structural_checks='passed', translation_accuracy='requires review', visual_alignment='requires review',
          transcript_completeness='requires audio review', duration_known=duration is not None))
    print(out.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('normalize')
    for name in ('input', 'output', 'title', 'language'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--url', default='')
    p.set_defaults(run=normalize)
    p = sub.add_parser('frames')
    p.add_argument('--video', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--times', type=float, nargs='+', required=True)
    p.set_defaults(run=capture)
    p = sub.add_parser('build')
    for name in ('source', 'notes', 'out'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--extraction', help='Original full extraction JSON, required for full translation.')
    p.add_argument('--partial', action='store_true', help='Explicitly mark output as incomplete partial translation.')
    p.set_defaults(run=build)
    args = parser.parse_args()
    try:
        args.run(args)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
