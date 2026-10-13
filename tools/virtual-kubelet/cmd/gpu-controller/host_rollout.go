package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"sync"
	"time"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
)

type hostBundle struct {
	SHA256 string `json:"sha256"`
	BaseID string `json:"base_id"`
}

func (b *hostBundle) validate() error {
	if b != nil && (!regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(b.SHA256) || !regexp.MustCompile(`^[A-Za-z0-9._-]+$`).MatchString(b.BaseID)) {
		return fmt.Errorf("invalid host bundle pin")
	}
	return nil
}

type hostVersion struct {
	InstanceID    string `json:"instance_id"`
	Current       string `json:"host_bundle_sha256"`
	Previous      string `json:"previous_host_bundle_sha256"`
	Failed        string `json:"host_bundle_failed_sha256"`
	StagingFailed string `json:"host_bundle_staging_failed_sha256"`
	Trial         bool   `json:"host_bundle_trial"`
	Launcher      bool   `json:"host_launcher"`
}

type rolloutHost struct {
	version   hostVersion
	seen      time.Time
	completed bool
	checked   bool
}

type hostRollout struct {
	mu           sync.Mutex
	pin          *hostBundle
	order        []string
	hosts        map[string]rolloutHost
	active       string
	started      time.Time
	healthySince time.Time
	baseline     map[string]string
	failed       bool
	failureHost  string
	now          func() time.Time
}

func newHostRollout(pin *hostBundle, hosts []host) *hostRollout {
	r := &hostRollout{pin: pin, hosts: map[string]rolloutHost{}, now: time.Now}
	for _, h := range hosts {
		r.order = append(r.order, h.InstanceID)
	}
	return r
}

func (p *provider) serving(ctx context.Context) (map[string]string, error) {
	var pods []*v1.Pod
	if err := p.call(ctx, "list", "", nil, &pods); err != nil {
		return nil, err
	}
	identities := map[string]string{}
	for _, pod := range pods {
		if pod.Annotations["gradiated.com/workload-kind"] == "training" || pod.DeletionTimestamp != nil {
			continue
		}
		var status struct {
			Running  bool `json:"running"`
			Ready    bool `json:"ready"`
			Draining bool `json:"draining"`
			Epoch    struct {
				PID   int    `json:"pid"`
				Birth string `json:"birth"`
			} `json:"epoch"`
		}
		if err := p.call(ctx, "status", string(pod.UID), nil, &status); err != nil {
			return nil, err
		}
		if !status.Running || !status.Ready || status.Draining {
			return nil, fmt.Errorf("pod %s is not serving", pod.Name)
		}
		identities[string(pod.UID)] = fmt.Sprintf("%d:%s", status.Epoch.PID, status.Epoch.Birth)
	}
	if p.client != nil {
		desired, err := p.client.Pods("gpu-inference").List(ctx, metav1.ListOptions{FieldSelector: "spec.nodeName=gpu-" + p.host.InstanceID})
		if err != nil {
			return nil, err
		}
		for _, pod := range desired.Items {
			if pod.Spec.NodeName != "gpu-"+p.host.InstanceID || pod.DeletionTimestamp != nil || pod.Annotations["gradiated.com/workload-kind"] == "training" {
				continue
			}
			if _, exists := identities[string(pod.UID)]; !exists {
				return nil, fmt.Errorf("assigned pod %s is missing from the host", pod.Name)
			}
		}
	}
	return identities, nil
}

func (r *hostRollout) annotate(ctx context.Context, p *provider, key string) error {
	data, _ := json.Marshal(map[string]any{"metadata": map[string]any{"annotations": map[string]string{key: r.pin.SHA256}}})
	_, err := p.client.Nodes().Patch(ctx, "gpu-"+p.host.InstanceID, types.MergePatchType, data, metav1.PatchOptions{})
	return err
}

func (r *hostRollout) fail(ctx context.Context, p *provider, reason string) {
	r.failed = true
	r.failureHost = p.host.InstanceID
	// The node annotation survives leader changes; a new digest is the retry boundary.
	_ = r.annotate(ctx, p, "gradiated.com/host-bundle-failed")
	event := &v1.Event{ObjectMeta: metav1.ObjectMeta{GenerateName: "gpu-host-update-", Namespace: "gpu-inference"},
		InvolvedObject: v1.ObjectReference{Kind: "Node", Name: "gpu-" + p.host.InstanceID},
		Reason:         "GpuHostUpdateFailed", Message: reason, Type: v1.EventTypeWarning,
		FirstTimestamp: metav1.Now(), LastTimestamp: metav1.Now(), Count: 1,
		Source: v1.EventSource{Component: "gpu-controller"}}
	_, _ = p.client.Events("gpu-inference").Create(ctx, event, metav1.CreateOptions{})
}

func (r *hostRollout) observe(ctx context.Context, p *provider, version hostVersion) {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := r.now()
	state := r.hosts[p.host.InstanceID]
	if r.active == p.host.InstanceID && !state.seen.IsZero() && now.Sub(state.seen) > 30*time.Second {
		r.healthySince = time.Time{}
	}
	state.version, state.seen = version, now
	r.hosts[p.host.InstanceID] = state
	if r.pin == nil || r.failed {
		return
	}
	node, err := p.client.Nodes().Get(ctx, "gpu-"+p.host.InstanceID, metav1.GetOptions{})
	if err != nil {
		return
	}
	if node.Annotations["gradiated.com/host-bundle-failed"] == r.pin.SHA256 || version.Failed == r.pin.SHA256 || version.StagingFailed == r.pin.SHA256 {
		r.fail(ctx, p, "Host bundle staging or rollback rejected "+r.pin.SHA256)
		return
	}
	state.checked = true
	state.completed = node.Annotations["gradiated.com/host-bundle-ready"] == r.pin.SHA256 && version.Current == r.pin.SHA256 && !version.Trial
	r.hosts[p.host.InstanceID] = state
	if r.active == "" {
		// Observe every host before choosing a canary or continuing after a leader change.
		for _, id := range r.order {
			h, ok := r.hosts[id]
			if !ok || !h.checked || now.Sub(h.seen) > 30*time.Second {
				return
			}
		}
		for _, id := range r.order {
			if !r.hosts[id].completed {
				r.active = id
				break
			}
		}
		if r.active == "" {
			return
		}
		r.started, r.healthySince, r.baseline = now, time.Time{}, nil
	}
	if r.active != p.host.InstanceID {
		return
	}
	if !version.Launcher {
		r.fail(ctx, p, "Install the host launcher before pinning a host bundle")
		return
	}
	if now.Sub(r.started) > 35*time.Minute {
		r.fail(ctx, p, "Host bundle rollout exceeded staging and health deadline")
		return
	}
	identities, err := p.serving(ctx)
	if err != nil {
		r.healthySince = time.Time{}
		if version.Current == r.pin.SHA256 && now.Sub(r.started) > 120*time.Second {
			r.fail(ctx, p, "Updated host is not serving its pods")
		}
		return
	}
	if r.baseline == nil {
		r.baseline = identities
	}
	for uid, identity := range r.baseline {
		if current, exists := identities[uid]; exists && current != identity {
			r.fail(ctx, p, "A serving process changed identity during the host update")
			return
		}
	}
	if version.Current != r.pin.SHA256 {
		r.healthySince = time.Time{}
		var result map[string]any
		err = p.callPayload(ctx, map[string]any{"operation": "configure", "runtimes": p.host.Runtimes, "host_bundle": r.pin, "epoch": p.epoch, "term": p.term}, &result)
		if err != nil {
			r.fail(ctx, p, fmt.Sprintf("Host bundle configure failed: %v", err))
		}
		return
	}
	if version.Trial {
		r.healthySince = time.Time{}
		return
	}
	if r.healthySince.IsZero() {
		r.healthySince = now
	}
	if now.Sub(r.healthySince) >= 5*time.Minute {
		if r.annotate(ctx, p, "gradiated.com/host-bundle-ready") != nil {
			return
		}
		state.completed = true
		r.hosts[p.host.InstanceID] = state
		r.active = ""
	}
}

func (r *hostRollout) metrics(w http.ResponseWriter, _ *http.Request) {
	r.mu.Lock()
	defer r.mu.Unlock()
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	for id, h := range r.hosts {
		fmt.Fprintf(w, "gradiated_gpu_host_bundle_info{instance_id=%q,sha256=%q,previous_sha256=%q} 1\n", id, h.version.Current, h.version.Previous)
		drift := 0
		if r.pin != nil && h.version.Current != r.pin.SHA256 {
			drift = 1
		}
		fmt.Fprintf(w, "gradiated_gpu_host_bundle_drift{instance_id=%q} %d\n", id, drift)
	}
	failed := 0
	if r.failed {
		failed = 1
	}
	fmt.Fprintf(w, "gradiated_gpu_host_update_failed{instance_id=%q} %d\n", r.failureHost, failed)
}

func (r *hostRollout) unavailable(ctx context.Context, p *provider) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.pin == nil || r.failed || r.active != p.host.InstanceID {
		return
	}
	r.healthySince = time.Time{}
	if r.now().Sub(r.hosts[p.host.InstanceID].seen) > 120*time.Second {
		r.fail(ctx, p, "Host remained unreachable during its bundle update")
	}
}
