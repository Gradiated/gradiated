package main

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync"

	"github.com/virtual-kubelet/virtual-kubelet/errdefs"
	coordination "k8s.io/api/coordination/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

var (
	errLeadershipChanged = errors.New("leadership changed before host claim")
	errHostAhead         = errors.New("host fencing generation is not behind this controller; another leader holds it")
)

// staleFenceError reports that a host rejected the fencing epoch or term a
// request carried. Unless a re-claim succeeds it is not retried, like other
// invalid host operations.
type staleFenceError struct {
	operation any
	refused   error
}

func (e *staleFenceError) Error() string {
	message := fmt.Sprintf("host operation %v returned 409: stale fencing epoch", e.operation)
	if e.refused != nil {
		message += "; re-claim refused: " + e.refused.Error()
	}
	return message
}
func (e *staleFenceError) InvalidInput() bool { return true }

// hostFence is the fencing generation this leader holds on one host. The
// host's providers share it, so a re-claim reaches pod and configure requests.
type hostFence struct {
	mu    sync.Mutex
	epoch int64
	term  string
	// claim claims the host again for this leader's term while the host's
	// generation is below held. It is nil where re-claiming is not allowed.
	claim func(ctx context.Context, held int64) (int64, error)
}

func (f *hostFence) current() (int64, string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.epoch, f.term
}

// reclaim restores this leader's claim on a host that rejected epoch sent. A
// host whose generation went backwards lost its fence file, for example in a
// re-image. A host at or ahead of sent was claimed by another leader, and the
// claim refuses it. A claim that failed for a transient reason stays retryable.
func (f *hostFence) reclaim(ctx context.Context, sent int64, cause *staleFenceError) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.epoch != sent {
		// A concurrent request already re-claimed the host.
		return nil
	}
	if f.claim == nil {
		return cause
	}
	epoch, err := f.claim(ctx, sent)
	if errors.Is(err, errHostAhead) || errors.Is(err, errLeadershipChanged) || errdefs.IsInvalidInput(err) {
		return &staleFenceError{operation: cause.operation, refused: err}
	}
	if err != nil {
		return fmt.Errorf("%v; re-claim failed: %w", cause, err)
	}
	f.epoch = epoch
	return nil
}

// leaderFence holds the generation a leader claimed on h. The leader may claim
// h again, under the same lease and term, after the host lost its fence file;
// losing the lease meanwhile calls lost.
func leaderFence(client kubernetes.Interface, namespace, identity string, elected *coordination.Lease, term string, h host, epoch int64, lost func()) *hostFence {
	return &hostFence{epoch: epoch, term: term, claim: func(ctx context.Context, held int64) (int64, error) {
		epoch, err := claimHostBelow(ctx, client, namespace, identity, elected, term, h, held)
		if errors.Is(err, errLeadershipChanged) {
			lost()
		}
		return epoch, err
	}}
}

func claimHost(ctx context.Context, client kubernetes.Interface, namespace, identity string, elected *coordination.Lease, term string, h host) (int64, error) {
	return claimHostBelow(ctx, client, namespace, identity, elected, term, h, math.MaxInt64)
}

// claimHostBelow claims h only while its fencing generation is below limit.
// The claim names the generation it read, so the host rejects it if another
// leader claims the host in between.
func claimHostBelow(ctx context.Context, client kubernetes.Interface, namespace, identity string, elected *coordination.Lease, term string, h host, limit int64) (int64, error) {
	p := &provider{host: h}
	var current struct {
		Epoch int64 `json:"epoch"`
	}
	if err := p.callPayload(ctx, map[string]any{"operation": "fence"}, &current); err != nil {
		return 0, err
	}
	if current.Epoch >= limit {
		return 0, errHostAhead
	}
	lease, err := client.CoordinationV1().Leases(namespace).Get(ctx, "gpu-controller", metav1.GetOptions{})
	if err != nil {
		return 0, err
	}
	if ctx.Err() != nil || lease.UID != elected.UID || lease.Spec.AcquireTime == nil || elected.Spec.AcquireTime == nil || lease.Spec.HolderIdentity == nil || *lease.Spec.HolderIdentity != identity || !lease.Spec.AcquireTime.Equal(elected.Spec.AcquireTime) {
		return 0, errLeadershipChanged
	}
	var claimed struct {
		Epoch int64 `json:"epoch"`
	}
	if err := p.callPayload(ctx, map[string]any{"operation": "claim", "epoch": current.Epoch, "term": term}, &claimed); err != nil {
		return 0, err
	}
	if claimed.Epoch < 1 || claimed.Epoch < current.Epoch {
		return 0, fmt.Errorf("host returned an invalid fencing generation")
	}
	return claimed.Epoch, nil
}
