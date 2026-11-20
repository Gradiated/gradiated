import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]


def load_module(directory):
    """The cartridge module exactly as the bundle patch adds it to SGLang."""
    lines = (BUNDLE / "patches/cartridge_module.patch").read_text().splitlines(True)
    if not lines[0].startswith("--- /dev/null"):
        raise AssertionError("cartridge_module.patch must add a new file")
    path = Path(directory) / "cartridge.py"
    path.write_text("".join(line[1:] for line in lines[3:]))
    spec = importlib.util.spec_from_file_location("sglang_cartridge", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


with tempfile.TemporaryDirectory() as _source:
    cartridge = load_module(_source)

BOS, USER, ASSISTANT, EOS, TOOLS = 0, 1, 2, 3, 4
SLOTS = "甲乙丙"
SLOT_IDS = (1000, 1001, 1002)


def encode(text):
    """A toy tokenizer: one token per character; "\\n\\n" is one token."""
    ids, index = [], 0
    while index < len(text):
        if text.startswith("\n\n", index):
            ids.append(10_000)
            index += 2
        elif text[index] in SLOTS:
            ids.append(SLOT_IDS[SLOTS.index(text[index])])
            index += 1
        else:
            ids.append(100 + ord(text[index]))
            index += 1
    return ids


def text_of(content):
    if isinstance(content, list):
        return "".join(part["text"] for part in content if part["type"] == "text")
    return content or ""


def render(messages, tools=None):
    """A DeepSeek-like template; optional tool text precedes the system prompt."""
    ids = [BOS]
    if tools:
        ids += [TOOLS] + encode(tools)
    for message in messages:
        role, text = message["role"], text_of(message["content"])
        if role in ("system", "developer"):
            ids += encode(text)
        elif role == "user":
            ids += [USER] + encode(text)
        else:
            ids += [ASSISTANT] + encode(text) + [EOS]
    ids.append(ASSISTANT)
    return ids, ids


def make_cartridge(separator="\n\n", slots=SLOT_IDS):
    return cartridge.Cartridge(
        sha256="a" * 64,
        path="/unused",
        num_tokens=len(slots),
        hidden_size=4,
        separator=separator,
        slot_token_ids=tuple(slots),
        embeddings_offset=0,
    )


class PlacementTests(unittest.TestCase):
    def test_system_prompt_starts_with_the_slots_and_separator(self):
        messages = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
        ]

        ids, start = cartridge.place_cartridge(
            render, messages, make_cartridge(), SLOTS
        )

        self.assertEqual(start, 1)
        self.assertEqual(
            ids,
            render(
                [
                    {"role": "system", "content": SLOTS + "\n\nBe brief."},
                    {"role": "user", "content": "Hi"},
                ]
            )[0],
        )
        self.assertEqual(tuple(ids[start : start + 3]), SLOT_IDS)
        self.assertEqual(ids[start + 3], 10_000)

    def test_request_without_a_system_message_gets_an_empty_one(self):
        messages = [{"role": "user", "content": "Hi"}]

        ids, start = cartridge.place_cartridge(
            render, messages, make_cartridge(), SLOTS
        )

        self.assertEqual(start, 1)
        self.assertEqual(ids, [BOS, *SLOT_IDS, 10_000, USER, 172, 205, ASSISTANT])

    def test_multi_turn_conversation_places_the_slots_once_in_the_first_turn(self):
        messages = [
            {"role": "developer", "content": "Rules"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c" + SLOTS},
        ]

        ids, start = cartridge.place_cartridge(
            render, messages, make_cartridge(), SLOTS
        )

        self.assertEqual(start, 1)
        self.assertEqual(ids[1:5], [*SLOT_IDS, 10_000])
        self.assertEqual(ids[5:10], encode("Rules"))
        self.assertEqual(ids.count(SLOT_IDS[0]), 2)
        self.assertEqual(ids[-5:-1], [100 + ord("c"), *SLOT_IDS])

    def test_position_comes_from_the_render_not_from_matching_slot_tokens(self):
        def render_with_tools(messages):
            return render(messages, tools="use " + SLOTS)

        messages = [{"role": "user", "content": "Hi"}]

        ids, start = cartridge.place_cartridge(
            render_with_tools, messages, make_cartridge(), SLOTS
        )

        first_match = next(
            index
            for index in range(len(ids))
            if tuple(ids[index : index + 3]) == SLOT_IDS
        )
        self.assertLess(first_match, start)
        self.assertEqual(start, 2 + len(encode("use " + SLOTS)))
        self.assertEqual(tuple(ids[start : start + 3]), SLOT_IDS)

    def test_list_content_prefixes_the_first_text_part_or_adds_one(self):
        text_first = [{"type": "text", "text": "Be brief."}]
        image_first = [{"type": "image_url", "image_url": {"url": "x"}}]

        self.assertEqual(
            cartridge.system_prefixed([{"role": "system", "content": text_first}], "P"),
            [{"role": "system", "content": [{"type": "text", "text": "PBe brief."}]}],
        )
        self.assertEqual(
            cartridge.system_prefixed(
                [{"role": "system", "content": image_first}], "P"
            ),
            [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "P"}, *image_first],
                }
            ],
        )

    def test_custom_separator_and_a_system_message_after_the_first_turn(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "system", "content": "late"},
        ]

        ids, start = cartridge.place_cartridge(
            render, messages, make_cartridge(separator="|"), SLOTS
        )

        self.assertEqual(start, 1)
        self.assertEqual(ids[1:5], [*SLOT_IDS, 100 + ord("|")])

    def test_slots_merged_by_the_tokenizer_fail_closed(self):
        def merging(messages):
            ids, _ = render(messages)
            merged = []
            for token in ids:
                if merged and merged[-1] == SLOT_IDS[2] and token == 10_000:
                    merged[-1] = 20_000
                else:
                    merged.append(token)
            return merged, merged

        with self.assertRaises(cartridge.CartridgeError):
            cartridge.place_cartridge(
                merging, [{"role": "user", "content": "Hi"}], make_cartridge(), SLOTS
            )


class Ref:
    def __init__(self, sha256, num_tokens, start=1):
        self.sha256, self.num_tokens, self.start, self.path = (
            sha256,
            num_tokens,
            start,
            "",
        )


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.loaded = []
        self.pool = cartridge.CartridgePool(
            capacity_rows=8 * 4,
            load=lambda ref, rows: self.loaded.append((ref.sha256, list(rows))),
            page_rows=4,
        )

    def test_rows_follow_allocated_pages(self):
        self.pool.begin_round()
        self.assertTrue(self.pool.admit(Ref("a", 6), prefix_len=0))

        self.assertEqual(list(self.pool.rows("a")), [0, 1, 2, 3, 4, 5])
        self.assertEqual(self.loaded, [("a", [0, 1, 2, 3, 4, 5])])
        self.assertEqual(len(self.pool.free_pages), 6)

    def test_resident_cartridge_is_reused_without_a_load(self):
        self.pool.begin_round()
        self.pool.admit(Ref("a", 4), 0)
        self.pool.begin_round()
        self.pool.admit(Ref("a", 4), 0)

        self.assertEqual(len(self.loaded), 1)
        self.assertEqual(list(self.pool.rows("a")), [0, 1, 2, 3])

    def test_fully_cached_cartridge_needs_no_rows(self):
        self.pool.begin_round()
        self.assertTrue(self.pool.admit(Ref("a", 4, start=1), prefix_len=5))

        self.assertEqual(self.loaded, [])
        with self.assertRaises(RuntimeError):
            self.pool.rows("a")

    def test_least_recently_used_unprotected_cartridge_is_evicted(self):
        for name in "abcd":
            self.pool.begin_round()
            self.assertTrue(self.pool.admit(Ref(name, 8), 0))
        self.assertEqual(self.pool.free_pages, [])

        self.pool.begin_round()
        self.pool.admit(Ref("a", 8), 0)
        self.pool.begin_round()
        self.assertTrue(self.pool.admit(Ref("e", 8), 0))

        self.assertEqual(set(self.pool.resident), {"a", "c", "d", "e"})
        self.assertEqual(self.pool.evictions, 1)
        self.assertEqual(self.loaded[-1][1], [8, 9, 10, 11, 12, 13, 14, 15])

    def test_cartridges_of_the_last_two_rounds_are_never_evicted(self):
        self.pool.begin_round()
        self.pool.admit(Ref("a", 16), 0)
        self.pool.admit(Ref("b", 16), 0)
        self.pool.begin_round()

        self.assertFalse(self.pool.admit(Ref("c", 4), 0))
        self.assertEqual(set(self.pool.resident), {"a", "b"})

        self.pool.begin_round()
        self.assertTrue(self.pool.admit(Ref("c", 4), 0))
        self.assertEqual(set(self.pool.resident), {"b", "c"})

    def test_rows_are_only_valid_in_the_round_that_admitted_them(self):
        self.pool.begin_round()
        self.pool.admit(Ref("a", 4), 0)
        self.pool.begin_round()

        with self.assertRaises(RuntimeError):
            self.pool.rows("a")

    def test_failed_load_returns_its_pages(self):
        def fail(_ref, _rows):
            raise OSError("missing")

        self.pool.load = fail
        self.pool.begin_round()

        with self.assertRaises(OSError):
            self.pool.admit(Ref("a", 8), 0)
        self.assertEqual(len(self.pool.free_pages), 8)
        self.assertNotIn("a", self.pool.resident)

    def test_capacity_is_counted_in_whole_pages(self):
        self.assertTrue(self.pool.fits(32))
        self.assertFalse(self.pool.fits(33))
        self.pool.begin_round()
        self.assertFalse(self.pool.admit(Ref("big", 33), 0))
        with self.assertRaises(ValueError):
            cartridge.CartridgePool(3, lambda *_: None, page_rows=4)


class CacheIsolationTests(unittest.TestCase):
    def test_cache_namespace_shares_one_cartridge_and_isolates_others(self):
        first, second = "a" * 64, "b" * 64
        tokens = (0, *SLOT_IDS, 10_000)

        keys = {
            "first": (cartridge.extra_key(first, None), tokens),
            "first again": (cartridge.extra_key(first, None), tokens),
            "second": (cartridge.extra_key(second, None), tokens),
            "none": (None, tokens),
        }

        self.assertEqual(keys["first"], keys["first again"])
        self.assertEqual(len({keys[name] for name in ("first", "second", "none")}), 3)

    def test_caller_extra_key_stays_inside_the_cartridge_namespace(self):
        self.assertEqual(cartridge.extra_key("a" * 64, None), "cartridge:" + "a" * 64)
        self.assertEqual(
            cartridge.extra_key("a" * 64, "tenant"), "cartridge:" + "a" * 64 + "|tenant"
        )
        self.assertNotEqual(
            cartridge.extra_key("a" * 64, "x"), cartridge.extra_key("b" * 64, "x")
        )


class GatherIndexTests(unittest.TestCase):
    def test_mixed_batch_writes_only_cartridge_positions_of_this_extend(self):
        rows_a = [40, 41, 42, 43, 8, 9]
        rows_b = [100, 101, 102, 103]
        spans = [
            # No cartridge: never reaches gather_indices.
            # A: whole cartridge in this extend, after one BOS token.
            (5, 0, 10, 1, rows_a),
            # B: two cartridge rows already cached.
            (15, 3, 6, 1, rows_b),
            # A again: chunk ends inside the cartridge.
            (21, 0, 3, 1, rows_a),
            # A: next chunk of that request resumes inside the cartridge.
            (24, 3, 8, 1, rows_a),
            # B: cartridge fully cached.
            (32, 5, 4, 1, rows_b),
        ]

        dst, src = cartridge.gather_indices(spans)

        self.assertEqual(
            list(dst),
            [6, 7, 8, 9, 10, 11] + [15, 16] + [22, 23] + [24, 25, 26, 27],
        )
        self.assertEqual(
            list(src),
            rows_a + [102, 103] + [40, 41] + [42, 43, 8, 9],
        )

    def test_batch_without_cartridge_positions_has_no_indices(self):
        dst, src = cartridge.gather_indices(
            [(0, 10, 4, 1, [1, 2, 3]), (4, 0, 2, 1, None)]
        )

        self.assertEqual((len(dst), len(src)), (0, 0))
        self.assertEqual((dst.typecode, src.typecode), ("i", "i"))


class CartridgeFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write(self, header, data=b""):
        encoded = json.dumps(header).encode()
        path = self.root / f"{len(list(self.root.iterdir()))}.safetensors"
        path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + data)
        return str(path)

    def header(self, slots=True, metadata=None):
        header = {
            "__metadata__": metadata or {"format": "gradiated.cartridge/1"},
            "embeddings": {"dtype": "BF16", "shape": [3, 4], "data_offsets": [0, 24]},
        }
        if slots:
            header["slot_token_ids"] = {
                "dtype": "I64",
                "shape": [3],
                "data_offsets": [24, 48],
            }
        return header

    def read(self, path, **overrides):
        values = {
            "sha256": "a" * 64,
            "num_tokens": 3,
            "hidden_size": 4,
            "vocab_size": 2000,
        }
        return cartridge.read_cartridge(path, **{**values, **overrides})

    def test_header_slots_and_embedding_offset_are_read_without_the_embeddings(self):
        data = bytes(24) + struct.pack("<3q", *SLOT_IDS)
        path = self.write(
            self.header(metadata={"format": "gradiated.cartridge/1", "separator": "|"}),
            data,
        )

        spec = self.read(path)

        self.assertEqual(spec.slot_token_ids, SLOT_IDS)
        self.assertEqual(spec.separator, "|")
        self.assertEqual(spec.embeddings_nbytes, 24)
        self.assertEqual(spec.embeddings_offset, Path(path).stat().st_size - 48)

    def test_invalid_files_are_rejected(self):
        data = bytes(24) + struct.pack("<3q", *SLOT_IDS)
        cases = [
            (self.header(slots=False), bytes(24), {}),
            (self.header(metadata={"format": "other"}), data, {}),
            (self.header(), data, {"hidden_size": 8}),
            (self.header(), data, {"vocab_size": 1001}),
            (self.header(), data[:-1], {}),
        ]
        for header, body, overrides in cases:
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(cartridge.CartridgeError),
            ):
                self.read(self.write(header, body), **overrides)


if __name__ == "__main__":
    unittest.main()
