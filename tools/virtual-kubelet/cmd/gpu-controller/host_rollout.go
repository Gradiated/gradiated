package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"regexp"
	"sync"
	"time"

	"github.com/virtual-kubelet/virtual-kubelet/errdefs"
	v1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
)

const hostUpdateAnnotation = "gradiated.com/host-bundle-update"

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

type hostCheckpoint struct {
	SHA256   string            `json:"sha256"`
	Phase    string            `json:"phase"`
	Started  time.Time         `json:"started"`
	Applied  time.Time         `json:"applied,omitempty"`
	Baseline map[string]string `json:"baseline,omitempty"`
	Reason   string            `json:"reason,omitempty"`
}

func checkpoint(node *v1.Node, digest string) (hostCheckpoint, error) {
	var state hostCheckpoint
	if data := node.Annotations[hostUpdateAnnotation]; data != "" {
		if err := json.Unmarshal([]byte(data), &state); err != nil {
			return state, err
		}
		if state.SHA256 == digest && (state.Phase != "ready" && state.Phase != "failed" && state.Phase != "updating" || state.Started.IsZero()) {
			return state, fmt.Errorf("invalid host update checkpoint")
		}
	} else if node.Annotations["gradiated.com/host-bundle-failed"] == digest {
		state = hostCheckpoint{SHA256: digest, Phase: "failed"}
	} else if node.Annotations["gradiated.com/host-bundle-ready"] == digest {
		state = hostCheckpoint{SHA256: digest, Phase: "ready"}
	}
	return state, nil
}

type rolloutSample struct {
	version    hostVersion
	checkpoint hostCheckpoint
	reachable  bool
	checked    bool
}

type rolloutFailure struct {
	provider   *provider
	checkpoint hostCheckpoint
	persisted  bool
	reported   bool
}

type observedHost struct {
	version  hostVersion
	lastSeen time.Time
}

type hostRollout struct {
	mu           sync.RWMutex
	pin          *hostBundle
	order        []string
	providers    map[string]*provider
	versions     map[string]observedHost
	failureLabel string

	active           string
	healthySince     time.Time
	lastSample       time.Time
	unavailableSince time.Time
	unhealthySince   time.Time
	failure          *rolloutFailure
	now              func() time.Time
}

func newHostRollout(pin *hostBundle, hosts []host) *hostRollout {
	r := &hostRollout{pin: pin, providers: map[string]*provider{}, versions: map[string]observedHost{}, now: time.Now}
	for _, h := range hosts {
		r.order = append(r.order, h.InstanceID)
	}
	return r
}

func (r *hostRollout) register(p *provider) {
	r.mu.Lock()
	r.providers[p.host.InstanceID] = p
	r.mu.Unlock()
}

func (r *hostRollout) snapshot() map[string]*provider {
	r.mu.RLock()
	defer r.mu.RUnlock()
	providers := map[string]*provider{}
	for id, p := range r.providers {
		providers[id] = p
	}
	return providers
}

func (r *hostRollout) recordVersion(id string, version hostVersion) {
	r.mu.Lock()
	r.versions[id] = observedHost{version: version, lastSeen: r.now()}
	r.mu.Unlock()
}

func saveCheckpoint(ctx context.Context, p *provider, state hostCheckpoint) error {
	value, err := json.Marshal(state)
	if err != nil {
		return err
	}
	data, _ := json.Marshal(map[string]any{"metadata": map[string]any{"annotations": map[string]string{hostUpdateAnnotation: string(value)}}})
	_, err = p.client.Nodes().Patch(ctx, "gpu-"+p.host.InstanceID, types.MergePatchType, data, metav1.PatchOptions{})
	return err
}

func (r *hostRollout) fail(p *provider, state hostCheckpoint, reason string) {
	if r.failure != nil {
		return
	}
	state.SHA256, state.Phase, state.Reason = r.pin.SHA256, "failed", reason
	if state.Started.IsZero() {
		state.Started = r.now()
	}
	r.failure = &rolloutFailure{provider: p, checkpoint: state}
	r.mu.Lock()
	r.failureLabel = p.host.InstanceID
	r.mu.Unlock()
	log.Printf("host %s bundle update stopped: %s", p.host.InstanceID, reason)
}

func (r *hostRollout) persistFailure(ctx context.Context) {
	failure := r.failure
	if !failure.persisted {
		if err := saveCheckpoint(ctx, failure.provider, failure.checkpoint); err != nil {
			log.Printf("host %s failure checkpoint retry: %v", failure.provider.host.InstanceID, err)
			return
		}
		failure.persisted = true
	}
	if failure.reported {
		return
	}
	id := failure.provider.host.InstanceID
	event := &v1.Event{ObjectMeta: metav1.ObjectMeta{Name: "gpu-host-update-" + id + "." + r.pin.SHA256[:16], Namespace: "gpu-inference"},
		InvolvedObject: v1.ObjectReference{Kind: "Node", Name: "gpu-" + id},
		Reason:         "GpuHostUpdateFailed", Message: failure.checkpoint.Reason, Type: v1.EventTypeWarning,
		FirstTimestamp: metav1.Now(), LastTimestamp: metav1.Now(), Count: 1, Source: v1.EventSource{Component: "gpu-controller"}}
	_, err := failure.provider.client.Events("gpu-inference").Create(ctx, event, metav1.CreateOptions{})
	if err == nil || apierrors.IsAlreadyExists(err) {
		failure.reported = true
	} else {
		log.Printf("host %s failure event retry: %v", id, err)
	}
}

func (r *hostRollout) poll(ctx context.Context, p *provider) rolloutSample {
	var sample rolloutSample
	checkpointReady := r.pin == nil
	if r.pin != nil {
		node, err := p.client.Nodes().Get(ctx, "gpu-"+p.host.InstanceID, metav1.GetOptions{})
		if err == nil {
			sample.checkpoint, err = checkpoint(node, r.pin.SHA256)
			if err != nil {
				r.fail(p, sample.checkpoint, "Invalid durable host update checkpoint")
			} else {
				checkpointReady = true
			}
		}
	}
	if err := p.call(ctx, "ping", "", nil, &sample.version); err != nil || sample.version.InstanceID != p.host.InstanceID {
		return sample
	}
	sample.reachable = true
	r.recordVersion(p.host.InstanceID, sample.version)
	if len(p.host.Runtimes) > 0 {
		var response map[string]any
		if err := p.call(ctx, "configure", "", nil, &response); err != nil {
			return sample
		}
	}
	sample.checked = checkpointReady
	return sample
}

func (r *hostRollout) step(ctx context.Context) {
	providers := r.snapshot()
	samples := map[string]rolloutSample{}
	allReady := len(providers) == len(r.order)
	for _, id := range r.order {
		p := providers[id]
		if p == nil {
			allReady = false
			continue
		}
		request, cancel := context.WithTimeout(ctx, 10*time.Second)
		sample := r.poll(request, p)
		cancel()
		samples[id] = sample
		allReady = allReady && sample.reachable && sample.checked
		if r.pin != nil && r.failure == nil && (sample.checkpoint.SHA256 == r.pin.SHA256 && sample.checkpoint.Phase == "failed" || sample.version.Failed == r.pin.SHA256 || sample.version.StagingFailed == r.pin.SHA256) {
			reason := sample.checkpoint.Reason
			if reason == "" {
				reason = "Host bundle staging or rollback rejected " + r.pin.SHA256
			}
			r.fail(p, sample.checkpoint, reason)
		}
	}
	if r.pin == nil {
		return
	}
	request, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	defer func() {
		if r.failure != nil {
			r.persistFailure(request)
		}
	}()
	if r.failure != nil {
		return
	}
	now := r.now()
	if r.active == "" {
		for _, id := range r.order {
			state := samples[id].checkpoint
			if state.SHA256 == r.pin.SHA256 && state.Phase == "updating" {
				if r.active != "" {
					r.fail(providers[id], state, "Multiple host updates are in progress")
					return
				}
				r.active = id
			}
		}
		if r.active == "" && allReady {
			for _, id := range r.order {
				sample := samples[id]
				if sample.checkpoint.SHA256 != r.pin.SHA256 || sample.checkpoint.Phase != "ready" || sample.version.Current != r.pin.SHA256 || sample.version.Trial {
					r.active = id
					break
				}
			}
		}
	}
	if r.active == "" {
		return
	}
	p := providers[r.active]
	sample := samples[r.active]
	state := sample.checkpoint
	if state.SHA256 == r.pin.SHA256 && state.Phase == "updating" && state.Applied.IsZero() && sample.version.Current != r.pin.SHA256 && now.Sub(state.Started) > 35*time.Minute {
		r.fail(p, state, "Host bundle staging exceeded its deadline")
	} else if !sample.reachable {
		r.healthySince = time.Time{}
		if r.unavailableSince.IsZero() {
			r.unavailableSince = now
		}
		if now.Sub(r.unavailableSince) >= 120*time.Second {
			r.fail(p, state, "Host remained unreachable during its bundle update")
		}
	} else {
		r.unavailableSince = time.Time{}
	}
	if r.failure != nil {
		return
	}
	if !allReady {
		r.healthySince = time.Time{}
		return
	}
	if !sample.version.Launcher {
		r.fail(p, state, "Install the host launcher before pinning a host bundle")
		return
	}
	if !r.lastSample.IsZero() && now.Sub(r.lastSample) > 30*time.Second {
		r.healthySince = time.Time{}
	}
	r.lastSample = now
	if state.SHA256 == r.pin.SHA256 && state.Phase == "updating" && sample.version.Current == r.pin.SHA256 && state.Applied.IsZero() {
		state.Applied = now
		if saveCheckpoint(request, p, state) != nil {
			r.healthySince = time.Time{}
			return
		}
	}
	identities, err := p.serving(request)
	if err != nil {
		r.healthySince = time.Time{}
		if sample.version.Current == r.pin.SHA256 {
			if r.unhealthySince.IsZero() {
				r.unhealthySince = now
			}
			if now.Sub(r.unhealthySince) >= 120*time.Second {
				r.fail(p, state, "Updated host is not serving its pods")
			}
		}
		return
	}
	if state.SHA256 != r.pin.SHA256 || state.Phase != "updating" {
		state = hostCheckpoint{SHA256: r.pin.SHA256, Phase: "updating", Started: now, Baseline: identities}
		if err := saveCheckpoint(request, p, state); err != nil {
			log.Printf("host %s update checkpoint retry: %v", r.active, err)
			return
		}
	}
	for uid, identity := range state.Baseline {
		if current, exists := identities[uid]; !exists || current != identity {
			r.fail(p, state, "A serving process changed identity during the host update")
			return
		}
	}
	if sample.version.Current != r.pin.SHA256 {
		r.healthySince = time.Time{}
		if !state.Applied.IsZero() {
			r.fail(p, state, "Host reverted after applying its bundle")
			return
		}
		var response map[string]any
		if err := p.callPayload(request, map[string]any{"operation": "configure", "runtimes": p.host.Runtimes, "host_bundle": r.pin, "epoch": p.epoch, "term": p.term}, &response); err != nil {
			if errdefs.IsInvalidInput(err) {
				r.fail(p, state, fmt.Sprintf("Host rejected bundle configuration: %v", err))
			} else {
				log.Printf("host %s bundle configure retry: %v", r.active, err)
			}
		}
		return
	}
	if state.Applied.IsZero() {
		state.Applied = now
		if err := saveCheckpoint(request, p, state); err != nil {
			return
		}
	}
	if sample.version.Trial {
		r.healthySince = time.Time{}
		if r.unhealthySince.IsZero() {
			r.unhealthySince = now
		}
		if now.Sub(r.unhealthySince) >= 120*time.Second {
			r.fail(p, state, "Updated agent did not complete its health trial")
		}
		return
	}
	r.unhealthySince = time.Time{}
	if r.healthySince.IsZero() {
		r.healthySince = now
	}
	if now.Sub(r.healthySince) >= 5*time.Minute {
		state.Phase = "ready"
		if saveCheckpoint(request, p, state) != nil {
			return
		}
		r.active = ""
		r.healthySince, r.lastSample = time.Time{}, time.Time{}
	}
}

func (r *hostRollout) run(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	for {
		r.step(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (r *hostRollout) metrics(w http.ResponseWriter, _ *http.Request) {
	r.mu.RLock()
	versions := map[string]observedHost{}
	for id, version := range r.versions {
		versions[id] = version
	}
	failure := r.failureLabel
	r.mu.RUnlock()
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	for _, id := range r.order {
		observed, exists := versions[id]
		lastSeen := int64(0)
		if exists {
			lastSeen = observed.lastSeen.Unix()
		}
		fmt.Fprintf(w, "gradiated_gpu_host_last_seen_seconds{instance_id=%q} %d\n", id, lastSeen)
		if !exists {
			continue
		}
		version := observed.version
		fmt.Fprintf(w, "gradiated_gpu_host_bundle_info{instance_id=%q,sha256=%q,previous_sha256=%q} 1\n", id, version.Current, version.Previous)
		drift := 0
		if r.pin != nil && version.Current != r.pin.SHA256 {
			drift = 1
		}
		fmt.Fprintf(w, "gradiated_gpu_host_bundle_drift{instance_id=%q} %d\n", id, drift)
	}
	failed := 0
	if failure != "" {
		failed = 1
	}
	fmt.Fprintf(w, "gradiated_gpu_host_update_failed{instance_id=%q} %d\n", failure, failed)
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
