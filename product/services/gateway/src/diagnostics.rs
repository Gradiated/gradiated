//! Bounded warning volume during outages. Counters and HTTP responses are never sampled.
use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

const WINDOW: Duration = Duration::from_secs(1);
const BURST: u32 = 10;

#[derive(Default)]
pub(crate) struct WarningBudget {
    window: Option<Instant>,
    emitted: u32,
    suppressed: u64,
}

impl WarningBudget {
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

pub(crate) fn warning_budget(budget: &Mutex<WarningBudget>) -> Option<u64> {
    budget
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take(Instant::now())
}

// One fixed-size budget per call site and process. No user-controlled keys or growing maps.
macro_rules! limited_warn {
    ($($fields:tt)*) => {{
        static BUDGET: std::sync::LazyLock<std::sync::Mutex<$crate::diagnostics::WarningBudget>> =
            std::sync::LazyLock::new(Default::default);
        if tracing::enabled!(tracing::Level::WARN) {
        if let Some(suppressed_events) = $crate::diagnostics::warning_budget(&BUDGET) {
            tracing::warn!(suppressed_events, $($fields)*);
        }
        }
    }};
}
pub(crate) use limited_warn;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounds_bursts_and_reports_suppression_on_next_event() {
        let mut budget = WarningBudget::default();
        let now = Instant::now();
        for _ in 0..BURST {
            assert_eq!(budget.take(now), Some(0));
        }
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now), None);
        assert_eq!(budget.take(now + WINDOW), Some(2));
        assert_eq!(budget.take(now + WINDOW), Some(0));
    }
}

#[cfg(test)]
pub(crate) mod capture {
    use std::{
        io,
        sync::{Arc, Mutex},
    };
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
