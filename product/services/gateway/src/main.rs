use std::sync::Arc;

use gradiated_gateway::{
    router, DependencyReadiness, GatewayConfig, GatewayState, SglangHealthClient,
    ValkeyServingState,
};
use tracing::info;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let config = GatewayConfig::from_environment()?;
    let serving_state = ValkeyServingState::connect(&config.valkey_url).await?;
    let runtimes = SglangHealthClient::new(config.sglang_api_key)?;
    let readiness = Arc::new(DependencyReadiness::new(serving_state, runtimes));
    let listener = tokio::net::TcpListener::bind(config.bind_address).await?;

    info!(
        bind_address = %config.bind_address,
        generation_timeout_seconds = config.generation_timeout_seconds,
        "gateway listening"
    );
    axum::serve(listener, router(GatewayState::new(readiness)))
        .with_graceful_shutdown(shutdown_signal())
        .await?;
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
