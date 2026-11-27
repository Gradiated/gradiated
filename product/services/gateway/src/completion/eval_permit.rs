use std::sync::Arc;

use crate::{serving_state::EvalLease, ServingState};

/// Holds the generation's slot in its workspace's eval limits until it ends.
pub(super) struct EvalPermit {
    serving_state: Arc<dyn ServingState>,
    lease: EvalLease,
}

impl EvalPermit {
    pub(super) fn new(serving_state: Arc<dyn ServingState>, lease: EvalLease) -> Self {
        Self {
            serving_state,
            lease,
        }
    }
}

impl Drop for EvalPermit {
    fn drop(&mut self) {
        let Ok(runtime) = tokio::runtime::Handle::try_current() else {
            return;
        };
        let serving_state = self.serving_state.clone();
        let lease = self.lease.clone();

        runtime.spawn(async move {
            if let Err(error) = serving_state.release_eval(&lease).await {
                crate::diagnostics::limited_warn!(generation_id = %lease.generation_id,
                    phase = "eval_release", error_code = error.diagnostic_code(),
                    "the eval slot stays taken until its lease expires");
            }
        });
    }
}
