package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"sync"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/dynamic"
)

type hostBundle struct {
	SHA256 string `json:"sha256"`
	BaseID string `json:"base_id"`
}

var (
	bundleDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)
	bundleBase   = regexp.MustCompile(`^[A-Za-z0-9._-]{1,64}$`)
)

// targetBundle reads the bundle the gpu-fleet operator chose for a host from
// its GpuHost status; nil means the host keeps the bundle it runs.
func targetBundle(ctx context.Context, objects dynamic.Interface, instanceID string) (*hostBundle, error) {
	object, err := objects.Resource(gpuHosts).Get(ctx, "gpu-"+instanceID, metav1.GetOptions{})
	if err != nil {
		return nil, err
	}
	data, err := json.Marshal(object.Object)
	if err != nil {
		return nil, err
	}
	var item struct {
		Status struct {
			Rollout struct {
				Bundle *struct {
					SHA256 string `json:"sha256"`
					BaseID string `json:"baseId"`
				} `json:"bundle"`
			} `json:"rollout"`
		} `json:"status"`
	}
	if err := json.Unmarshal(data, &item); err != nil {
		return nil, err
	}
	bundle := item.Status.Rollout.Bundle
	if bundle == nil {
		return nil, nil
	}
	if !bundleDigest.MatchString(bundle.SHA256) || !bundleBase.MatchString(bundle.BaseID) {
		return nil, fmt.Errorf("GpuHost gpu-%s names an invalid host bundle", instanceID)
	}
	return &hostBundle{SHA256: bundle.SHA256, BaseID: bundle.BaseID}, nil
}

// hostRegistry tracks the providers this leader has claimed.
type hostRegistry struct {
	mu        sync.Mutex
	providers map[string]*provider
}

func (h *hostRegistry) register(p *provider) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.providers == nil {
		h.providers = map[string]*provider{}
	}
	h.providers[p.host.InstanceID] = p
}

func (h *hostRegistry) snapshot() []*provider {
	h.mu.Lock()
	defer h.mu.Unlock()
	providers := make([]*provider, 0, len(h.providers))
	for _, p := range h.providers {
		providers = append(providers, p)
	}
	return providers
}

// configureHost stages the pod runtimes and, if the operator chose one, the
// host bundle. Only the controller holds the fencing epoch configure needs.
func configureHost(ctx context.Context, objects dynamic.Interface, p *provider) error {
	payload := map[string]any{"operation": "configure", "runtimes": p.host.Runtimes, "epoch": p.epoch, "term": p.term}
	bundle, err := targetBundle(ctx, objects, p.host.InstanceID)
	if err != nil {
		log.Printf("host %s bundle target unavailable: %v", p.host.InstanceID, err)
	} else if bundle != nil {
		payload["host_bundle"] = bundle
	}
	var response map[string]any
	return p.callPayload(ctx, payload, &response)
}

func configureHosts(ctx context.Context, objects dynamic.Interface, registry *hostRegistry, every time.Duration) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		for _, p := range registry.snapshot() {
			if len(p.host.Runtimes) == 0 {
				continue
			}
			request, cancel := context.WithTimeout(ctx, 30*time.Second)
			if err := configureHost(request, objects, p); err != nil {
				log.Printf("host %s configure: %v", p.host.InstanceID, err)
			}
			cancel()
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
