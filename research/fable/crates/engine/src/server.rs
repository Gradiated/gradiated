//! OpenAI-compatible HTTP layer. The engine runs on a dedicated OS thread
//! (it owns the Metal device); handlers submit Requests over a std mpsc
//! channel and read tokens back on per-request tokio channels. Detokenization
//! and stop-string matching happen here, never in the engine loop.
use crate::config::EngineConfig;
use crate::detok::{ChatTemplate, IncrementalDecoder};
use crate::engine::{Engine, Request};
use crate::model::Model;
use crate::sample::SamplingParams;
use crate::sched::{FinishReason, Out};
use anyhow::{Context, Result};
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::sse::{Event, Sse};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::Arc;
use tokenizers::Tokenizer;
use tokio::sync::mpsc::{unbounded_channel, UnboundedReceiver, UnboundedSender};
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::StreamExt;

pub struct ServeArgs {
    pub model: PathBuf,
    pub device: String,
    pub dtype: String,
    pub port: u16,
    pub max_slots: usize,
    pub max_ctx: usize,
    pub prefill_chunk: usize,
}

#[derive(Clone)]
struct AppState {
    tx: std::sync::mpsc::Sender<Request>,
    tokenizer: Arc<Tokenizer>,
    template: ChatTemplate,
    model_id: Arc<String>,
    eos: Arc<Vec<u32>>,
    max_ctx: usize,
    created: u64,
}

pub fn serve(args: ServeArgs) -> Result<()> {
    let dev = crate::parse_device(&args.device)?;
    let dt = crate::parse_dtype(&args.dtype)?;
    let ecfg = EngineConfig {
        max_slots: args.max_slots,
        max_ctx: args.max_ctx,
        prefill_chunk: args.prefill_chunk,
        dtype: dt,
        device: dev.clone(),
    };
    let model = Model::load(&args.model, dt, &dev, args.max_ctx).context("loading model")?;
    let tokenizer = Tokenizer::from_file(args.model.join("tokenizer.json"))
        .map_err(|e| anyhow::anyhow!("tokenizer: {e}"))?;
    let template = ChatTemplate::detect(&args.model);
    let model_id = args
        .model
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "model".into());
    let eos = model.cfg.eos_token_id.clone();
    eprintln!(
        "loaded {model_id} ({} layers); kv budget {:.1} MB; template {template:?}",
        model.cfg.num_hidden_layers,
        ecfg.kv_bytes(&model.cfg) as f64 / 1e6
    );

    let mut engine = Engine::new(model, &ecfg)?;
    let (tx, rx) = std::sync::mpsc::channel::<Request>();
    std::thread::Builder::new()
        .name("engine".into())
        .spawn(move || {
            if let Err(e) = engine.run(rx) {
                eprintln!("engine loop failed: {e:#}");
            }
        })?;

    // Warmup: absorb Metal pipeline compilation before accepting traffic.
    {
        let (otx, mut orx) = unbounded_channel();
        tx.send(Request {
            prompt: vec![1, 2, 3, 4],
            params: SamplingParams {
                temperature: 0.0,
                max_tokens: 4,
                ignore_eos: true,
                ..Default::default()
            },
            tx: otx,
        })?;
        while let Some(o) = orx.blocking_recv() {
            if matches!(o, Out::Done { .. }) {
                break;
            }
        }
    }

    let state = AppState {
        tx,
        tokenizer: Arc::new(tokenizer),
        template,
        model_id: Arc::new(model_id),
        eos: Arc::new(eos),
        max_ctx: args.max_ctx,
        created: unix_now(),
    };
    let app = Router::new()
        .route("/v1/completions", post(completions))
        .route("/v1/chat/completions", post(chat_completions))
        .route("/v1/models", get(models))
        .route("/health", get(health))
        .with_state(state);

    let rt = tokio::runtime::Runtime::new()?;
    rt.block_on(async {
        let listener = tokio::net::TcpListener::bind(("0.0.0.0", args.port)).await?;
        eprintln!("barge serving on http://0.0.0.0:{}", args.port);
        axum::serve(listener, app).await?;
        anyhow::Ok(())
    })
}

#[derive(Clone, Copy)]
enum Api {
    Chat,
    Text,
}

#[derive(Deserialize)]
struct GenParams {
    max_tokens: Option<usize>,
    temperature: Option<f32>,
    top_p: Option<f32>,
    top_k: Option<usize>,
    seed: Option<u64>,
    stop: Option<StopSpec>,
    #[serde(default)]
    stream: bool,
    n: Option<u32>,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum StopSpec {
    One(String),
    Many(Vec<String>),
}

impl StopSpec {
    fn into_vec(self) -> Vec<String> {
        match self {
            StopSpec::One(s) => vec![s],
            StopSpec::Many(v) => v,
        }
    }
}

#[derive(Deserialize)]
struct CompletionRequest {
    prompt: String,
    #[serde(flatten)]
    params: GenParams,
}

#[derive(Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Deserialize)]
struct ChatRequest {
    messages: Vec<ChatMessage>,
    #[serde(flatten)]
    params: GenParams,
}

async fn completions(State(st): State<AppState>, Json(req): Json<CompletionRequest>) -> Response {
    respond(st, req.prompt, req.params, Api::Text).await
}

async fn chat_completions(State(st): State<AppState>, Json(req): Json<ChatRequest>) -> Response {
    if req.messages.is_empty() {
        return error_response(StatusCode::BAD_REQUEST, "messages must not be empty");
    }
    let msgs: Vec<(String, String)> = req.messages.into_iter().map(|m| (m.role, m.content)).collect();
    let text = st.template.render(&msgs);
    respond(st, text, req.params, Api::Chat).await
}

async fn models(State(st): State<AppState>) -> Json<Value> {
    Json(json!({
        "object": "list",
        "data": [{"id": st.model_id.as_str(), "object": "model", "created": st.created, "owned_by": "barge"}],
    }))
}

async fn health() -> Json<Value> {
    Json(json!({"status": "ok"}))
}

async fn respond(st: AppState, prompt_text: String, p: GenParams, api: Api) -> Response {
    let stream = p.stream;
    let (rx, ts, prompt_tokens) = match admit(&st, prompt_text, p, api) {
        Ok(x) => x,
        Err(resp) => return resp,
    };
    let prefix = match api {
        Api::Chat => "chatcmpl",
        Api::Text => "cmpl",
    };
    let id = format!("{prefix}-{:016x}", rand::random::<u64>());
    let created = unix_now();

    if stream {
        let (etx, erx) = unbounded_channel::<Event>();
        let ctx = SseCtx {
            api,
            id,
            model: st.model_id.clone(),
            created,
            etx,
        };
        tokio::spawn(pump_sse(rx, ts, ctx));
        Sse::new(UnboundedReceiverStream::new(erx).map(Ok::<_, std::convert::Infallible>))
            .into_response()
    } else {
        let (text, finish, completion_tokens) = run_to_end(rx, ts).await;
        let usage = json!({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        });
        let body = match api {
            Api::Chat => json!({
                "id": id, "object": "chat.completion", "created": created, "model": st.model_id.as_str(),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
                "usage": usage,
            }),
            Api::Text => json!({
                "id": id, "object": "text_completion", "created": created, "model": st.model_id.as_str(),
                "choices": [{"index": 0, "text": text, "logprobs": null, "finish_reason": finish}],
                "usage": usage,
            }),
        };
        Json(body).into_response()
    }
}

/// Validate, tokenize, budget-check, and submit to the engine.
fn admit(
    st: &AppState,
    text: String,
    p: GenParams,
    api: Api,
) -> Result<(UnboundedReceiver<Out>, TextStream, usize), Response> {
    let bad = |msg: String| error_response(StatusCode::BAD_REQUEST, &msg);
    if p.n.unwrap_or(1) > 1 {
        return Err(bad("n > 1 is not supported; send concurrent requests instead".into()));
    }
    let ids = st
        .tokenizer
        .encode(text, false)
        .map_err(|e| bad(format!("tokenization failed: {e}")))?
        .get_ids()
        .to_vec();
    let prompt_tokens = ids.len();
    let max_tokens = p.max_tokens.unwrap_or(match api {
        Api::Chat => st.max_ctx.saturating_sub(prompt_tokens),
        Api::Text => 16,
    });
    if max_tokens == 0 || prompt_tokens + max_tokens > st.max_ctx {
        return Err(bad(format!(
            "prompt ({prompt_tokens} tokens) plus max_tokens ({max_tokens}) exceeds the \
             per-request context budget ({} tokens); shorten the prompt or lower max_tokens",
            st.max_ctx
        )));
    }
    let stops = p.stop.map(StopSpec::into_vec).unwrap_or_default();
    let params = SamplingParams {
        temperature: p.temperature.unwrap_or(1.0),
        top_p: p.top_p.unwrap_or(1.0),
        top_k: p.top_k.unwrap_or(0),
        max_tokens,
        seed: p.seed.unwrap_or_else(rand::random),
        ignore_eos: false,
        stop: stops.clone(),
    };
    let (otx, orx) = unbounded_channel();
    st.tx
        .send(Request {
            prompt: ids,
            params,
            tx: otx,
        })
        .map_err(|_| error_response(StatusCode::INTERNAL_SERVER_ERROR, "engine unavailable"))?;
    let ts = TextStream::new(st.tokenizer.clone(), st.eos.clone(), stops);
    Ok((orx, ts, prompt_tokens))
}

/// Turns the engine's token stream into emit-ready text: skips EOS ids,
/// detokenizes incrementally, and applies server-side stop strings.
struct TextStream {
    dec: IncrementalDecoder,
    scan: StopScan,
    tokenizer: Arc<Tokenizer>,
    eos: Arc<Vec<u32>>,
    completion_tokens: usize,
}

enum Step {
    Text(String),
    Finish { text: String, reason: &'static str },
}

impl TextStream {
    fn new(tokenizer: Arc<Tokenizer>, eos: Arc<Vec<u32>>, stops: Vec<String>) -> Self {
        Self {
            dec: IncrementalDecoder::new(),
            scan: StopScan::new(stops),
            tokenizer,
            eos,
            completion_tokens: 0,
        }
    }

    fn on(&mut self, out: Out) -> Option<Step> {
        match out {
            Out::Token(t) => {
                self.completion_tokens += 1;
                if self.eos.contains(&t) {
                    return None;
                }
                let piece = self.dec.push(t, &self.tokenizer)?;
                let (text, hit) = self.scan.push(&piece);
                if hit {
                    Some(Step::Finish { text, reason: "stop" })
                } else if text.is_empty() {
                    None
                } else {
                    Some(Step::Text(text))
                }
            }
            Out::Done { finish } => Some(Step::Finish {
                text: self.scan.flush(),
                reason: match finish {
                    FinishReason::Stop => "stop",
                    FinishReason::Length => "length",
                },
            }),
        }
    }
}

/// Stop-string matcher over streamed text. Holds back a tail shorter than the
/// longest stop string so a match spanning chunk boundaries is still caught.
struct StopScan {
    stops: Vec<String>,
    hold: usize,
    pending: String,
}

impl StopScan {
    fn new(stops: Vec<String>) -> Self {
        let hold = stops.iter().map(|s| s.len()).max().unwrap_or(0).saturating_sub(1);
        Self {
            stops,
            hold,
            pending: String::new(),
        }
    }

    /// Returns text safe to emit and whether a stop string was hit (the text
    /// is already cut at the earliest match).
    fn push(&mut self, piece: &str) -> (String, bool) {
        if self.stops.is_empty() {
            return (piece.to_string(), false);
        }
        self.pending.push_str(piece);
        if let Some(i) = self.stops.iter().filter_map(|s| self.pending.find(s.as_str())).min() {
            self.pending.truncate(i);
            return (std::mem::take(&mut self.pending), true);
        }
        let mut cut = self.pending.len().saturating_sub(self.hold);
        while !self.pending.is_char_boundary(cut) {
            cut -= 1;
        }
        let out = self.pending[..cut].to_string();
        self.pending.drain(..cut);
        (out, false)
    }

    fn flush(&mut self) -> String {
        std::mem::take(&mut self.pending)
    }
}

async fn run_to_end(
    mut rx: UnboundedReceiver<Out>,
    mut ts: TextStream,
) -> (String, &'static str, usize) {
    let mut text = String::new();
    while let Some(out) = rx.recv().await {
        match ts.on(out) {
            Some(Step::Text(s)) => text.push_str(&s),
            Some(Step::Finish { text: tail, reason }) => {
                text.push_str(&tail);
                return (text, reason, ts.completion_tokens);
            }
            None => {}
        }
    }
    (text, "length", ts.completion_tokens)
}

struct SseCtx {
    api: Api,
    id: String,
    model: Arc<String>,
    created: u64,
    etx: UnboundedSender<Event>,
}

impl SseCtx {
    fn emit(&self, delta_text: Option<&str>, finish: Option<&str>) {
        let choice = match self.api {
            Api::Chat => {
                let delta = match delta_text {
                    Some(t) => json!({"content": t}),
                    None => json!({}),
                };
                json!({"index": 0, "delta": delta, "finish_reason": finish})
            }
            Api::Text => json!({"index": 0, "text": delta_text.unwrap_or(""), "finish_reason": finish}),
        };
        let chunk = json!({
            "id": self.id,
            "object": match self.api { Api::Chat => "chat.completion.chunk", Api::Text => "text_completion" },
            "created": self.created,
            "model": self.model.as_str(),
            "choices": [choice],
        });
        let _ = self.etx.send(Event::default().data(chunk.to_string()));
    }
}

async fn pump_sse(mut rx: UnboundedReceiver<Out>, mut ts: TextStream, ctx: SseCtx) {
    if let Api::Chat = ctx.api {
        let role = json!({
            "id": ctx.id, "object": "chat.completion.chunk", "created": ctx.created, "model": ctx.model.as_str(),
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": null}],
        });
        let _ = ctx.etx.send(Event::default().data(role.to_string()));
    }
    let mut finish = "length";
    while let Some(out) = rx.recv().await {
        match ts.on(out) {
            Some(Step::Text(s)) => ctx.emit(Some(&s), None),
            Some(Step::Finish { text, reason }) => {
                if !text.is_empty() {
                    ctx.emit(Some(&text), None);
                }
                finish = reason;
                break;
            }
            None => {}
        }
    }
    ctx.emit(None, Some(finish));
    let _ = ctx.etx.send(Event::default().data("[DONE]"));
    // TODO: the engine has no cancel; on a server-side stop match we drop the
    // receiver here and the engine keeps decoding the sequence to its budget,
    // discarding tokens.
}

fn error_response(status: StatusCode, msg: &str) -> Response {
    (
        status,
        Json(json!({"error": {"message": msg, "type": "invalid_request_error"}})),
    )
        .into_response()
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs()
}
