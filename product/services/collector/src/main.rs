use std::{error::Error, future::IntoFuture, process::ExitCode, sync::Arc};

use gradiated_collector::{admin_router, public_router, Collector, CollectorConfig, Store};
use object_store::{aws::AmazonS3Builder, local::LocalFileSystem, ObjectStore};
use tokio::{
    net::TcpListener,
    signal::unix::{signal, SignalKind},
};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> ExitCode {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            error!(%error, "collector failed");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Box<dyn Error>> {
    let config = CollectorConfig::from_environment()?;
    let mut interrupt = signal(SignalKind::interrupt())?;
    let mut terminate = signal(SignalKind::terminate())?;

    let store: Arc<dyn ObjectStore> = match &config.store {
        Store::S3 { bucket } => Arc::new(
            AmazonS3Builder::from_env()
                .with_bucket_name(bucket)
                .build()?,
        ),
        Store::Local { directory } => {
            std::fs::create_dir_all(directory)?;
            Arc::new(LocalFileSystem::new_with_prefix(directory)?)
        }
    };

    let collector = Collector::start(&config, store)?;
    let public = TcpListener::bind(config.bind_address).await?;
    let admin = TcpListener::bind(config.admin_address).await?;
    info!(
        bind_address = %config.bind_address,
        admin_address = %config.admin_address,
        replica = %config.replica,
        "collector listening"
    );

    tokio::spawn(axum::serve(admin, admin_router(collector.state.clone())).into_future());

    let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
    let server = tokio::spawn(
        axum::serve(public, public_router(collector.state.clone()))
            .with_graceful_shutdown(async {
                let _ = stopped.await;
            })
            .into_future(),
    );

    tokio::select! {
        _ = interrupt.recv() => {},
        _ = terminate.recv() => {},
    }

    let _ = stop.send(());
    let _ = server.await;
    collector.shutdown(config.drain).await;

    Ok(())
}
