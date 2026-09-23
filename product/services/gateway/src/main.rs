use std::{future::IntoFuture, sync::Arc, time::Duration};

use axum::http::HeaderValue;
use gradiated_gateway::{
    browser_cors, router, CompletionService, DependencyReadiness, GatewayConfig, GatewayState,
    ModelTokenizer, PostgresReader, ProviderRelay, RequestCoordinator, RuntimeTlsConfig,
    SglangClient, ValkeyServingState,
};
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

const NATURAL_DRAIN_BUFFER: Duration = Duration::from_secs(5);
const FORCED_DRAIN_TIMEOUT: Duration = Duration::from_secs(15);
const HTTP_DRAIN_TIMEOUT: Duration = Duration::from_secs(5);

type StartupError = Box<dyn std::error::Error>;

#[tokio::main]
async fn main() -> Result<(), StartupError> {
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .expect("AWS-LC must be the gateway's only installed Rustls crypto provider");

    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let config = GatewayConfig::from_environment()?;
    let serving_state = Arc::new(connect_serving_state(&config).await?);

    let tokenizer = ModelTokenizer::new()?;
    let runtimes = SglangClient::with_tokenizer_and_tls(
        config.sglang_api_key.clone(),
        tokenizer.clone(),
        RuntimeTlsConfig::from_environment()?.as_ref(),
    )?;
    let completions = CompletionService::new(
        serving_state.clone(),
        Arc::new(runtimes),
        tokenizer,
        Arc::new(config.clone()),
    );

    let app = application(&config, serving_state, completions.clone())?;
    let listener = tokio::net::TcpListener::bind(config.bind_address).await?;
    info!(
        bind_address = %config.bind_address,
        generation_timeout_seconds = config.generation_timeout_seconds,
        "gateway listening"
    );

    let (stop_server, server_stopped) = tokio::sync::oneshot::channel();
    let server = axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = server_stopped.await;
        })
        .into_future();
    tokio::pin!(server);

    tokio::select! {
        result = &mut server => result?,
        () = shutdown_signal() => {
            // New work stops first; generations in flight then finish and settle
            // before the HTTP server lets their connections go.
            completions.begin_draining();
            let _ = stop_server.send(());

            let natural_drain_timeout = Duration::from_secs(config.generation_timeout_seconds)
                .saturating_add(NATURAL_DRAIN_BUFFER);
            drain_generations(&completions, natural_drain_timeout).await;

            match tokio::time::timeout(HTTP_DRAIN_TIMEOUT, &mut server).await {
                Ok(result) => result?,
                Err(_) => warn!(
                    timeout_seconds = HTTP_DRAIN_TIMEOUT.as_secs(),
                    "gateway HTTP drain timed out"
                ),
            }
        }
    }

    Ok(())
}

async fn connect_serving_state(config: &GatewayConfig) -> Result<ValkeyServingState, StartupError> {
    let database = PostgresReader::connect(
        &config.database_url,
        config.database_ca_bundle_path.as_deref(),
    )?;
    database.ping().await?;

    let record_cache_ttl = config.record_cache_ttl();
    let serving_state = match config.valkey_iam() {
        Some(iam) => {
            ValkeyServingState::connect_with_iam(
                &config.valkey_url,
                iam,
                database,
                record_cache_ttl,
            )
            .await?
        }
        None => ValkeyServingState::connect(&config.valkey_url, database, record_cache_ttl).await?,
    };

    Ok(serving_state)
}

fn application(
    config: &GatewayConfig,
    serving_state: Arc<ValkeyServingState>,
    completions: CompletionService,
) -> Result<axum::Router, StartupError> {
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

/// Waits for generations to finish on their own, then cancels what remains and
/// waits a bounded time more for those to settle.
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

async fn shutdown_signal() {
    let interrupt = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = interrupt => {},
        () = terminate => {},
    }
}
