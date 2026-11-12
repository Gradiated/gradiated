package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"sort"
	"strings"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
)

var gpuHosts = schema.GroupVersionResource{Group: "fleet.gradiated.com", Version: "v1alpha1", Resource: "gpuhosts"}

const faultDomainLabel = "gradiated.com/fault-domain"

type gpuHost struct {
	Metadata struct {
		Name string `json:"name"`
	} `json:"metadata"`
	Spec struct {
		InstanceID  string     `json:"instanceId"`
		ExtraTaints hostTaints `json:"extraTaints,omitempty"`
		Provider    struct {
			MachineID string `json:"machineId"`
		} `json:"provider"`
		Inventory struct {
			GPUProduct string `json:"gpuProduct"`
			GPUCount   int64  `json:"gpuCount"`
			CPU        int64  `json:"cpu"`
			MemoryGiB  int64  `json:"memoryGiB"`
		} `json:"inventory"`
	} `json:"spec"`
}

// The GpuHost CRD enforces the same bounds at admission;
// tools/gpu/render_config_test.py checks that they agree.
func validateHost(h host) error {
	if h.GPUCount < 1 || h.GPUCount > 8 || h.CPU < 1 || h.CPU > 512 || h.MemoryGiB < 1 || h.MemoryGiB > 4096 {
		return fmt.Errorf("host %s has invalid resource capacity", h.InstanceID)
	}
	return validateExtraTaints(h.ExtraTaints)
}

func hostFromObject(object map[string]any) (host, error) {
	data, err := json.Marshal(object)
	if err != nil {
		return host{}, err
	}
	var item gpuHost
	if err := json.Unmarshal(data, &item); err != nil {
		return host{}, err
	}
	id := item.Spec.InstanceID
	if item.Metadata.Name != "gpu-"+id {
		return host{}, fmt.Errorf("GpuHost %s is not named after instance %s", item.Metadata.Name, id)
	}
	h := host{
		InstanceID:  id,
		Endpoint:    "http://gpu-" + id + ".tailscale-inference.svc.cluster.local:8888/_kubelet",
		TokenFile:   "/var/run/gradiated-host-keys/" + id,
		GPUCount:    item.Spec.Inventory.GPUCount,
		CPU:         item.Spec.Inventory.CPU,
		MemoryGiB:   item.Spec.Inventory.MemoryGiB,
		GPUProduct:  item.Spec.Inventory.GPUProduct,
		FaultDomain: item.Spec.Provider.MachineID,
		ExtraTaints: item.Spec.ExtraTaints,
	}
	return h, validateHost(h)
}

// listHosts reads the fleet from GpuHost objects, sorted by instance ID. An
// invalid object is skipped and logged; the gpu-fleet operator marks it Degraded.
func listHosts(ctx context.Context, client dynamic.Interface) ([]host, error) {
	list, err := client.Resource(gpuHosts).List(ctx, metav1.ListOptions{})
	if err != nil {
		return nil, err
	}
	hosts := make([]host, 0, len(list.Items))
	for _, item := range list.Items {
		h, err := hostFromObject(item.Object)
		if err != nil {
			log.Printf("skipping GpuHost %s: %v", item.GetName(), err)
			continue
		}
		hosts = append(hosts, h)
	}
	sort.Slice(hosts, func(i, j int) bool { return hosts[i].InstanceID < hosts[j].InstanceID })
	return hosts, nil
}

func hostsSignature(hosts []host) string {
	data, _ := json.Marshal(hosts)
	return string(data)
}

// watchHosts calls changed once when the GpuHost fleet differs from the one
// this leader started with. The leader then steps down so a fresh leader
// starts with the new fleet.
func watchHosts(ctx context.Context, client dynamic.Interface, current []host, every time.Duration, changed func()) {
	started := hostsSignature(current)
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(every):
		}
		hosts, err := listHosts(ctx, client)
		if err != nil {
			log.Printf("GpuHost watch: %v", err)
			continue
		}
		if hostsSignature(hosts) != started {
			log.Print("the GpuHost fleet changed; stepping down to restart with it")
			changed()
			return
		}
	}
}

// labelNode sets the labels a GpuHost edit can change. virtual-kubelet applies
// labels only when it first creates a node; a missing node is created later
// with them.
func labelNode(ctx context.Context, client kubernetes.Interface, h host) error {
	var domain any
	if h.FaultDomain != "" {
		domain = h.FaultDomain
	}
	labels := map[string]any{
		"nvidia.com/gpu.product": h.GPUProduct,
		"nvidia.com/gpu.count":   fmt.Sprint(h.GPUCount),
		faultDomainLabel:         domain,
	}
	patch, err := json.Marshal(map[string]any{"metadata": map[string]any{"labels": labels}})
	if err != nil {
		return err
	}
	_, err = client.CoreV1().Nodes().Patch(ctx, "gpu-"+h.InstanceID, types.MergePatchType, patch, metav1.PatchOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

// startupPartKinds are the startup state the host agent reports per runtime.
// A kind added here becomes a gradiated.com/<kind>.<runtime> label.
var startupPartKinds = []string{"bundle", "weights"}

var startupLabel = regexp.MustCompile(`^gradiated\.com/(` + strings.Join(startupPartKinds, "|") + `)\.[0-9a-f]{16}$`)

// reconcileStartupLabels makes the node's gradiated.com/<kind>.<runtime>
// labels match the parts the host reports: it adds missing ones, removes ones
// no longer reported and leaves every other label alone. When the host cannot
// be read the labels stay as they are.
func reconcileStartupLabels(ctx context.Context, client kubernetes.Interface, name string, fetch func(context.Context) ([]string, error)) error {
	parts, err := fetch(ctx)
	if err != nil {
		return fmt.Errorf("read startup parts: %w", err)
	}
	node, err := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	if err != nil {
		return err
	}
	wanted := map[string]bool{}
	for _, part := range parts {
		if key := "gradiated.com/" + part; startupLabel.MatchString(key) {
			wanted[key] = true
		}
	}
	labels := map[string]any{}
	for key := range node.Labels {
		if startupLabel.MatchString(key) && !wanted[key] {
			labels[key] = nil
		}
	}
	for key := range wanted {
		if node.Labels[key] != "true" {
			labels[key] = "true"
		}
	}
	if len(labels) == 0 {
		return nil
	}
	patch, err := json.Marshal(map[string]any{"metadata": map[string]any{"labels": labels}})
	if err != nil {
		return err
	}
	_, err = client.CoreV1().Nodes().Patch(ctx, name, types.MergePatchType, patch, metav1.PatchOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

// reconcileStartupLabelsEvery corrects the startup labels now and then every
// interval, so a missed pass or a manual edit is fixed by the next one.
func reconcileStartupLabelsEvery(ctx context.Context, client kubernetes.Interface, name string, fetch func(context.Context) ([]string, error), every time.Duration) {
	for {
		if err := reconcileStartupLabels(ctx, client, name, fetch); err != nil && ctx.Err() == nil {
			log.Printf("startup labels of %s left unchanged: %v", name, err)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(every):
		}
	}
}
