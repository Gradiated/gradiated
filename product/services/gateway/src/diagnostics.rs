//! Bounded warning volume during outages. Counters and HTTP responses are never sampled.
use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

const WINDOW: Duration = Duration::from_secs(1);
const BURST: u32 = 10;

#[derive(Default)]
pub(crate) struct LogBudget {
    window: Option<Instant>,
    emitted: u32,
    suppressed: u64,
}

impl LogBudget {
    pub(crate) fn take_now(budget: &Mutex<Self>) -> Option<u64> {
        budget
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take(Instant::now())
    }

    fn take(&mut self, now: Instant) -> Option<u64> {
        if self
            .window
            .is_none_or(|start| now.duration_since(start) >= WINDOW)
        {
            self.window = Some(now);
            self.emitted = 0;
        }

        if self.emitted == BURST {
            self.suppressed = self.suppressed.saturating_add(1);
            return None;
        }

        self.emitted += 1;
        Some(std::mem::take(&mut self.suppressed))
    }
}

// One fixed-size budget per call site and process. No user-controlled keys or growing maps.
macro_rules! limited {
    ($level:expr, $($fields:tt)*) => {{
        static BUDGET: std::sync::LazyLock<std::sync::Mutex<$crate::diagnostics::LogBudget>> =
            std::sync::LazyLock::new(Default::default);

        if tracing::enabled!($level) {
            if let Some(suppressed_events) = $crate::diagnostics::LogBudget::take_now(&BUDGET) {
                tracing::event!($level, suppressed_events, $($fields)*);
            }
        }
    }};
}
pub(crate) use limited;

macro_rules! limited_warn {
    ($($fields:tt)*) => { $crate::diagnostics::limited!(tracing::Level::WARN, $($fields)*) };
}
pub(crate) use limited_warn;

macro_rules! limited_error {
    ($($fields:tt)*) => { $crate::diagnostics::limited!(tracing::Level::ERROR, $($fields)*) };
}
pub(crate) use limited_error;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounds_bursts_and_reports_suppression_on_next_event() {
        let mut budget = LogBudget::default();
        let now = Instant::now();
        for _ in 0..BURST {
            assert_eq!(budget.take(now), Some(0));
        }
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now + WINDOW), Some(2));
        assert_eq!(budget.take(now + WINDOW), Some(0));
    }

    #[test]
    fn limited_macros_emit_at_their_level_with_the_suppression_count() {
        let logs = capture::Logs::default();
        let _guard = logs.start();

        limited_error!(phase = "error_probe", "probe");
        limited_warn!(phase = "warn_probe", "probe");

        let events = logs.events();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["level"], "ERROR");
        assert_eq!(events[0]["fields"]["phase"], "error_probe");
        assert_eq!(events[0]["fields"]["suppressed_events"], 0);
        assert_eq!(events[1]["level"], "WARN");
        assert_eq!(events[1]["fields"]["phase"], "warn_probe");
        assert_eq!(events[1]["fields"]["suppressed_events"], 0);
    }
}

#[cfg(test)]
pub(crate) mod capture {
    use std::{
        io,
        sync::{Arc, LazyLock, Mutex},
    };

    // tracing caches each callsite's interest globally. While a single dispatcher
    // is registered, a callsite first reached on a thread without a capture is
    // cached as never and stays silent for every later capture. A permanent
    // second dispatcher makes registration consult every live dispatcher.
    static PERMANENT_DISPATCH: LazyLock<tracing::Dispatch> = LazyLock::new(|| {
        tracing::Dispatch::new(tracing_subscriber::fmt().with_writer(io::sink).finish())
    });

    #[derive(Clone, Default)]
    pub(crate) struct Logs(Arc<Mutex<Vec<u8>>>);

    impl io::Write for Logs {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Logs {
        pub(crate) fn start(&self) -> tracing::subscriber::DefaultGuard {
            LazyLock::force(&PERMANENT_DISPATCH);
            let logs = self.clone();
            tracing::subscriber::set_default(
                tracing_subscriber::fmt()
                    .json()
                    .with_ansi(false)
                    .without_time()
                    .with_writer(move || logs.clone())
                    .finish(),
            )
        }

        pub(crate) fn events(&self) -> Vec<serde_json::Value> {
            String::from_utf8(self.0.lock().unwrap().clone())
                .unwrap()
                .lines()
                .map(|line| serde_json::from_str(line).unwrap())
                .collect()
        }
    }
}

/// Identity fields are populated only after credential verification. Never record
/// headers, credential digests, provider keys or request bodies on this span.
pub(crate) fn request_span(generation_id: uuid::Uuid) -> tracing::Span {
    tracing::info_span!("inference_request", service = "gateway", %generation_id,
        organization_id = tracing::field::Empty,
        workspace_id = tracing::field::Empty,
        api_key_id = tracing::field::Empty)
}
