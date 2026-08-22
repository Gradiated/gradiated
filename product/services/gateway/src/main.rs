use std::{future::IntoFuture, sync::Arc, time::Duration};

use gradiated_gateway::{
    router, CompletionService, DependencyReadiness, GatewayConfig, GatewayState, ModelTokenizer,
    RequestCoordinator, SglangClient, ValkeyServingState,
};
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

const NATURAL_DRAIN_BUFFER: Duration = Duration::from_secs(5);
const FORCED_DRAIN_TIMEOUT: Duration = Duration::from_secs(15);
const HTTP_DRAIN_TIMEOUT: Duration = Duration::from_secs(5);

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .expect("AWS-LC must be the gateway's only installed Rustls crypto provider");

    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let config = GatewayConfig::from_environment()?;
    let natural_drain_timeout =
        Duration::from_secs(config.generation_timeout_seconds).saturating_add(NATURAL_DRAIN_BUFFER);
    let serving_state = Arc::new(match config.valkey_iam() {
        Some(iam) => ValkeyServingState::connect_with_iam(&config.valkey_url, iam).await?,
        None => ValkeyServingState::connect(&config.valkey_url).await?,
    });
    let tokenizer = ModelTokenizer::new()?;
    let runtimes = SglangClient::with_tokenizer(config.sglang_api_key.clone(), tokenizer.clone())?;
    let completions = CompletionService::new(
        serving_state.clone(),
        Arc::new(runtimes.clone()),
        tokenizer,
        Arc::new(config.clone()),
    );
    let readiness = Arc::new(DependencyReadiness::new(
        (*serving_state).clone(),
        runtimes,
        completions.metrics(),
    ));
    let listener = tokio::net::TcpListener::bind(config.bind_address).await?;

    info!(
        bind_address = %config.bind_address,
        generation_timeout_seconds = config.generation_timeout_seconds,
        "gateway listening"
    );
    let (stop_server, server_stopped) = tokio::sync::oneshot::channel();
    let server = axum::serve(
        listener,
        router(GatewayState::new(
            readiness,
            completions.clone(),
            RequestCoordinator::new(serving_state),
        )),
    )
    .with_graceful_shutdown(async {
        let _ = server_stopped.await;
    })
    .into_future();
    tokio::pin!(server);
    tokio::select! {
        result = &mut server => result?,
        () = shutdown_signal() => {
            completions.begin_draining();
            let _ = stop_server.send(());

            if tokio::time::timeout(natural_drain_timeout, completions.wait_for_drain())
                .await
                .is_err()
            {
                warn!(
                    timeout_seconds = natural_drain_timeout.as_secs(),
                    "gateway natural drain timed out; cancelling remaining generations"
                );
                completions.force_shutdown();
                if tokio::time::timeout(FORCED_DRAIN_TIMEOUT, completions.wait_for_drain())
                    .await
                    .is_err()
                {
                    warn!(
                        timeout_seconds = FORCED_DRAIN_TIMEOUT.as_secs(),
                        "gateway forced drain timed out"
                    );
                }
            }

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
