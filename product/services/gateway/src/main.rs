use std::{error::Error, future::IntoFuture, process::ExitCode, sync::Arc, time::Duration};

use axum::http::HeaderValue;
use gradiated_gateway::{
    browser_cors, router, CompletionService, DependencyReadiness, GatewayConfig, GatewayState,
    ModelTokenizer, PostgresReader, ProviderRelay, RequestCoordinator, RuntimeTlsConfig,
    SglangClient, ValkeyServingState,
};
use tokio::signal::unix::{signal, Signal, SignalKind};
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;

const NATURAL_DRAIN_BUFFER: Duration = Duration::from_secs(5);
const FORCED_DRAIN_TIMEOUT: Duration = Duration::from_secs(15);
const HTTP_DRAIN_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone, Copy)]
enum Stage {
    Crypto,
    Config,
    Signals,
    Postgres,
    Valkey,
    Tokenizer,
    Runtime,
    Application,
    Bind,
    Serve,
}

impl Stage {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Crypto => "crypto",
            Self::Config => "config",
            Self::Signals => "signals",
            Self::Postgres => "postgres",
            Self::Valkey => "valkey",
            Self::Tokenizer => "tokenizer",
            Self::Runtime => "runtime",
            Self::Application => "application",
            Self::Bind => "bind",
            Self::Serve => "serve",
        }
    }
}

struct Failure {
    stage: Stage,
    error: Box<dyn Error>,
}

fn at<E: Into<Box<dyn Error>>>(stage: Stage) -> impl FnOnce(E) -> Failure {
    move |error| Failure {
        stage,
        error: error.into(),
    }
}

#[tokio::main]
async fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(Failure { stage, error }) => {
            error!(error_code = stage.as_str(), %error, "gateway failed");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Failure> {
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .map_err(|_| "a Rustls crypto provider other than AWS-LC is already installed")
        .map_err(at(Stage::Crypto))?;

    let config = GatewayConfig::from_environment().map_err(at(Stage::Config))?;
    let interrupt = signal(SignalKind::interrupt()).map_err(at(Stage::Signals))?;
    let terminate = signal(SignalKind::terminate()).map_err(at(Stage::Signals))?;

    let serving_state = Arc::new(connect_serving_state(&config).await?);

    let tokenizer = ModelTokenizer::new().map_err(at(Stage::Tokenizer))?;
    let tls = RuntimeTlsConfig::from_environment().map_err(at(Stage::Runtime))?;
    let runtimes = SglangClient::with_tokenizer_and_tls(
        config.sglang_api_key.clone(),
        tokenizer.clone(),
        tls.as_ref(),
    )
    .map_err(at(Stage::Runtime))?;
    let completions = CompletionService::new(
        serving_state.clone(),
        Arc::new(runtimes),
        tokenizer,
        Arc::new(config.clone()),
    );

    let app =
        application(&config, serving_state, completions.clone()).map_err(at(Stage::Application))?;
    let listener = tokio::net::TcpListener::bind(config.bind_address)
        .await
        .map_err(at(Stage::Bind))?;
    info!(
        bind_address = %config.bind_address,
        generation_timeout_seconds = config.generation_timeout_seconds,
        "gateway listening"
    );

    // The server runs as its own task so it stops accepting connections while
    // generations drain, not only after they finish.
    let (stop_server, server_stopped) = tokio::sync::oneshot::channel();
    let mut server = tokio::spawn(
        axum::serve(listener, app)
            .with_graceful_shutdown(async {
                let _ = server_stopped.await;
            })
            .into_future(),
    );

    tokio::select! {
        result = &mut server => result.map_err(at(Stage::Serve))?.map_err(at(Stage::Serve))?,
        () = shutdown_signal(interrupt, terminate) => {
            // New work stops first; generations in flight then finish and settle
            // before the HTTP server lets their connections go.
            completions.begin_draining();
            let _ = stop_server.send(());

            let natural_drain_timeout = Duration::from_secs(config.generation_timeout_seconds)
                .saturating_add(NATURAL_DRAIN_BUFFER);
            drain_generations(&completions, natural_drain_timeout).await;

            match tokio::time::timeout(HTTP_DRAIN_TIMEOUT, &mut server).await {
                Ok(result) => result.map_err(at(Stage::Serve))?.map_err(at(Stage::Serve))?,
                Err(_) => warn!(
                    timeout_seconds = HTTP_DRAIN_TIMEOUT.as_secs(),
                    "gateway HTTP drain timed out"
                ),
            }
        }
    }

    Ok(())
}

async fn connect_serving_state(config: &GatewayConfig) -> Result<ValkeyServingState, Failure> {
    let database = PostgresReader::connect(
        &config.database_url,
        config.database_ca_bundle_path.as_deref(),
    )
    .map_err(at(Stage::Postgres))?;
    database.ping().await.map_err(at(Stage::Postgres))?;

    let record_cache_ttl = config.record_cache_ttl();
    let serving_state = match config.valkey_iam() {
        Some(iam) => {
            ValkeyServingState::connect_with_iam(
                &config.valkey_url,
                iam,
                database,
                record_cache_ttl,
            )
            .await
        }
        None => ValkeyServingState::connect(&config.valkey_url, database, record_cache_ttl).await,
    };

    serving_state.map_err(at(Stage::Valkey))
}

fn application(
    config: &GatewayConfig,
    serving_state: Arc<ValkeyServingState>,
    completions: CompletionService,
) -> Result<axum::Router, Box<dyn Error>> {
    let readiness = Arc::new(DependencyReadiness::new(
        (*serving_state).clone(),
        completions.metrics(),
    ));
    let relay = ProviderRelay::new(&config.proxy_anthropic_origin, config.proxy_limits())?;
    let app = router(GatewayState::new(
        readiness,
        completions,
        RequestCoordinator::new(serving_state),
        relay,
        config.compliance(),
    ));

    let browser_origins = config
        .browser_origins()
        .into_iter()
        .map(str::parse::<HeaderValue>)
        .collect::<Result<Vec<_>, _>>()?;
    if browser_origins.is_empty() {
        return Ok(app);
    }

    Ok(app.layer(browser_cors(browser_origins)))
}

async fn drain_generations(completions: &CompletionService, natural_drain_timeout: Duration) {
    let drained = tokio::time::timeout(natural_drain_timeout, completions.wait_for_drain()).await;
    if drained.is_ok() {
        return;
    }

    warn!(
        timeout_seconds = natural_drain_timeout.as_secs(),
        "gateway natural drain timed out; cancelling remaining generations"
    );
    completions.force_shutdown();

    let drained = tokio::time::timeout(FORCED_DRAIN_TIMEOUT, completions.wait_for_drain()).await;
    if drained.is_err() {
        warn!(
            timeout_seconds = FORCED_DRAIN_TIMEOUT.as_secs(),
            "gateway forced drain timed out"
        );
    }
}

async fn shutdown_signal(mut interrupt: Signal, mut terminate: Signal) {
    tokio::select! {
        _ = interrupt.recv() => {},
        _ = terminate.recv() => {},
    }
}
