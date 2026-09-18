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


# --- tool calling ------------------------------------------------------------------
# A checkpoint trained on this format will not reliably call a tool described any other
# way, so these assert the exact shapes rather than "something tool-ish happened".

WEATHER = {
    "name": "get_weather",
    "description": "Current conditions for a city.",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "The city"},
            "units": {"type": "string", "enum": ["c", "f"]},
        },
        "required": ["city"],
    },
}


class RenderToolsTest(unittest.TestCase):
    def test_namespace_and_types(self):
        out = channels.render_tools([WEATHER])
        self.assertIn("namespace functions {", out)
        self.assertIn("} // namespace functions", out)
        self.assertIn("type get_weather = (_: {", out)
        self.assertIn("// Current conditions for a city.", out)
        self.assertIn("city: string,", out)          # required has no marker
        self.assertIn('units?: "c" | "f",', out)     # optional is marked, enum is a union

    def test_no_properties_is_a_nullary_function(self):
        self.assertIn("type ping = () => any;", channels.render_tools([{"name": "ping"}]))

    def test_no_tools_renders_nothing(self):
        self.assertEqual(channels.render_tools([]), "")


class ToolPromptTest(unittest.TestCase):
    def test_tools_reach_the_developer_message(self):
        p = channels.build_prompt({"tools": [WEATHER], "messages": [{"role": "user", "content": "weather?"}]})
        self.assertIn("# Tools", p)
        self.assertIn("type get_weather", p)
        self.assertIn("to=functions.<name>", p)      # the system message says where calls go

    def test_a_prior_call_and_its_result_are_replayed(self):
        p = channels.build_prompt({
            "tools": [WEATHER],
            "messages": [
                {"role": "user", "content": "weather in Paris?"},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"city": "Paris"}}]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "14C"}]},
            ]})
        self.assertIn('<|start|>assistant<|channel|>commentary to=functions.get_weather '
                      '<|constrain|>json<|message|>{"city":"Paris"}<|call|>', p)
        # the result is a message FROM the tool, named by resolving the id of the call
        self.assertIn("<|start|>functions.get_weather to=assistant<|channel|>commentary"
                      "<|message|>14C<|end|>", p)
        # a turn that carried only a result does not also invent an empty user message
        self.assertNotIn("<|start|>user<|message|><|end|>", p)


class ToolParseTest(unittest.TestCase):
    CALL = ('<|channel|>analysis<|message|>Need the weather.<|end|>'
            '<|start|>assistant<|channel|>commentary to=functions.get_weather '
            '<|constrain|>json<|message|>{"city":"Paris","units":"c"}<|call|>')

    def test_a_call_becomes_a_tool_use_block(self):
        blocks = channels.parse_output(self.CALL)
        self.assertEqual([b["type"] for b in blocks], ["thinking", "tool_use"])
        call = blocks[1]
        self.assertEqual(call["name"], "get_weather")
        self.assertEqual(call["input"], {"city": "Paris", "units": "c"})
        self.assertTrue(call["id"].startswith("toolu_"))

    def test_arguments_stream_as_json_deltas(self):
        s = channels.ChannelStream()
        events = []
        for i in range(0, len(self.CALL), 7):
            events += s.feed(self.CALL[i:i + 7])
        events += s.finish()
        kinds = [e[2]["type"] for e in events if e[0] == "delta"]
        self.assertIn("input_json_delta", kinds)
        joined = "".join(e[2]["partial_json"] for e in events
                         if e[0] == "delta" and e[2]["type"] == "input_json_delta")
        self.assertEqual(joined, '{"city":"Paris","units":"c"}')
        self.assertTrue(s.called_tool)

    def test_malformed_arguments_do_not_raise(self):
        blocks = channels.parse_output(
            '<|start|>assistant<|channel|>commentary to=functions.f <|message|>{not json<|call|>')
        self.assertEqual(blocks[-1]["type"], "tool_use")
        self.assertEqual(blocks[-1]["input"], {})

    def test_a_plain_answer_is_still_text(self):
        blocks = channels.parse_output(SAMPLE)
        self.assertEqual([b["type"] for b in blocks], ["thinking", "text"])
        self.assertFalse(any(b["type"] == "tool_use" for b in blocks))
