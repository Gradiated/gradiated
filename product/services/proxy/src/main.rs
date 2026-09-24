use std::{
    error::Error,
    future::IntoFuture,
    process::ExitCode,
    sync::{atomic::AtomicBool, atomic::Ordering, Arc},
    time::Duration,
};

use gradiated_proxy::{
    admin_router, public_router, AppState, HostedCatalog, IdentityCache, Metrics, Origins,
    PostgresDirectory, ProxyConfig, Upstreams,
};
use tokio::{
    net::TcpListener,
    signal::unix::{signal, SignalKind},
};
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;

const DRAIN_BUFFER: Duration = Duration::from_secs(5);

#[tokio::main]
async fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            error!(%error, "proxy failed");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Box<dyn Error>> {
    rustls::crypto::aws_lc_rs::default_provider()
        .install_default()
        .map_err(|_| "a Rustls crypto provider other than AWS-LC is already installed")?;

    let config = ProxyConfig::from_environment()?;
    let mut interrupt = signal(SignalKind::interrupt())?;
    let mut terminate = signal(SignalKind::terminate())?;

    let metrics = Metrics::default();
    let directory = Arc::new(PostgresDirectory::connect(
        &config.database_url,
        config.database_ca_bundle_path.as_deref(),
    )?);

    let catalog = HostedCatalog::new(directory.clone(), metrics.clone());
    tokio::spawn(catalog.clone().run(config.catalog_refresh));

    let state = AppState {
        catalog,
        identity: IdentityCache::new(directory, config.identity, metrics.clone()),
        upstreams: Upstreams::new(
            Origins {
                gateway: &config.gateway_origin,
                anthropic: &config.anthropic_origin,
                openai: &config.openai_origin,
            },
            config.limits,
            metrics.clone(),
        )?,
        metrics,
        relay_enabled: config.relay_enabled,
        draining: Arc::new(AtomicBool::new(false)),
    };

    let public = TcpListener::bind(config.bind_address).await?;
    let admin = TcpListener::bind(config.admin_address).await?;
    info!(
        bind_address = %config.bind_address,
        admin_address = %config.admin_address,
        relay_enabled = config.relay_enabled,
        "proxy listening"
    );

    tokio::spawn(axum::serve(admin, admin_router(state.clone())).into_future());

    let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
    let mut server = tokio::spawn(
        axum::serve(public, public_router(state.clone()))
            .with_graceful_shutdown(async {
                let _ = stopped.await;
            })
            .into_future(),
    );

    tokio::select! {
        result = &mut server => return Ok(result??),
        _ = interrupt.recv() => {},
        _ = terminate.recv() => {},
    }

    state.draining.store(true, Ordering::SeqCst);
    let _ = stop.send(());

    let drain = config
        .limits
        .provider
        .total
        .max(config.limits.gateway.total)
        + DRAIN_BUFFER;
    match tokio::time::timeout(drain, &mut server).await {
        Ok(result) => result??,
        Err(_) => {
            warn!(timeout_seconds = drain.as_secs(), "proxy drain timed out");
            server.abort();
        }
    }

    Ok(())
}
