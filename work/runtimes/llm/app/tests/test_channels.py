# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
import unittest

from symoneural_llm import channels

SAMPLE = ("<|channel|>analysis<|message|>We need to answer briefly.<|end|>"
          "<|start|>assistant<|channel|>final<|message|>I am the assistant served here.<|return|>")


class BuildPromptTest(unittest.TestCase):
    def test_shape(self):
        p = channels.build_prompt({"system": "Be terse.", "messages": [
            {"role": "user", "content": "hi"}, {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
            {"role": "user", "content": "again"}]}, identity="I", reasoning="low")
        self.assertTrue(p.startswith("<|start|>system<|message|>I\nReasoning: low\n"))
        self.assertIn("<|start|>developer<|message|># Instructions\n\nBe terse.<|end|>", p)
        self.assertIn("<|start|>user<|message|>hi<|end|>", p)
        self.assertIn("<|start|>assistant<|channel|>final<|message|>hello<|end|>", p)
        self.assertTrue(p.endswith("<|start|>user<|message|>again<|end|><|start|>assistant"))

    def test_bad_role(self):
        with self.assertRaises(ValueError):
            channels.build_prompt({"messages": [{"role": "tool", "content": "x"}]})


class ParseTest(unittest.TestCase):
    def test_two_channels(self):
        blocks = channels.parse_output(SAMPLE)
        self.assertEqual([b["type"] for b in blocks], ["thinking", "text"])
        self.assertEqual(blocks[0]["thinking"], "We need to answer briefly.")
        self.assertEqual(blocks[1]["text"], "I am the assistant served here.")

    def test_plain_text_without_markers(self):
        blocks = channels.parse_output("Paris.")
        self.assertEqual(blocks, [{"type": "text", "text": "Paris."}])

    def test_final_only_ended_by_end(self):
        blocks = channels.parse_output("<|channel|>final<|message|>Done.<|end|>")
        self.assertEqual(blocks, [{"type": "text", "text": "Done."}])

    def test_call_stops_generation(self):
        s = channels.ChannelStream()
        ev = s.feed("<|channel|>commentary<|message|>tool time<|call|> trailing garbage") + s.finish()
        self.assertTrue(s.done)
        self.assertEqual([e[0] for e in ev], ["start", "delta", "stop"])


class StreamTest(unittest.TestCase):
    def _run(self, pieces):
        s = channels.ChannelStream(); ev = []
        for p in pieces:
            ev += s.feed(p)
        ev += s.finish()
        return ev

    def _assemble(self, ev):
        blocks = {}
        for e in ev:
            if e[0] == "start": blocks[e[1]] = dict(e[2])
            elif e[0] == "delta":
                b = blocks[e[1]]; k = "text" if b["type"] == "text" else "thinking"; b[k] += e[2][k]
        return [blocks[i] for i in sorted(blocks)]

    def test_split_at_every_boundary_gives_the_same_blocks(self):
        expect = channels.parse_output(SAMPLE)
        for n in (1, 2, 3, 5, 7, 11, 13, 40):
            pieces = [SAMPLE[i:i + n] for i in range(0, len(SAMPLE), n)]
            got = self._assemble(self._run(pieces))
            for b in got:
                b.pop("signature", None)
            for b in expect:
                b.pop("signature", None)
            self.assertEqual(got, expect, f"piece size {n}")

    def test_event_order(self):
        ev = self._run([SAMPLE])
        kinds = [(e[0], e[1]) for e in ev]
        self.assertEqual(kinds, [("start", 0), ("delta", 0), ("stop", 0), ("start", 1), ("delta", 1), ("stop", 1)])

    def test_sse_shapes(self):
        out = "".join(channels.sse(iter(self._run([SAMPLE]))))
        self.assertIn("event: content_block_start", out)
        self.assertIn('"type": "thinking_delta"', out)
        self.assertIn('"type": "text_delta"', out)
        self.assertEqual(out.count("event: content_block_stop"), 2)


if __name__ == "__main__":
    unittest.main()
