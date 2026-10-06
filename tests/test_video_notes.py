import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("video_notes", ROOT / "scripts/video_notes.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TranslationBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = json.loads((ROOT / "examples/source.json").read_text())
        self.notes = json.loads((ROOT / "examples/notes.json").read_text())
        self.extraction = json.loads((ROOT / "examples/extraction.json").read_text())

    def save(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def build(self, partial=False):
        MODULE.build(SimpleNamespace(
            source=self.save("source.json", self.source),
            notes=self.save("notes.json", self.notes),
            extraction=self.save("extraction.json", self.extraction),
            partial=partial, out=str(self.root / "reading")))
        return self.root / "reading"

    def test_full_document_contains_both_sentences_and_translations(self):
        out = self.build()
        for filename in ("notes.md", "notes.html"):
            content = (out / filename).read_text()
            for section in self.notes["sections"]:
                self.assertIn(section["original"], content)
                self.assertIn(section["translation"], content)
        checks = json.loads((out / "checks.json").read_text())
        self.assertEqual(checks["scope"], "full")
        self.assertEqual(checks["raw_extraction_cues"], 2)

    def test_shortened_source_cannot_be_published_as_full(self):
        self.source["cues"] = self.source["cues"][:1]
        self.notes["sections"] = self.notes["sections"][:1]
        with self.assertRaisesRegex(ValueError, "complete unchanged extraction"):
            self.build()
        self.assertFalse((self.root / "reading").exists())

    def test_omitted_translation_is_rejected(self):
        self.notes["sections"] = self.notes["sections"][:1]
        with self.assertRaisesRegex(ValueError, "omitted, duplicated, or reordered"):
            self.build()

    def test_rewritten_original_is_rejected(self):
        self.notes["sections"][0]["original"] = "The model learns everything."
        with self.assertRaisesRegex(ValueError, "Original differs"):
            self.build()

    def test_summary_is_not_accepted_as_translation(self):
        self.notes["kind"] = "chapter_summary"
        with self.assertRaisesRegex(ValueError, "summaries are not translations"):
            self.build()

    def test_partial_source_is_visibly_marked_incomplete(self):
        self.source["cues"] = self.source["cues"][:1]
        self.notes["sections"] = self.notes["sections"][:1]
        out = self.build(partial=True)
        self.assertIn("部分翻译，未完成全文", (out / "notes.md").read_text())
        self.assertEqual(json.loads((out / "checks.json").read_text())["scope"], "partial")

    def test_sentence_splits_preserve_all_original_characters(self):
        text = "A model learns. It predicts."
        self.extraction = {"transcriptSegments": [{"startMs": 0, "endMs": 4000, "text": text}]}
        self.source["cues"] = [
            {"id": "s1", "start": 0, "end": 4, "text": text[:15],
             "cue_spans": [{"cue_id": "c0001", "start": 0, "end": 15}]},
            {"id": "s2", "start": 0, "end": 4, "text": text[15:],
             "cue_spans": [{"cue_id": "c0001", "start": 15, "end": len(text)}]},
        ]
        self.notes["sections"] = [
            {"source_ids": [c["id"]], "original": c["text"], "translation": translation}
            for c, translation in zip(self.source["cues"], ["模型学习。", "它进行预测。"])
        ]
        out = self.build()
        self.assertIn("它进行预测。", (out / "notes.html").read_text())
        damaged = copy.deepcopy(self.source)
        damaged["cues"][1]["cue_spans"][0]["start"] = 16
        with self.assertRaisesRegex(ValueError, "without gaps"):
            MODULE.verify_full_source(damaged, self.root / "extraction.json")


if __name__ == "__main__":
    unittest.main()
