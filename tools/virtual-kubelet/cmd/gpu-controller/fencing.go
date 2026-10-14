package main

import (
	"context"
	"errors"
	"fmt"

	coordination "k8s.io/api/coordination/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

var errLeadershipChanged = errors.New("leadership changed before host claim")

func claimHost(ctx context.Context, client kubernetes.Interface, namespace, identity string, elected *coordination.Lease, term string, h host) (int64, error) {
	p := &provider{host: h}
	var current struct {
		Epoch int64 `json:"epoch"`
	}
	if err := p.call(ctx, "fence", "", nil, &current); err != nil {
		return 0, err
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
