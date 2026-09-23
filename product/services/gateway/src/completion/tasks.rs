use std::{
    future::Future,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc,
    },
};

use tokio::{
    sync::{watch, Notify},
    task::JoinHandle,
};
use tracing::Instrument;

#[derive(Clone)]
pub(super) struct GenerationTasks {
    inner: Arc<GenerationTasksInner>,
}

struct GenerationTasksInner {
    draining: AtomicBool,
    force_shutdown: watch::Sender<bool>,
    active: AtomicUsize,
    idle: Notify,
}

impl GenerationTasks {
    pub(super) fn new() -> Self {
        let (force_shutdown, _) = watch::channel(false);

        Self {
            inner: Arc::new(GenerationTasksInner {
                draining: AtomicBool::new(false),
                force_shutdown,
                active: AtomicUsize::new(0),
                idle: Notify::new(),
            }),
        }
    }

    /// Registers a generation before it checks for draining. With sequentially
    /// consistent ordering, either this sees the drain or the drain waits for it.
    pub(super) fn enter(&self) -> Option<ActiveGeneration> {
        let active = ActiveGeneration::enter(self.inner.clone());

        (!self.is_draining()).then_some(active)
    }

    pub(super) fn subscribe(&self) -> watch::Receiver<bool> {
        self.inner.force_shutdown.subscribe()
    }

    pub(super) fn begin_draining(&self) {
        self.inner.draining.store(true, Ordering::SeqCst);
    }

    pub(super) fn is_draining(&self) -> bool {
        self.inner.draining.load(Ordering::SeqCst)
    }

    pub(super) fn force_shutdown(&self) {
        self.begin_draining();
        self.inner.force_shutdown.send_replace(true);
    }

    pub(super) async fn wait(&self) {
        loop {
            let idle = self.inner.idle.notified();
            if self.inner.active.load(Ordering::SeqCst) == 0 {
                return;
            }

            idle.await;
        }
    }
}

pub(super) struct ActiveGeneration(Arc<GenerationTasksInner>);

impl ActiveGeneration {
    fn enter(inner: Arc<GenerationTasksInner>) -> Self {
        inner.active.fetch_add(1, Ordering::SeqCst);

        Self(inner)
    }

    pub(super) fn spawn<F>(self, future: F) -> JoinHandle<F::Output>
    where
        F: Future + Send + 'static,
        F::Output: Send + 'static,
    {
        tokio::spawn(
            async move {
                let _active = self;
                future.await
            }
            .in_current_span(),
        )
    }
}

impl Drop for ActiveGeneration {
    fn drop(&mut self) {
        if self.0.active.fetch_sub(1, Ordering::SeqCst) == 1 {
            self.0.idle.notify_waiters();
        }
    }
}

pub(super) async fn force_shutdown_requested(force_shutdown: &mut watch::Receiver<bool>) {
    while !*force_shutdown.borrow() {
        if force_shutdown.changed().await.is_err() {
            std::future::pending::<()>().await;
        }
    }
}
