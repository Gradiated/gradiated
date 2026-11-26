//! Native tiktoken BPE and XTML prompt encoding for Kimi K3.1 releases.
//!
//! Adapted from the pinned `tokenization_kimi.py` and `encoding_k3.py` modules
//! shipped alongside `moonshotai/Kimi-K3.1-Pro` and
//! `yetalabs/Kimi-K3.1-Pro-abliterated`.

use std::{
    cmp::Reverse,
    collections::{BTreeMap, BinaryHeap, HashMap},
    fs,
    path::Path,
};

use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use fancy_regex::Regex;
use serde_json::{Map, Value};

use super::{ModelTokenizerError, TokenizerRequestError};
use crate::InferenceRequest;

const NUM_RESERVED_SPECIAL_TOKENS: u32 = 256;
const TIKTOKEN_MAX_ENCODE_CHARS: usize = 400_000;
const MAX_NO_WHITESPACES_CHARS: usize = 25_000;

const OPEN_TOKEN: &str = "<|open|>";
const CLOSE_TOKEN: &str = "<|close|>";
const SEP_TOKEN: &str = "<|sep|>";
const END_OF_MSG_TOKEN: &str = "<|end_of_msg|>";

const KIMI_PAT_STR: &str = concat!(
    r#"[\p{Han}]+"#,
    "|",
    r#"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?"#,
    "|",
    r#"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?"#,
    "|",
    r#"\p{N}{1,3}"#,
    "|",
    r#" ?[^\s\p{L}\p{N}]+[\r\n]*"#,
    "|",
    r#"\s*[\r\n]+"#,
    "|",
    r#"\s+(?!\S)"#,
    "|",
    r#"\s+"#,
);

pub(super) struct KimiK31Tokenizer {
    encoder: HashMap<Vec<u8>, u32>,
    decoder: HashMap<u32, Vec<u8>>,
    special_tokens: HashMap<String, u32>,
    pat_regex: Regex,
    special_regex: Regex,
}

impl KimiK31Tokenizer {
    pub(super) fn load(vocab_path: &Path, config_path: &Path) -> Result<Self, ModelTokenizerError> {
        let vocab_source = fs::read_to_string(vocab_path)?;
        let config_bytes = fs::read(config_path)?;
        let config: Value = serde_json::from_slice(&config_bytes)?;

        Self::from_sources(&vocab_source, &config)
    }

    pub(super) fn from_sources(
        vocab_source: &str,
        config: &Value,
    ) -> Result<Self, ModelTokenizerError> {
        let mut encoder = HashMap::new();
        let mut decoder = HashMap::new();

        for (line_number, raw_line) in vocab_source.lines().enumerate() {
            let line = raw_line.trim();
            if line.is_empty() {
                continue;
            }
            let mut parts = line.split_whitespace();
            let (Some(token_b64), Some(rank_str), None) =
                (parts.next(), parts.next(), parts.next())
            else {
                return Err(ModelTokenizerError::Tokenizer(format!(
                    "malformed tiktoken vocab line {}",
                    line_number + 1
                )));
            };
            let token_bytes = BASE64_STANDARD.decode(token_b64).map_err(|error| {
                ModelTokenizerError::Tokenizer(format!(
                    "invalid base64 on tiktoken line {}: {error}",
                    line_number + 1
                ))
            })?;
            let rank: u32 = rank_str.parse().map_err(|error| {
                ModelTokenizerError::Tokenizer(format!(
                    "invalid rank on tiktoken line {}: {error}",
                    line_number + 1
                ))
            })?;
            encoder.insert(token_bytes.clone(), rank);
            decoder.insert(rank, token_bytes);
        }

        if encoder.is_empty() {
            return Err(ModelTokenizerError::Tokenizer(
                "tiktoken vocab is empty".to_owned(),
            ));
        }

        let num_base_tokens = u32::try_from(encoder.len())
            .map_err(|_| ModelTokenizerError::Tokenizer("tiktoken vocab exceeds u32".to_owned()))?;

        let mut added_tokens = HashMap::new();
        if let Some(entries) = config
            .get("added_tokens_decoder")
            .and_then(Value::as_object)
        {
            for (id_str, entry) in entries {
                if let (Ok(id), Some(content)) = (
                    id_str.parse::<u32>(),
                    entry.get("content").and_then(Value::as_str),
                ) {
                    added_tokens.insert(id, content.to_owned());
                }
            }
        }

        let mut special_tokens = HashMap::with_capacity(NUM_RESERVED_SPECIAL_TOKENS as usize);
        let mut special_names = Vec::with_capacity(NUM_RESERVED_SPECIAL_TOKENS as usize);
        for offset in 0..NUM_RESERVED_SPECIAL_TOKENS {
            let id = num_base_tokens.checked_add(offset).ok_or_else(|| {
                ModelTokenizerError::Tokenizer("special token id overflow".into())
            })?;
            let token = added_tokens
                .remove(&id)
                .unwrap_or_else(|| format!("<|reserved_token_{id}|>"));
            decoder.insert(id, token.as_bytes().to_vec());
            special_names.push(token.clone());
            special_tokens.insert(token, id);
        }

        special_names
            .sort_by(|left, right| right.len().cmp(&left.len()).then_with(|| left.cmp(right)));
        let special_pattern = special_names
            .iter()
            .map(|token| escape_regex(token))
            .collect::<Vec<_>>()
            .join("|");

        let pat_regex = Regex::new(KIMI_PAT_STR).map_err(|error| {
            ModelTokenizerError::Tokenizer(format!("invalid Kimi regex: {error}"))
        })?;
        let special_regex = Regex::new(&special_pattern).map_err(|error| {
            ModelTokenizerError::Tokenizer(format!("invalid Kimi special regex: {error}"))
        })?;

        Ok(Self {
            encoder,
            decoder,
            special_tokens,
            pat_regex,
            special_regex,
        })
    }

    pub(super) fn encode_input(
        &self,
        request: &InferenceRequest,
    ) -> Result<Vec<u32>, TokenizerRequestError> {
        let segments = build_chat_segments(request)?;
        let mut ids = Vec::new();
        for segment in segments {
            self.encode_text_piece(&segment.text, segment.allow_special, &mut ids)?;
        }
        Ok(ids)
    }

    pub(super) fn decode(&self, token_ids: &[u32]) -> Result<String, ModelTokenizerError> {
        let mut bytes = Vec::new();
        for id in token_ids {
            if let Some(piece) = self.decoder.get(id) {
                bytes.extend_from_slice(piece);
            }
        }
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }

    fn encode_text_piece(
        &self,
        text: &str,
        allow_special: bool,
        out: &mut Vec<u32>,
    ) -> Result<(), TokenizerRequestError> {
        if text.is_empty() {
            return Ok(());
        }
        if allow_special {
            if let Some(&id) = self.special_tokens.get(text) {
                out.push(id);
                return Ok(());
            }
        }

        for chunk in char_chunks(text, TIKTOKEN_MAX_ENCODE_CHARS) {
            for slice in split_whitespaces_or_nonwhitespaces(chunk, MAX_NO_WHITESPACES_CHARS) {
                if allow_special {
                    self.encode_with_special(slice, out)?;
                } else {
                    self.encode_ordinary(slice, out)?;
                }
            }
        }

        Ok(())
    }

    fn encode_with_special(
        &self,
        text: &str,
        out: &mut Vec<u32>,
    ) -> Result<(), TokenizerRequestError> {
        let mut cursor = 0;
        while cursor < text.len() {
            let next_special = self
                .special_regex
                .find_from_pos(text, cursor)
                .map_err(|_| TokenizerRequestError::Encode)?;
            match next_special {
                Some(matched) => {
                    if matched.start() > cursor {
                        self.encode_ordinary(&text[cursor..matched.start()], out)?;
                    }
                    let &id = self
                        .special_tokens
                        .get(matched.as_str())
                        .ok_or(TokenizerRequestError::Encode)?;
                    out.push(id);
                    cursor = matched.end();
                }
                None => {
                    self.encode_ordinary(&text[cursor..], out)?;
                    break;
                }
            }
        }
        Ok(())
    }

    fn encode_ordinary(&self, text: &str, out: &mut Vec<u32>) -> Result<(), TokenizerRequestError> {
        let mut cursor = 0;
        while cursor < text.len() {
            let Some(matched) = self
                .pat_regex
                .find_from_pos(text, cursor)
                .map_err(|_| TokenizerRequestError::Encode)?
            else {
                return Err(TokenizerRequestError::Encode);
            };
            if matched.start() != cursor || matched.end() == matched.start() {
                return Err(TokenizerRequestError::Encode);
            }
            self.byte_pair_encode(matched.as_str().as_bytes(), out)?;
            cursor = matched.end();
        }
        Ok(())
    }

    fn byte_pair_encode(
        &self,
        piece: &[u8],
        out: &mut Vec<u32>,
    ) -> Result<(), TokenizerRequestError> {
        if let Some(&rank) = self.encoder.get(piece) {
            out.push(rank);
            return Ok(());
        }
        let len = piece.len();
        if len < 2 {
            return Err(TokenizerRequestError::Encode);
        }

        // Doubly-linked list of active token spans in `piece` paired with a
        // min-heap over `(merge_rank, left_start_index)` so long pieces merge
        // in O(L log L) instead of rescanning and shifting a Vec on each step.
        const NONE: usize = usize::MAX;
        let mut prev: Vec<usize> = (0..len)
            .map(|i| if i == 0 { NONE } else { i - 1 })
            .collect();
        let mut next: Vec<usize> = (0..len)
            .map(|i| if i + 1 < len { i + 1 } else { NONE })
            .collect();
        let mut span_end: Vec<usize> = (1..=len).collect();
        let mut alive = vec![true; len];
        let mut heap: BinaryHeap<Reverse<(u32, usize, usize)>> = BinaryHeap::new();

        let pair_rank = |left: usize, right: usize, span_end: &[usize]| -> Option<u32> {
            self.encoder.get(&piece[left..span_end[right]]).copied()
        };

        for left in 0..len - 1 {
            if let Some(rank) = pair_rank(left, left + 1, &span_end) {
                heap.push(Reverse((rank, left, left + 1)));
            }
        }

        while let Some(Reverse((rank, left, right))) = heap.pop() {
            // Skip stale heap entries invalidated by an earlier adjacent merge.
            if !alive[left] || !alive[right] || next[left] != right {
                continue;
            }
            if pair_rank(left, right, &span_end) != Some(rank) {
                continue;
            }

            // Merge `right` into `left`.
            let after = next[right];
            span_end[left] = span_end[right];
            next[left] = after;
            if after != NONE {
                prev[after] = left;
            }
            alive[right] = false;

            // Enqueue newly formed pairs with `left`'s neighbors.
            let before = prev[left];
            if before != NONE {
                if let Some(new_rank) = pair_rank(before, left, &span_end) {
                    heap.push(Reverse((new_rank, before, left)));
                }
            }
            if after != NONE {
                if let Some(new_rank) = pair_rank(left, after, &span_end) {
                    heap.push(Reverse((new_rank, left, after)));
                }
            }
        }

        let mut cursor = 0;
        while cursor != NONE {
            let &rank = self
                .encoder
                .get(&piece[cursor..span_end[cursor]])
                .ok_or(TokenizerRequestError::Encode)?;
            out.push(rank);
            cursor = next[cursor];
        }

        Ok(())
    }
}

pub(super) fn is_kimi_tiktoken_config(path: &Path) -> Result<bool, ModelTokenizerError> {
    let config: Value = serde_json::from_slice(&fs::read(path)?)?;
    Ok(
        config.get("tokenizer_class").and_then(Value::as_str) == Some("TikTokenTokenizer")
            && config
                .pointer("/auto_map/AutoTokenizer/0")
                .and_then(Value::as_str)
                == Some("tokenization_kimi.TikTokenTokenizer"),
    )
}

fn escape_regex(literal: &str) -> String {
    let mut escaped = String::with_capacity(literal.len() + 8);
    for ch in literal.chars() {
        if matches!(
            ch,
            '\\' | '.' | '+' | '*' | '?' | '(' | ')' | '|' | '[' | ']' | '{' | '}' | '^' | '$'
        ) {
            escaped.push('\\');
        }
        escaped.push(ch);
    }
    escaped
}

fn char_chunks(text: &str, max_chars: usize) -> impl Iterator<Item = &str> {
    let mut start = 0;
    std::iter::from_fn(move || {
        if start >= text.len() {
            return None;
        }
        let mut end = text.len();
        for (count, (offset, _)) in text[start..].char_indices().enumerate() {
            if count == max_chars {
                end = start + offset;
                break;
            }
        }
        let chunk = &text[start..end];
        start = end;
        Some(chunk)
    })
}

fn split_whitespaces_or_nonwhitespaces(text: &str, max_run: usize) -> Vec<&str> {
    if text.is_empty() {
        return Vec::new();
    }
    let mut slices = Vec::new();
    let mut current_len = 0usize;
    let mut current_is_space = text.chars().next().is_some_and(char::is_whitespace);
    let mut slice_start = 0usize;

    for (byte_idx, ch) in text.char_indices() {
        let is_space = ch.is_whitespace();
        if current_is_space ^ is_space {
            current_len = 1;
            current_is_space = is_space;
        } else {
            current_len += 1;
            if current_len > max_run {
                slices.push(&text[slice_start..byte_idx]);
                slice_start = byte_idx;
                current_len = 1;
            }
        }
    }
    slices.push(&text[slice_start..]);
    slices
}

#[derive(Debug, Eq, PartialEq)]
struct EncodeSegment {
    text: String,
    allow_special: bool,
}

fn push_segment(segments: &mut Vec<EncodeSegment>, text: impl Into<String>, allow_special: bool) {
    let text = text.into();
    if !text.is_empty() {
        segments.push(EncodeSegment {
            text,
            allow_special,
        });
    }
}

fn push_control(segments: &mut Vec<EncodeSegment>, token: &str) {
    push_segment(segments, token, true);
}

fn push_text(segments: &mut Vec<EncodeSegment>, text: impl Into<String>) {
    push_segment(segments, text, false);
}

fn escape_attr_value(value: &str) -> String {
    value.replace('&', "&amp;").replace('"', "&quot;")
}

fn push_attr(segments: &mut Vec<EncodeSegment>, key: &str, value: &str) {
    push_text(segments, format!(" {key}"));
    push_text(segments, "=\"");
    push_text(segments, escape_attr_value(value));
    push_text(segments, "\"");
}

fn push_open_tag(segments: &mut Vec<EncodeSegment>, tag: &str, attrs: &[(&str, String)]) {
    push_control(segments, OPEN_TOKEN);
    push_text(segments, tag);
    for (key, value) in attrs {
        push_attr(segments, key, value);
    }
    push_control(segments, SEP_TOKEN);
}

fn push_close_tag(segments: &mut Vec<EncodeSegment>, tag: &str) {
    push_control(segments, CLOSE_TOKEN);
    push_text(segments, tag);
    push_control(segments, SEP_TOKEN);
}

fn push_end_of_msg(segments: &mut Vec<EncodeSegment>) {
    push_control(segments, END_OF_MSG_TOKEN);
}

fn push_internal_system_message(segments: &mut Vec<EncodeSegment>, message_type: &str, body: &str) {
    push_open_tag(
        segments,
        "message",
        &[
            ("role", "system".to_owned()),
            ("type", message_type.to_owned()),
        ],
    );
    push_text(segments, body.trim());
    push_close_tag(segments, "message");
    push_end_of_msg(segments);
}

fn push_tool_declare(segments: &mut Vec<EncodeSegment>, tools: &Value, dynamic: bool) {
    let sorted = deep_sort_json(tools);
    let rendered = json_compact(&sorted);
    let body = if dynamic {
        format!(
            "## New Tools Available\n\
             The system dynamically extends the toolset via lazy-loading.\n\
             You have access to all existing and extended tools.\n\
             Here are the specs for the extended tools.\n\n\
             ```json\n{rendered}\n```"
        )
    } else {
        format!(
            "# Tools\n\
             Here are the available tools, described in JSONSchema.\n\n\
             ```json\n{rendered}\n```"
        )
    };
    push_open_tag(
        segments,
        "message",
        &[
            ("role", "system".to_owned()),
            ("type", "tool-declare".to_owned()),
        ],
    );
    push_text(segments, body);
    push_close_tag(segments, "message");
    push_end_of_msg(segments);
}

fn deep_sort_json(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let sorted: BTreeMap<&String, Value> = map
                .iter()
                .map(|(key, value)| (key, deep_sort_json(value)))
                .collect();
            let mut out = Map::with_capacity(sorted.len());
            for (key, value) in sorted {
                out.insert(key.clone(), value);
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.iter().map(deep_sort_json).collect()),
        other => other.clone(),
    }
}

fn json_compact(value: &Value) -> String {
    serde_json::to_string(value).expect("serde_json::Value serializes")
}

// Match Python `json.dumps(value, ensure_ascii=False)` default spacing.
fn python_json(value: &Value) -> String {
    match value {
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_json)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!(
                    "{}: {}",
                    json_compact(&Value::String(key.clone())),
                    python_json(value)
                ))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        _ => json_compact(value),
    }
}

fn xtml_type(value: &Value) -> &'static str {
    match value {
        Value::Bool(_) => "boolean",
        Value::Null => "null",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Object(_) => "object",
        Value::Array(_) => "array",
    }
}

fn xtml_value(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => python_json(other),
    }
}

struct XtmlArgument {
    key: String,
    arg_type: &'static str,
    text: String,
}

enum NormalizedArguments {
    Pairs(Vec<XtmlArgument>),
    RawJson(String),
}

fn normalize_tool_arguments(
    arguments: Option<&Value>,
) -> Result<NormalizedArguments, TokenizerRequestError> {
    match arguments {
        None | Some(Value::Null) => Ok(NormalizedArguments::Pairs(Vec::new())),
        Some(Value::Object(map)) => Ok(NormalizedArguments::Pairs(
            map.iter()
                .map(|(key, value)| XtmlArgument {
                    key: key.clone(),
                    arg_type: xtml_type(value),
                    text: xtml_value(value),
                })
                .collect(),
        )),
        Some(Value::String(text)) => {
            if text.is_empty() {
                return Ok(NormalizedArguments::Pairs(Vec::new()));
            }
            match parse_arguments_object(text) {
                Ok(pairs) => Ok(NormalizedArguments::Pairs(pairs)),
                Err(()) => Ok(NormalizedArguments::RawJson(text.clone())),
            }
        }
        Some(_) => Err(TokenizerRequestError::InvalidInput),
    }
}

/// Parses a JSON object string one level deep, preserving exact source bytes
/// for non-string values and decoded strings for string values.
fn parse_arguments_object(source: &str) -> Result<Vec<XtmlArgument>, ()> {
    let bytes = source.as_bytes();
    let mut idx = 0usize;

    let skip_ws = |idx: &mut usize| {
        while *idx < bytes.len() && matches!(bytes[*idx], b' ' | b'\t' | b'\n' | b'\r') {
            *idx += 1;
        }
    };

    skip_ws(&mut idx);
    if bytes.get(idx) != Some(&b'{') {
        return Err(());
    }
    idx += 1;
    skip_ws(&mut idx);

    let mut parsed = Vec::new();
    if idx >= bytes.len() {
        return Err(());
    }
    if bytes[idx] == b'}' {
        return Ok(parsed);
    }

    loop {
        let (key_val, next_idx) = raw_decode_json_value(source, idx)?;
        let Value::String(key) = key_val else {
            return Err(());
        };
        idx = next_idx;
        skip_ws(&mut idx);
        if bytes.get(idx) != Some(&b':') {
            return Err(());
        }
        idx += 1;
        skip_ws(&mut idx);

        let value_start = idx;
        let (decoded_value, value_end) = raw_decode_json_value(source, value_start)?;
        idx = value_end;

        let arg_type = xtml_type(&decoded_value);
        let text = match decoded_value {
            Value::String(decoded) => decoded,
            _ => source[value_start..value_end].to_owned(),
        };
        parsed.push(XtmlArgument {
            key,
            arg_type,
            text,
        });

        skip_ws(&mut idx);
        match bytes.get(idx) {
            Some(b'}') => break,
            Some(b',') => {
                idx += 1;
                skip_ws(&mut idx);
            }
            _ => return Err(()),
        }
    }

    Ok(parsed)
}

fn raw_decode_json_value(source: &str, start: usize) -> Result<(Value, usize), ()> {
    let slice = source.get(start..).ok_or(())?;
    let mut stream = serde_json::Deserializer::from_str(slice).into_iter::<Value>();
    let value = stream.next().ok_or(())?.map_err(|_| ())?;
    let consumed = stream.byte_offset();
    Ok((value, start + consumed))
}

fn tool_call_id_index(tool_calls: &Value) -> HashMap<String, (usize, Option<String>)> {
    let mut index = HashMap::new();
    let Some(calls) = tool_calls.as_array() else {
        return index;
    };
    for (offset, call) in calls.iter().enumerate() {
        let Some(object) = call.as_object() else {
            continue;
        };
        let Some(call_id) = object.get("id").filter(|id| !id.is_null()) else {
            continue;
        };
        let key = value_to_string(call_id);
        if index.contains_key(&key) {
            continue;
        }
        let name = object
            .get("function")
            .and_then(Value::as_object)
            .and_then(|function| function.get("name"))
            .or_else(|| object.get("name"))
            .and_then(Value::as_str)
            .map(str::to_owned);
        index.insert(key, (offset + 1, name));
    }
    index
}

fn normalize_xtml_tool_result_messages(messages: &[Value]) -> Vec<Value> {
    let mut output = Vec::with_capacity(messages.len());
    let mut current_index: HashMap<String, (usize, Option<String>)> = HashMap::new();
    let mut i = 0;

    while i < messages.len() {
        let message = &messages[i];
        let role = message.get("role").and_then(Value::as_str);

        if role == Some("assistant") {
            current_index = message
                .get("tool_calls")
                .filter(|calls| calls.as_array().is_some_and(|arr| !arr.is_empty()))
                .map(tool_call_id_index)
                .unwrap_or_default();
            output.push(message.clone());
            i += 1;
            continue;
        }

        if role != Some("tool") {
            output.push(message.clone());
            i += 1;
            continue;
        }

        let mut run: Vec<(Option<usize>, usize, &Value, Option<String>)> = Vec::new();
        let mut unresolved = false;
        let mut offset = 0usize;
        while i < messages.len() && messages[i].get("role").and_then(Value::as_str) == Some("tool")
        {
            let tool_message = &messages[i];
            let call_id = tool_message
                .get("tool_call_id")
                .or_else(|| tool_message.get("id"))
                .filter(|id| !id.is_null());
            let matched = call_id.and_then(|id| current_index.get(&value_to_string(id)));
            match matched {
                Some((position, name)) => {
                    run.push((Some(*position), offset, tool_message, name.clone()));
                }
                None => {
                    unresolved = true;
                    run.push((None, offset, tool_message, None));
                }
            }
            offset += 1;
            i += 1;
        }

        if unresolved {
            for (_, _, tool_message, _) in run {
                output.push(tool_message.clone());
            }
        } else {
            run.sort_by_key(|(position, original_offset, _, _)| {
                (position.unwrap(), *original_offset)
            });
            for (_, _, tool_message, name) in run {
                match name {
                    Some(name) => {
                        let mut resolved = tool_message.clone();
                        if let Some(object) = resolved.as_object_mut() {
                            object.insert("tool".to_owned(), Value::String(name.clone()));
                            if object.contains_key("name") {
                                object.insert("name".to_owned(), Value::String(name));
                            }
                        }
                        output.push(resolved);
                    }
                    None => output.push(tool_message.clone()),
                }
            }
        }
    }

    output
}

fn value_to_string(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        other => other.to_string(),
    }
}

fn push_content_segments(
    segments: &mut Vec<EncodeSegment>,
    content: Option<&Value>,
) -> Result<(), TokenizerRequestError> {
    match content {
        None | Some(Value::Null) => Ok(()),
        Some(Value::String(text)) => {
            push_text(segments, text.as_str());
            Ok(())
        }
        Some(Value::Array(parts)) => {
            for part in parts {
                let part_type = part.get("type").and_then(Value::as_str);
                if matches!(part_type, Some("image" | "image_url")) {
                    return Err(TokenizerRequestError::Rejected);
                }
                let text = part
                    .get("text")
                    .and_then(Value::as_str)
                    .ok_or(TokenizerRequestError::InvalidInput)?;
                push_text(segments, text);
            }
            Ok(())
        }
        Some(_) => Err(TokenizerRequestError::InvalidInput),
    }
}

struct ThinkingOptions {
    thinking: bool,
    effort: Option<&'static str>,
}

fn parse_thinking_options(
    request: &InferenceRequest,
) -> Result<ThinkingOptions, TokenizerRequestError> {
    let kwargs = request.parameters.get("chat_template_kwargs");
    let kwarg = |name: &str| kwargs.and_then(|value| value.get(name));

    let mut thinking = if request.continue_final_message {
        false
    } else {
        match kwarg("thinking") {
            None | Some(Value::Null) => match request
                .parameters
                .get("reasoning")
                .and_then(|value| value.get("enabled"))
            {
                Some(Value::Bool(enabled)) => *enabled,
                None | Some(Value::Null) => true,
                Some(_) => return Err(TokenizerRequestError::InvalidParameter("reasoning")),
            },
            Some(Value::Bool(enabled)) => *enabled,
            Some(_) => {
                return Err(TokenizerRequestError::InvalidParameter(
                    "chat_template_kwargs.thinking",
                ))
            }
        }
    };

    let (raw_effort, param_name) = if let Some(value) = kwarg("thinking_effort") {
        (Some(value), "chat_template_kwargs.thinking_effort")
    } else if let Some(value) = kwarg("reasoning_effort") {
        (Some(value), "chat_template_kwargs.reasoning_effort")
    } else if let Some(value) = request.parameters.get("reasoning_effort") {
        (Some(value), "reasoning_effort")
    } else if let Some(value) = request
        .parameters
        .get("reasoning")
        .and_then(|value| value.get("effort"))
    {
        (Some(value), "reasoning")
    } else {
        (None, "reasoning_effort")
    };

    let effort = match raw_effort {
        None | Some(Value::Null) => Some("max"),
        Some(Value::String(value)) => match value.as_str() {
            "low" => Some("low"),
            "high" => Some("high"),
            "max" => Some("max"),
            "none" => {
                thinking = false;
                None
            }
            _ => return Err(TokenizerRequestError::InvalidParameter(param_name)),
        },
        Some(_) => return Err(TokenizerRequestError::InvalidParameter(param_name)),
    };

    Ok(ThinkingOptions { thinking, effort })
}

fn extract_response_schema(response_format: &Value) -> Option<&Value> {
    let json_schema = response_format.get("json_schema")?;
    if let Some(object) = json_schema.as_object() {
        object
            .get("schema")
            .or_else(|| object.get("json_schema"))
            .or(Some(json_schema))
    } else {
        Some(json_schema)
    }
}

fn build_chat_segments(
    request: &InferenceRequest,
) -> Result<Vec<EncodeSegment>, TokenizerRequestError> {
    let options = parse_thinking_options(request)?;
    let messages = normalize_xtml_tool_result_messages(&request.messages);

    let mut segments = Vec::new();
    let mut last_tool_calls: Option<&Vec<Value>> = None;
    let mut tool_index = 0usize;

    if let Some(tools) = request.parameters.get("tools") {
        if tools.as_array().is_some_and(|items| !items.is_empty()) {
            push_tool_declare(&mut segments, tools, false);
        }
    }

    if options.thinking {
        if let Some(effort) = options.effort {
            push_internal_system_message(
                &mut segments,
                "thinking-effort",
                &format!(
                    "`thinking_effort` guides on how much to think in your \
                     thinking channel (not including the response channel), \
                     supported values include `low`, `medium`, `high`, and `max`.\n\
                     Now the system is invoked with `thinking_effort={effort}`."
                ),
            );
        }
    }

    let last_index = messages.len().saturating_sub(1);
    for (message_index, message) in messages.iter().enumerate() {
        let Some(object) = message.as_object() else {
            return Err(TokenizerRequestError::InvalidInput);
        };
        let role = object.get("role").and_then(Value::as_str);
        let name_attr = object
            .get("name")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty());

        match role {
            Some("user") => {
                let mut attrs = vec![("role", "user".to_owned())];
                if let Some(name) = name_attr {
                    attrs.push(("name", name.to_owned()));
                }
                push_open_tag(&mut segments, "message", &attrs);
                push_content_segments(&mut segments, object.get("content"))?;
                push_close_tag(&mut segments, "message");
                push_end_of_msg(&mut segments);
            }
            Some("system")
                if object
                    .get("tools")
                    .is_some_and(|tools| tools.as_array().is_some_and(|a| !a.is_empty())) =>
            {
                push_tool_declare(&mut segments, &object["tools"], true);
            }
            Some("system") => {
                let mut attrs = vec![("role", "system".to_owned())];
                if let Some(name) = name_attr {
                    attrs.push(("name", name.to_owned()));
                }
                push_open_tag(&mut segments, "message", &attrs);
                push_content_segments(&mut segments, object.get("content"))?;
                push_close_tag(&mut segments, "message");
                push_end_of_msg(&mut segments);
            }
            Some("tool") => {
                tool_index += 1;
                let mut tool_name = object
                    .get("tool")
                    .or_else(|| object.get("name"))
                    .and_then(Value::as_str);
                if tool_name.is_none() {
                    if let Some(calls) = last_tool_calls {
                        if let Some(call) = calls.get(tool_index - 1) {
                            tool_name = call
                                .get("function")
                                .and_then(|function| function.get("name"))
                                .or_else(|| call.get("name"))
                                .and_then(Value::as_str);
                        }
                    }
                }
                let tool_name = tool_name.ok_or(TokenizerRequestError::InvalidInput)?;
                push_open_tag(
                    &mut segments,
                    "message",
                    &[
                        ("role", "tool".to_owned()),
                        ("tool", tool_name.to_owned()),
                        ("index", tool_index.to_string()),
                    ],
                );
                push_content_segments(&mut segments, object.get("content"))?;
                push_close_tag(&mut segments, "message");
                push_end_of_msg(&mut segments);
            }
            Some("assistant") => {
                last_tool_calls = object.get("tool_calls").and_then(Value::as_array);
                tool_index = 0;

                let continue_this = request.continue_final_message && message_index == last_index;
                let mut attrs = vec![("role", "assistant".to_owned())];
                if let Some(name) = name_attr {
                    attrs.push(("name", name.to_owned()));
                }
                push_open_tag(&mut segments, "message", &attrs);

                if options.thinking {
                    let reasoning = object
                        .get("reasoning_content")
                        .filter(|value| !value.is_null() && value.as_str() != Some(""))
                        .or_else(|| {
                            object
                                .get("reasoning")
                                .filter(|value| !value.is_null() && value.as_str() != Some(""))
                        });
                    push_open_tag(&mut segments, "think", &[]);
                    if let Some(reasoning) = reasoning {
                        push_text(&mut segments, value_to_string(reasoning));
                    }
                    push_close_tag(&mut segments, "think");
                }

                push_open_tag(&mut segments, "response", &[]);
                push_content_segments(&mut segments, object.get("content"))?;
                if continue_this {
                    continue;
                }
                push_close_tag(&mut segments, "response");

                if let Some(calls) = last_tool_calls.filter(|calls| !calls.is_empty()) {
                    push_open_tag(&mut segments, "tools", &[]);
                    for (index, call) in calls.iter().enumerate() {
                        let fn_obj = call.get("function").unwrap_or(call);
                        let fn_name = fn_obj
                            .get("name")
                            .and_then(Value::as_str)
                            .ok_or(TokenizerRequestError::InvalidInput)?;
                        push_open_tag(
                            &mut segments,
                            "call",
                            &[
                                ("tool", fn_name.to_owned()),
                                ("index", (index + 1).to_string()),
                            ],
                        );
                        match normalize_tool_arguments(fn_obj.get("arguments"))? {
                            NormalizedArguments::RawJson(raw) => {
                                push_open_tag(
                                    &mut segments,
                                    "json",
                                    &[("type", "object".to_owned())],
                                );
                                push_text(&mut segments, raw);
                                push_close_tag(&mut segments, "json");
                            }
                            NormalizedArguments::Pairs(args) => {
                                for arg in args {
                                    push_open_tag(
                                        &mut segments,
                                        "argument",
                                        &[("key", arg.key), ("type", arg.arg_type.to_owned())],
                                    );
                                    push_text(&mut segments, arg.text);
                                    push_close_tag(&mut segments, "argument");
                                }
                            }
                        }
                        push_close_tag(&mut segments, "call");
                    }
                    push_close_tag(&mut segments, "tools");
                }

                push_close_tag(&mut segments, "message");
                push_end_of_msg(&mut segments);
            }
            _ => return Err(TokenizerRequestError::InvalidInput),
        }
    }

    match request
        .parameters
        .get("tool_choice")
        .and_then(Value::as_str)
    {
        Some("required") => push_internal_system_message(
            &mut segments,
            "tool-choice",
            "The system is invoked with `tool_choice=required`.\n\
             You MUST call tools in the next message.",
        ),
        Some("none") => push_internal_system_message(
            &mut segments,
            "tool-choice",
            "The system is invoked with `tool_choice=none`.\n\
             You MUST NOT call any tools in the next message.",
        ),
        _ => {}
    }

    if let Some(response_format) = request.parameters.get("response_format") {
        let rf_type = response_format
            .get("type")
            .and_then(Value::as_str)
            .or_else(|| response_format.as_str());
        match rf_type {
            Some("json_object") => push_internal_system_message(
                &mut segments,
                "response-format",
                "The system is invoked with `response_format=json_object`.\n\
                 Your response must be raw JSON data without markdown code \
                 blocks (```json) or any additional formatting.",
            ),
            Some("json_schema") => {
                let schema = extract_response_schema(response_format)
                    .map(deep_sort_json)
                    .unwrap_or(Value::Null);
                let rendered = json_compact(&schema);
                push_internal_system_message(
                    &mut segments,
                    "response-format",
                    &format!(
                        "The system is invoked with `response_format=json_schema`.\n\
                         Your response must be raw JSON data without markdown code \
                         blocks (```json) or any additional formatting.\n\
                         The JSON data must match the following schema:\n\
                         ```json\n{rendered}\n```"
                    ),
                );
            }
            _ => {}
        }
    }

    if !request.continue_final_message {
        push_open_tag(
            &mut segments,
            "message",
            &[("role", "assistant".to_owned())],
        );
        push_open_tag(
            &mut segments,
            if options.thinking {
                "think"
            } else {
                "response"
            },
            &[],
        );
    }

    Ok(segments)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn synthetic_tokenizer() -> KimiK31Tokenizer {
        let mut lines = Vec::new();
        for byte in 0u8..=255 {
            lines.push(format!("{} {}", BASE64_STANDARD.encode([byte]), byte));
        }
        // Add multi-byte merges with an unambiguous BPE merge chain:
        // h+e -> he (256), l+l -> ll (257), he+ll -> hell (258), hell+o -> hello (259).
        for (offset, token) in [b"he".as_slice(), b"ll", b"hell", b"hello"]
            .into_iter()
            .enumerate()
        {
            lines.push(format!(
                "{} {}",
                BASE64_STANDARD.encode(token),
                256 + offset
            ));
        }
        let base = 256 + 4;
        let config = json!({
            "tokenizer_class": "TikTokenTokenizer",
            "auto_map": {
                "AutoTokenizer": ["tokenization_kimi.TikTokenTokenizer", null]
            },
            "added_tokens_decoder": {
                (base).to_string(): {"content": "[BOS]"},
                (base + 1).to_string(): {"content": "[EOS]"},
                (base + 2).to_string(): {"content": "<|end_of_msg|>"},
                (base + 3).to_string(): {"content": "<|open|>"},
                (base + 4).to_string(): {"content": "<|close|>"},
                (base + 5).to_string(): {"content": "<|sep|>"}
            }
        });

        KimiK31Tokenizer::from_sources(&lines.join("\n"), &config).unwrap()
    }

    fn request(body: Value) -> InferenceRequest {
        serde_json::from_value(body).unwrap()
    }

    #[test]
    fn encodes_control_markers_as_special_tokens_and_user_text_literally() {
        let tokenizer = synthetic_tokenizer();
        let req = request(json!({
            "model": "moonshotai/kimi-k3.1-pro",
            "messages": [{"role": "user", "content": "hello <|open|> world"}]
        }));

        let ids = tokenizer.encode_input(&req).unwrap();
        let open_id = tokenizer.special_tokens[OPEN_TOKEN];
        let close_id = tokenizer.special_tokens[CLOSE_TOKEN];
        let sep_id = tokenizer.special_tokens[SEP_TOKEN];
        let eom_id = tokenizer.special_tokens[END_OF_MSG_TOKEN];

        // Structural open tags: thinking-effort message, user message, assistant message, think tag = 4.
        // The `<|open|>` inside user text must NOT produce a 5th open special token.
        assert_eq!(ids.iter().filter(|&&id| id == open_id).count(), 4);
        assert_eq!(ids.iter().filter(|&&id| id == close_id).count(), 2);
        assert_eq!(ids.iter().filter(|&&id| id == sep_id).count(), 6);
        assert_eq!(ids.iter().filter(|&&id| id == eom_id).count(), 2);
        // "hello" merged to its single BPE token (259).
        assert!(ids.contains(&259));
    }

    #[test]
    fn reorders_tool_results_and_preserves_raw_non_string_argument_literals() {
        let req = request(json!({
            "model": "moonshotai/kimi-k3.1-pro",
            "messages": [
                {"role": "user", "content": "Run tools"},
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "plan",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "first", "arguments": "{\"n\":1e2,\"s\":\"a\\\"b\"}"}},
                        {"id": "c2", "type": "function", "function": {"name": "second", "arguments": "not-json"}}
                    ]
                },
                {"role": "tool", "tool_call_id": "c2", "content": "res2"},
                {"role": "tool", "tool_call_id": "c1", "content": "res1"}
            ]
        }));

        let rendered: String = build_chat_segments(&req)
            .unwrap()
            .into_iter()
            .map(|seg| seg.text)
            .collect();

        assert!(rendered.contains(
            r#"<|open|>argument key="n" type="number"<|sep|>1e2<|close|>argument<|sep|>"#
        ));
        assert!(rendered.contains(
            r#"<|open|>argument key="s" type="string"<|sep|>a"b<|close|>argument<|sep|>"#
        ));
        assert!(
            rendered.contains(r#"<|open|>json type="object"<|sep|>not-json<|close|>json<|sep|>"#)
        );
        let first_pos = rendered
            .find(r#"<|open|>message role="tool" tool="first" index="1"<|sep|>res1"#)
            .expect("first tool result reordered first");
        let second_pos = rendered
            .find(r#"<|open|>message role="tool" tool="second" index="2"<|sep|>res2"#)
            .expect("second tool result reordered second");
        assert!(first_pos < second_pos);
    }

    #[test]
    fn renders_tools_thinking_effort_tool_choice_and_response_format() {
        let req = request(json!({
            "model": "moonshotai/kimi-k3.1-pro",
            "reasoning_effort": "low",
            "tool_choice": "required",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "out",
                    "schema": {"type": "object", "properties": {"b": {"type": "string"}, "a": {"type": "number"}}}
                }
            },
            "tools": [{"type": "function", "function": {"name": "ping", "parameters": {"b": 2, "a": 1}}}],
            "messages": [{"role": "user", "content": "Hi"}]
        }));

        let rendered: String = build_chat_segments(&req)
            .unwrap()
            .into_iter()
            .map(|seg| seg.text)
            .collect();

        assert!(rendered.contains("`thinking_effort=low`."));
        assert!(rendered.contains(r#"{"a":1,"b":2}"#));
        assert!(rendered.contains("`tool_choice=required`"));
        assert!(rendered.contains("`response_format=json_schema`"));
        assert!(rendered.contains(
            r#"{"properties":{"a":{"type":"number"},"b":{"type":"string"}},"type":"object"}"#
        ));
        assert!(rendered.ends_with("<|open|>message role=\"assistant\"<|sep|><|open|>think<|sep|>"));
    }

    #[test]
    fn rejects_invalid_effort_and_image_parts() {
        let bad_effort = request(json!({
            "model": "moonshotai/kimi-k3.1-pro",
            "reasoning_effort": "turbo",
            "messages": [{"role": "user", "content": "Hi"}]
        }));
        assert_eq!(
            build_chat_segments(&bad_effort),
            Err(TokenizerRequestError::InvalidParameter("reasoning_effort"))
        );

        let image = request(json!({
            "model": "moonshotai/kimi-k3.1-pro",
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}]}]
        }));
        assert_eq!(
            build_chat_segments(&image),
            Err(TokenizerRequestError::Rejected)
        );
    }

    #[test]
    fn encodes_max_length_unbroken_piece_in_sublinear_time_per_merge() {
        let tokenizer = synthetic_tokenizer();
        let long_piece = "hello".repeat(5_000); // 25,000 chars, full MAX_NO_WHITESPACES_CHARS run
        let mut out = Vec::new();
        tokenizer
            .byte_pair_encode(long_piece.as_bytes(), &mut out)
            .unwrap();
        // Every "hello" merges cleanly to token 259 via h+e -> he, l+l -> ll, he+ll -> hell, hell+o -> hello.
        assert_eq!(out.len(), 5_000);
        assert!(out.iter().all(|&id| id == 259));
    }
}
