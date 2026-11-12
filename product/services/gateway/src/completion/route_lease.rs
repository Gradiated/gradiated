use std::sync::Arc;

use uuid::Uuid;

use crate::{routing::RoutePlacement, session_routing::RouteLease, ServingState};

/// Releases its lease when the generation ends, however it ends.
pub(super) struct HeldRoute {
    serving_state: Arc<dyn ServingState>,
    lease: RouteLease,
}

impl HeldRoute {
    pub(super) fn new(serving_state: Arc<dyn ServingState>, lease: RouteLease) -> Self {
        Self {
            serving_state,
            lease,
        }
    }

    pub(super) async fn move_to(&mut self, deployment_id: Uuid, placement: &RoutePlacement) {
        let next = RouteLease {
            release_digest: placement.release_digest.clone(),
            route_key: placement.route_key,
            deployment_id,
            ..self.lease.clone()
        };
        if next == self.lease {
            return;
        }

        // A missed claim only undercounts one replica until the lease would expire.
        if let Err(error) = self.serving_state.claim_route(&next).await {
            crate::diagnostics::limited_warn!(generation_id = %next.generation_id,
                phase = "route_claim", error_code = error.diagnostic_code(),
                "could not move the session to its fallback replica");
        }

        let previous = std::mem::replace(&mut self.lease, next);
        release(self.serving_state.clone(), previous);
    }
}

impl Drop for HeldRoute {
    fn drop(&mut self) {
        release(self.serving_state.clone(), self.lease.clone());
    }
}

fn release(serving_state: Arc<dyn ServingState>, lease: RouteLease) {
    let Ok(runtime) = tokio::runtime::Handle::try_current() else {
        return;
    };

    runtime.spawn(async move {
        if let Err(error) = serving_state.release_route(&lease).await {
            crate::diagnostics::limited_warn!(generation_id = %lease.generation_id,
                phase = "route_release", error_code = error.diagnostic_code(),
                "route lease stays until it expires");
        }
    });
}
