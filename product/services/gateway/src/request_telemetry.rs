use serde::Serialize;
use serde_json::Value;

use crate::protocol::Protocol;

const MAX_NODES: u64 = 4096;
const MAX_DEPTH: u64 = 32;
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub(crate) struct RoleCounts {
    pub system: u64,
    pub developer: u64,
    pub user: u64,
    pub assistant: u64,
    pub tool: u64,
    pub other: u64,
}

impl RoleCounts {
    fn add(&mut self, role: &str, count: u64) {
        let value = match role {
            "system" => &mut self.system,
            "developer" => &mut self.developer,
            "user" => &mut self.user,
            "assistant" => &mut self.assistant,
            "tool" => &mut self.tool,
            _ => &mut self.other,
        };
        *value = value.saturating_add(count);
    }
}

#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub(crate) struct ContentCounts {
    pub text: u64,
    pub image: u64,
    pub audio: u64,
    pub video: u64,
    pub file: u64,
    pub other: u64,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub(crate) struct SchemaCounts {
    pub nodes: u64,
    pub properties: u64,
    pub required: u64,
    pub enum_values: u64,
    pub max_depth: u64,
    pub truncated: bool,
}

impl SchemaCounts {
    fn visit(&mut self, schema: &Value, depth: u64) {
        if self.nodes >= MAX_NODES || depth > MAX_DEPTH {
            self.truncated = true;
            return;
        }

        self.nodes += 1;
        self.max_depth = self.max_depth.max(depth);
        self.required += array_len(schema.get("required"));
        self.enum_values += array_len(schema.get("enum"));
        for name in ["properties", "$defs", "definitions", "patternProperties"] {
            if let Some(fields) = schema.get(name).and_then(Value::as_object) {
                if name == "properties" {
                    self.properties += fields.len() as u64;
                }
                for child in fields.values() {
                    if self.nodes == MAX_NODES {
                        self.truncated = true;
                        break;
                    }
                    self.visit(child, depth + 1);
                }
            }
        }
        for name in [
            "items",
            "additionalProperties",
            "contains",
            "not",
            "if",
            "then",
            "else",
        ] {
            if let Some(child) = schema.get(name) {
                if child.is_object() || child.is_boolean() {
                    self.visit(child, depth + 1);
                }
            }
        }
        for name in ["allOf", "anyOf", "oneOf", "prefixItems"] {
            if let Some(children) = schema.get(name).and_then(Value::as_array) {
                for child in children {
                    if self.nodes == MAX_NODES {
                        self.truncated = true;
                        break;
                    }
                    self.visit(child, depth + 1);
                }
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct SamplingSettings {
    pub temperature: Option<f64>,
    pub top_p: Option<f64>,
    pub top_k: Option<i64>,
    pub min_p: Option<f64>,
    pub frequency_penalty: Option<f64>,
    pub presence_penalty: Option<f64>,
    pub repetition_penalty: Option<f64>,
    pub candidates: Option<u64>,
    pub seed_present: bool,
    pub stop_sequences: u64,
    pub logprobs_requested: bool,
    pub parallel_tool_calls: Option<bool>,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize)]
pub(crate) struct TextShape {
    pub scanned_bytes: u64,
    pub line_breaks: u64,
    pub whitespace_bytes: u64,
    pub digit_bytes: u64,
    pub non_ascii_bytes: u64,
    pub code_fences: u64,
    pub max_line_bytes: u64,
    pub truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct TokenBuckets {
    pub input: &'static str,
    pub uncached_input: &'static str,
    pub output: &'static str,
    pub cache_fraction: &'static str,
    pub output_input_ratio: &'static str,
    pub reasoning_fraction: &'static str,
}

pub(crate) fn token_bucket(tokens: u64) -> &'static str {
    match tokens {
        0 => "0",
        1..=128 => "1_128",
        129..=512 => "129_512",
        513..=2048 => "513_2048",
        2049..=8192 => "2049_8192",
        8193..=32768 => "8193_32768",
        32769..=131072 => "32769_131072",
        131073..=524288 => "131073_524288",
        _ => "524289_plus",
    }
}

fn ratio_bucket(numerator: u64, denominator: u64) -> &'static str {
    if denominator == 0 {
        return "undefined";
    }

    match numerator as f64 / denominator as f64 {
        0.0 => "0",
        v if v <= 0.1 => "0_0.1",
        v if v <= 0.25 => "0.1_0.25",
        v if v <= 0.5 => "0.25_0.5",
        v if v < 1.0 => "0.5_1",
        1.0 => "1",
        v if v <= 4.0 => "1_4",
        _ => "4_plus",
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct RequestTelemetry {
    pub schema_version: u8,
    pub protocol: &'static str,
    pub client: &'static str,
    pub traffic: &'static str,
    pub kind: &'static str,
    pub task_type: &'static str,
    pub task_source: &'static str,
    pub task_scan_bytes: u64,
    pub task_scan_truncated: bool,
    pub language_hint: &'static str,
    pub text_shape: TextShape,
    pub token_buckets: Option<TokenBuckets>,
    pub request_bytes: u64,
    pub messages: u64,
    pub roles: RoleCounts,
    pub text_bytes: RoleCounts,
    pub content_parts: ContentCounts,
    pub max_message_text_bytes: u64,
    pub instruction_text_bytes: u64,
    pub last_role: &'static str,
    pub role_transitions: u64,
    pub last_user_text_bytes: u64,
    pub tool_definitions: u64,
    pub strict_tools: u64,
    pub tool_calls: u64,
    pub tool_results: u64,
    pub tool_argument_text_bytes: u64,
    pub tool_choice: &'static str,
    pub tool_schema: SchemaCounts,
    pub response_format: &'static str,
    pub response_schema: SchemaCounts,
    pub reasoning_effort: &'static str,
    pub thinking_mode: &'static str,
    pub thinking_budget: Option<u64>,
    pub requested_max_output_tokens: Option<u64>,
    pub effective_max_output_tokens: Option<u64>,
    pub output_limit_source: &'static str,
    pub context_limit_tokens: Option<u64>,
    pub sampling: SamplingSettings,
    pub truncated: bool,
}

fn array_len(value: Option<&Value>) -> u64 {
    value
        .and_then(Value::as_array)
        .map_or(0, |items| items.len() as u64)
}

fn setting<'a>(request: &'a Value, name: &str) -> Option<&'a Value> {
    request
        .get(name)
        .or_else(|| request.get("sampling_params")?.get(name))
}

fn number(request: &Value, name: &str, min: f64, max: f64) -> Option<f64> {
    setting(request, name)?
        .as_f64()
        .filter(|v| v.is_finite() && (min..=max).contains(v))
}

fn integer(value: Option<&Value>, max: u64) -> Option<u64> {
    value?.as_u64().filter(|value| *value <= max)
}

fn role(value: Option<&Value>) -> &'static str {
    match value.and_then(Value::as_str) {
        Some("system") => "system",
        Some("developer") => "developer",
        Some("user") => "user",
        Some("assistant") => "assistant",
        Some("tool" | "function") => "tool",
        _ => "other",
    }
}

impl RequestTelemetry {
    pub(crate) fn extract(request: &Value, protocol: Protocol, bytes: usize) -> Self {
        let response_format = request
            .get("response_format")
            .or_else(|| request.pointer("/text/format"));
        let format = match response_format
            .and_then(|v| v.get("type"))
            .and_then(Value::as_str)
        {
            None => "unspecified",
            Some("text") => "text",
            Some("json_object") => "json_object",
            Some("json_schema") => "json_schema",
            Some(_) => "other",
        };
        let choice = request
            .get("tool_choice")
            .or_else(|| request.get("function_call"));
        let tool_choice = match choice {
            None => "unspecified",
            Some(Value::String(v)) => match v.as_str() {
                "auto" => "auto",
                "none" => "none",
                "required" => "required",
                _ => "other",
            },
            Some(v) if v.get("type").and_then(Value::as_str) == Some("any") => "required",
            Some(v) if v.get("type").and_then(Value::as_str) == Some("auto") => "auto",
            Some(v) if v.get("type").and_then(Value::as_str) == Some("none") => "none",
            Some(v) if v.get("function").is_some() || v.get("name").is_some() => "named",
            Some(_) => "other",
        };
        let effort = request
            .get("reasoning_effort")
            .or_else(|| request.pointer("/reasoning/effort"));
        let reasoning_effort = match effort.and_then(Value::as_str) {
            None if effort.is_some_and(Value::is_number) => "numeric",
            None => "unspecified",
            Some("none") => "none",
            Some("minimal") => "minimal",
            Some("low") => "low",
            Some("medium") => "medium",
            Some("high") => "high",
            Some("xhigh") => "xhigh",
            Some("max") => "max",
            Some(_) => "other",
        };
        let mut result = Self {
            schema_version: 1,
            protocol: match protocol {
                Protocol::OpenAiChat => "openai_chat",
                Protocol::OpenAiResponses => "openai_responses",
                Protocol::AnthropicMessages => "anthropic_messages",
            },
            traffic: "routed",
            client: "other",
            kind: "plain_text",
            task_type: "unknown",
            task_source: "unknown",
            task_scan_bytes: 0,
            task_scan_truncated: false,
            language_hint: "unknown",
            text_shape: TextShape::default(),
            token_buckets: None,
            request_bytes: bytes as u64,
            messages: 0,
            roles: RoleCounts::default(),
            text_bytes: RoleCounts::default(),
            content_parts: ContentCounts::default(),
            max_message_text_bytes: 0,
            instruction_text_bytes: 0,
            last_role: "none",
            role_transitions: 0,
            last_user_text_bytes: 0,
            tool_definitions: array_len(request.get("tools").or_else(|| request.get("functions"))),
            strict_tools: 0,
            tool_calls: 0,
            tool_results: 0,
            tool_argument_text_bytes: 0,
            tool_choice,
            tool_schema: SchemaCounts::default(),
            response_format: format,
            response_schema: SchemaCounts::default(),
            reasoning_effort,
            thinking_mode: match request.pointer("/thinking/type").and_then(Value::as_str) {
                Some("enabled") => "enabled",
                Some("disabled") => "disabled",
                Some("adaptive") => "adaptive",
                Some(_) => "other",
                None => match request
                    .pointer("/chat_template_kwargs/enable_thinking")
                    .and_then(Value::as_bool)
                {
                    Some(true) => "enabled",
                    Some(false) => "disabled",
                    None => "unspecified",
                },
            },
            thinking_budget: integer(
                request
                    .pointer("/thinking/budget_tokens")
                    .or_else(|| request.pointer("/reasoning/max_tokens")),
                MAX_SAFE_INTEGER,
            ),
            requested_max_output_tokens: integer(
                request
                    .get("max_completion_tokens")
                    .or_else(|| request.get("max_output_tokens"))
                    .or_else(|| request.get("max_tokens")),
                MAX_SAFE_INTEGER,
            ),
            effective_max_output_tokens: None,
            output_limit_source: "unknown",
            context_limit_tokens: None,
            sampling: SamplingSettings {
                temperature: number(request, "temperature", 0.0, 2.0),
                top_p: number(request, "top_p", 0.0, 1.0),
                top_k: setting(request, "top_k")
                    .and_then(Value::as_i64)
                    .filter(|v| (-1..=1_000_000).contains(v)),
                min_p: number(request, "min_p", 0.0, 1.0),
                frequency_penalty: number(request, "frequency_penalty", -2.0, 2.0),
                presence_penalty: number(request, "presence_penalty", -2.0, 2.0),
                repetition_penalty: number(request, "repetition_penalty", 0.0, 10.0),
                candidates: integer(setting(request, "n"), 128),
                seed_present: setting(request, "seed").is_some_and(|v| !v.is_null()),
                stop_sequences: match request
                    .get("stop")
                    .or_else(|| request.get("stop_sequences"))
                {
                    Some(Value::String(_)) => 1,
                    value => array_len(value),
                },
                logprobs_requested: setting(request, "logprobs").and_then(Value::as_bool)
                    == Some(true)
                    || setting(request, "return_logprob").and_then(Value::as_bool) == Some(true),
                parallel_tool_calls: setting(request, "parallel_tool_calls")
                    .and_then(Value::as_bool),
            },
            truncated: false,
        };
        let mut remaining = MAX_NODES;
        if let Some(instructions) = request
            .get("system")
            .or_else(|| request.get("instructions"))
        {
            result.instruction_text_bytes = result.content(instructions, &mut remaining);
        }
        if let Some(messages) = request
            .get("messages")
            .or_else(|| request.get("input"))
            .and_then(Value::as_array)
        {
            result.messages = messages.len() as u64;
            for message in messages {
                if remaining == 0 {
                    result.truncated = true;
                    break;
                }
                remaining -= 1;
                result.message(message, &mut remaining);
            }
            if let Some(message) = messages
                .iter()
                .rev()
                .take(MAX_NODES as usize)
                .find(|message| message.get("role").and_then(Value::as_str) == Some("user"))
            {
                result.classify_content(message.get("content"));
            }
        } else if let Some(input) = request.get("input").and_then(Value::as_str) {
            result.messages = 1;
            result.roles.user = 1;
            result.last_role = "user";
            result.text_bytes.user = input.len() as u64;
            result.max_message_text_bytes = input.len() as u64;
            result.content_parts.text += 1;
            result.last_user_text_bytes = input.len() as u64;
            result.classify_task(input);
            result.scan_text(input);
        }
        if let Some(tools) = request
            .get("tools")
            .or_else(|| request.get("functions"))
            .and_then(Value::as_array)
        {
            for tool in tools {
                if remaining == 0 {
                    result.truncated = true;
                    break;
                }
                remaining -= 1;
                let function = tool.get("function").unwrap_or(tool);
                result.strict_tools +=
                    u64::from(function.get("strict").and_then(Value::as_bool) == Some(true));
                if let Some(schema) = function
                    .get("parameters")
                    .or_else(|| function.get("input_schema"))
                {
                    result.tool_schema.visit(schema, 0);
                }
            }
        }
        if let Some(schema) = response_format
            .and_then(|v| v.pointer("/json_schema/schema").or_else(|| v.get("schema")))
        {
            result.response_schema.visit(schema, 0);
        }
        result.kind = if result.content_parts.image
            + result.content_parts.audio
            + result.content_parts.video
            + result.content_parts.file
            > 0
        {
            "multimodal"
        } else if matches!(format, "json_object" | "json_schema") {
            "structured_output"
        } else if result.tool_definitions + result.tool_calls + result.tool_results > 0 {
            "tool_context"
        } else {
            "plain_text"
        };

        result
    }

    pub(crate) fn task_hint(&mut self, hint: Option<&str>) {
        if let Some(task) = hint.and_then(task_type) {
            self.task_type = task;
            self.task_source = "caller";
        }
    }

    pub(crate) fn with_usage(mut self, usage: crate::NormalizedUsage) -> Self {
        self.token_buckets = Some(TokenBuckets {
            input: token_bucket(usage.input_tokens()),
            uncached_input: token_bucket(usage.input_tokens() - usage.cached_input_tokens()),
            output: token_bucket(usage.output_tokens()),
            cache_fraction: ratio_bucket(usage.cached_input_tokens(), usage.input_tokens()),
            output_input_ratio: ratio_bucket(usage.output_tokens(), usage.input_tokens()),
            reasoning_fraction: ratio_bucket(usage.reasoning_tokens(), usage.output_tokens()),
        });

        self
    }

    fn classify_task(&mut self, text: &str) {
        self.task_type = "unknown";
        self.task_source = "unknown";
        let prefix = bounded_prefix(text, 8192);
        self.task_scan_bytes = prefix.len() as u64;
        self.task_scan_truncated = prefix.len() < text.len();
        let text = prefix
            .split("```")
            .next()
            .unwrap_or("")
            .to_ascii_lowercase();
        let patterns: &[(&str, &[&str])] = &[
            (
                "code_edit",
                &[
                    "edit the code",
                    "modify the code",
                    "refactor",
                    "apply this patch",
                    "update the function",
                ],
            ),
            (
                "debugging",
                &[
                    "debug",
                    "fix the bug",
                    "fix this error",
                    "stack trace",
                    "traceback",
                ],
            ),
            (
                "code_generation",
                &[
                    "write a function",
                    "write code",
                    "implement",
                    "generate code",
                    "write a script",
                ],
            ),
            (
                "summarization",
                &["summarize", "summarise", "give a summary"],
            ),
            ("translation", &["translate", "translation"]),
            ("extraction", &["extract", "parse into", "convert to json"]),
            (
                "classification",
                &["classify", "categorize", "categorise", "sentiment"],
            ),
            ("reasoning", &["solve", "prove", "calculate", "derive"]),
            (
                "question_answering",
                &["explain", "what is", "what are", "how does", "why does"],
            ),
        ];
        for (task, terms) in patterns {
            if terms.iter().any(|term| text.contains(term)) {
                self.task_type = task;
                self.task_source = "heuristic";
                break;
            }
        }
    }

    fn classify_content(&mut self, content: Option<&Value>) {
        if let Some(text) = content.and_then(Value::as_str) {
            self.classify_task(text);
        } else if let Some(parts) = content.and_then(Value::as_array) {
            for part in parts.iter().take(MAX_NODES as usize) {
                if matches!(
                    part.get("type").and_then(Value::as_str),
                    Some("text" | "input_text")
                ) {
                    if let Some(text) = part.get("text").and_then(Value::as_str) {
                        self.classify_task(text);
                        break;
                    }
                }
            }
        }
    }

    fn scan_text(&mut self, text: &str) {
        let remaining = 65_536_usize.saturating_sub(self.text_shape.scanned_bytes as usize);
        let prefix = bounded_prefix(text, remaining);
        let shape = &mut self.text_shape;
        shape.scanned_bytes += prefix.len() as u64;
        shape.truncated |= prefix.len() < text.len();
        shape.line_breaks += prefix.bytes().filter(|b| *b == b'\n').count() as u64;
        shape.whitespace_bytes += prefix.bytes().filter(u8::is_ascii_whitespace).count() as u64;
        shape.digit_bytes += prefix.bytes().filter(u8::is_ascii_digit).count() as u64;
        shape.non_ascii_bytes += prefix.bytes().filter(|b| !b.is_ascii()).count() as u64;
        shape.code_fences += prefix.matches("```").count() as u64;
        shape.max_line_bytes = shape
            .max_line_bytes
            .max(prefix.split('\n').map(str::len).max().unwrap_or(0) as u64);
        if self.language_hint == "unknown" {
            for fence in prefix.split("```").skip(1).step_by(2) {
                let tag = fence.split(['\r', '\n', ' ', '\t']).next().unwrap_or("");
                self.language_hint = match tag {
                    "python" | "py" => "python",
                    "typescript" | "ts" | "tsx" => "typescript",
                    "javascript" | "js" | "jsx" => "javascript",
                    "rust" | "rs" => "rust",
                    "go" | "golang" => "go",
                    "java" => "java",
                    "sql" => "sql",
                    "bash" | "sh" | "shell" => "shell",
                    "c" | "cpp" | "c++" => "c_cpp",
                    "json" => "json",
                    "html" | "css" => "html_css",
                    _ => "unknown",
                };
                if self.language_hint != "unknown" {
                    break;
                }
            }
        }
    }

    fn message(&mut self, message: &Value, remaining: &mut u64) {
        let item_type = message.get("type").and_then(Value::as_str);
        let role = match item_type {
            Some("function_call") => "assistant",
            Some("function_call_output") => "tool",
            _ => role(message.get("role")),
        };
        self.roles.add(role, 1);
        self.role_transitions += u64::from(self.last_role != "none" && self.last_role != role);
        self.last_role = role;
        self.tool_results += u64::from(role == "tool");
        let content = message.get("content").or_else(|| message.get("output"));
        let bytes = content.map_or(0, |content| self.content(content, remaining));
        self.text_bytes.add(role, bytes);
        self.max_message_text_bytes = self.max_message_text_bytes.max(bytes);
        if role == "user" {
            self.last_user_text_bytes = bytes;
        }
        if let Some(calls) = message.get("tool_calls").and_then(Value::as_array) {
            self.tool_calls += calls.len() as u64;
            let limit = *remaining as usize;
            for call in calls.iter().take(limit) {
                *remaining -= 1;
                self.argument(call.get("function").unwrap_or(call));
            }
            if calls.len() > limit {
                self.truncated = true;
            }
        }
        if let Some(call) = message.get("function_call") {
            self.tool_calls += 1;
            self.argument(call);
        }
        if item_type == Some("function_call") {
            self.tool_calls += 1;
            self.argument(message);
        }
    }

    fn argument(&mut self, call: &Value) {
        self.tool_argument_text_bytes += call
            .get("arguments")
            .and_then(Value::as_str)
            .map_or(0, |v| v.len() as u64);
    }

    fn content(&mut self, content: &Value, remaining: &mut u64) -> u64 {
        if let Some(text) = content.as_str() {
            self.content_parts.text += 1;
            self.scan_text(text);
            return text.len() as u64;
        }

        let Some(parts) = content.as_array() else {
            return 0;
        };
        let mut bytes = 0;
        for part in parts {
            if *remaining == 0 {
                self.truncated = true;
                break;
            }
            *remaining -= 1;
            match part.get("type").and_then(Value::as_str) {
                Some("text" | "input_text" | "output_text") => {
                    self.content_parts.text += 1;
                    bytes += part
                        .get("text")
                        .and_then(Value::as_str)
                        .map_or(0, |v| v.len() as u64);
                    if let Some(text) = part.get("text").and_then(Value::as_str) {
                        self.scan_text(text);
                    }
                }
                Some("image" | "image_url" | "input_image") => self.content_parts.image += 1,
                Some("audio" | "input_audio" | "output_audio") => self.content_parts.audio += 1,
                Some("video" | "video_url" | "input_video") => self.content_parts.video += 1,
                Some("file" | "document" | "input_file") => self.content_parts.file += 1,
                Some("tool_use") => self.tool_calls += 1,
                Some("tool_result") => self.tool_results += 1,
                _ => self.content_parts.other += 1,
            }
        }

        bytes
    }
}

fn bounded_prefix(text: &str, max: usize) -> &str {
    let mut end = text.len().min(max);
    while !text.is_char_boundary(end) {
        end -= 1;
    }

    &text[..end]
}

fn task_type(value: &str) -> Option<&'static str> {
    match value {
        "code_edit" => Some("code_edit"),
        "code_generation" => Some("code_generation"),
        "debugging" => Some("debugging"),
        "summarization" => Some("summarization"),
        "translation" => Some("translation"),
        "extraction" => Some("extraction"),
        "classification" => Some("classification"),
        "reasoning" => Some("reasoning"),
        "question_answering" => Some("question_answering"),
        "creative_writing" => Some("creative_writing"),
        "other" => Some("other"),
        _ => None,
    }
}

#[cfg(test)]
mod tests;
