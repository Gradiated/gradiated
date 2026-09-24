use super::*;
use axum::{body::Body, routing::get, Router};
use futures_util::stream;
use tokio::{net::TcpListener, sync::oneshot, time::Instant};

#[tokio::test]
async fn graceful_shutdown_preserves_an_untracked_stream_beyond_five_seconds() {
    let (release, released) = oneshot::channel();
    let released = Arc::new(tokio::sync::Mutex::new(Some(released)));
    let app = Router::new().route(
        "/stream",
        get(move || {
            let released = released.clone();
            async move {
                let released = released.lock().await.take().unwrap();
                Body::from_stream(stream::once(async move {
                    released.await.unwrap();
                    Ok::<_, std::io::Error>("complete")
                }))
            }
        }),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let (stop, stopped) = oneshot::channel();
    let mut server = tokio::spawn(
        axum::serve(listener, app)
            .with_graceful_shutdown(async { stopped.await.unwrap() })
            .into_future(),
    );
    let response = reqwest::get(format!("http://{address}/stream"))
        .await
        .unwrap();
    stop.send(()).unwrap();
    let draining = tokio::spawn(async move {
        finish_http_shutdown(&mut server, Instant::now() + Duration::from_secs(10))
            .await
            .is_ok()
    });

    // No CompletionService generation exists, so only the HTTP drain holds it.
    tokio::time::sleep(Duration::from_secs(6)).await;
    assert!(!draining.is_finished());
    release.send(()).unwrap();
    assert_eq!(response.text().await.unwrap(), "complete");
    assert!(draining.await.unwrap());
}

#[tokio::test]
async fn http_shutdown_remains_bounded_for_a_stuck_connection() {
    let mut server = tokio::spawn(std::future::pending::<std::io::Result<()>>());
    let result =
        finish_http_shutdown(&mut server, Instant::now() + Duration::from_millis(20)).await;

    assert!(result.is_ok());
    assert!(server.await.unwrap_err().is_cancelled());
}
