package main

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	dynamicfake "k8s.io/client-go/dynamic/fake"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func TestStartupLabelsFollowTheHostAndLeaveOtherLabels(t *testing.T) {
	ctx := context.Background()
	rt, stale := strings.Repeat("a", 16), strings.Repeat("b", 16)
	others := map[string]string{"gradiated.com/fault-domain": "m1", "gradiated.com/kernels." + rt: "true", "example.com/bundle." + stale: "true"}
	initial := map[string]string{"gradiated.com/bundle." + stale: "true", "gradiated.com/weights." + rt: "true"}
	for key, value := range others {
		initial[key] = value
	}
	client := fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-x", Labels: initial}})
	labels := func() map[string]string {
		node, err := client.CoreV1().Nodes().Get(ctx, "gpu-x", metav1.GetOptions{})
		if err != nil {
			t.Fatal(err)
		}
		return node.Labels
	}
	reported := func(parts ...string) func(context.Context) ([]string, error) {
		return func(context.Context) ([]string, error) { return parts, nil }
	}

	if err := reconcileStartupLabels(ctx, client, "gpu-x", reported("bundle."+rt, "weights."+rt, "other."+rt, "bundle.XYZ")); err != nil {
		t.Fatal(err)
	}
	want := map[string]string{"gradiated.com/bundle." + rt: "true", "gradiated.com/weights." + rt: "true"}
	for key, value := range others {
		want[key] = value
	}
	if got := labels(); !reflect.DeepEqual(got, want) {
		t.Fatalf("labels = %v, want %v", got, want)
	}

	unreachable := func(context.Context) ([]string, error) { return nil, errors.New("host unreachable") }
	if err := reconcileStartupLabels(ctx, client, "gpu-x", unreachable); err == nil {
		t.Fatal("a failed read was not reported")
	}
	if got := labels(); !reflect.DeepEqual(got, want) {
		t.Fatalf("a failed read changed the labels to %v", got)
	}

	if err := reconcileStartupLabels(ctx, client, "gpu-x", reported()); err != nil {
		t.Fatal(err)
	}
	if got := labels(); !reflect.DeepEqual(got, others) {
		t.Fatalf("labels = %v, want %v", got, others)
	}
	if err := reconcileStartupLabels(ctx, client, "gpu-missing", reported()); err != nil {
		t.Fatalf("a missing node is not an error: %v", err)
	}
}

func gpuHostObject(id string, gpus int64) *unstructured.Unstructured {
	return &unstructured.Unstructured{Object: map[string]any{
		"apiVersion": "fleet.gradiated.com/v1alpha1",
		"kind":       "GpuHost",
		"metadata":   map[string]any{"name": "gpu-" + id},
		"spec": map[string]any{
			"instanceId": id,
			"provider":   map[string]any{"name": "runpod", "accountId": "user_test", "podId": "pod" + id[:4], "machineId": "machine" + id[:4]},
			"inventory":  map[string]any{"gpuProduct": "B300", "gpuCount": gpus, "cpu": int64(64), "memoryGiB": int64(896)},
			"managementSecret": map[string]any{
				"key": "gradiated/prod/platform/gpu-host/" + id,
			},
		},
	}}
}

func fleetClient(objects ...runtime.Object) *dynamicfake.FakeDynamicClient {
	return dynamicfake.NewSimpleDynamicClientWithCustomListKinds(runtime.NewScheme(),
		map[schema.GroupVersionResource]string{gpuHosts: "GpuHostList"}, objects...)
}

const (
	first  = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4"
	second = "01a0fbf7-5276-700b-903b-7e04da150ed6"
)

func TestControllerReadsTheFleetFromGpuHosts(t *testing.T) {
	hosts, err := listHosts(context.Background(), fleetClient(gpuHostObject(second, 8), gpuHostObject(first, 4)))
	if err != nil || len(hosts) != 2 || hosts[0].InstanceID != first || hosts[1].InstanceID != second {
		t.Fatalf("hosts = %+v, err %v", hosts, err)
	}
	want := host{InstanceID: first, Provider: "runpod", Endpoint: "http://gpu-" + first + ".tailscale-inference.svc.cluster.local:8888/_kubelet",
		TokenFile: "/var/run/gradiated-host-keys/" + first, GPUCount: 4, CPU: 64, MemoryGiB: 896, GPUProduct: "B300",
		FaultDomain: "machine01a0"}
	if hostsSignature(hosts[:1]) != hostsSignature([]host{want}) {
		t.Fatalf("host = %+v, want %+v", hosts[0], want)
	}
}

func awsHostObject(id string) *unstructured.Unstructured {
	object := gpuHostObject(id, 1)
	spec := object.Object["spec"].(map[string]any)
	spec["provider"] = map[string]any{"name": "aws", "accountId": "111122223333", "region": "us-east-1",
		"availabilityZone": "us-east-1b", "ec2InstanceId": "i-0123456789abcdef0"}
	spec["inventory"] = map[string]any{"gpuProduct": "L4", "gpuCount": int64(1), "cpu": int64(3), "memoryGiB": int64(12)}
	return object
}

func TestAnAwsHostIsLabelledWithItsProviderAndZone(t *testing.T) {
	hosts, err := listHosts(context.Background(), fleetClient(awsHostObject(second), gpuHostObject(first, 4)))
	if err != nil || len(hosts) != 2 {
		t.Fatalf("hosts = %+v, err %v", hosts, err)
	}
	if hosts[0].Provider != "runpod" || hosts[0].FaultDomain != "machine01a0" {
		t.Fatalf("runpod host = %+v", hosts[0])
	}
	aws := hosts[1]
	if aws.Provider != "aws" || aws.FaultDomain != "us-east-1b" || aws.GPUProduct != "L4" {
		t.Fatalf("aws host = %+v", aws)
	}
	labels := nodeLabels(aws)
	want := map[string]string{"type": "virtual-kubelet", "kubernetes.io/hostname": "gpu-" + second,
		"gradiated.com/provider": "aws", "gradiated.com/instance-id": second, "nvidia.com/gpu.product": "L4",
		"nvidia.com/gpu.count": "1", "gradiated.com/fault-domain": "us-east-1b"}
	if !reflect.DeepEqual(labels, want) {
		t.Fatalf("labels = %v, want %v", labels, want)
	}
	if got := nodeLabels(hosts[0])["gradiated.com/provider"]; got != "runpod" {
		t.Fatalf("runpod provider label = %q", got)
	}
}

func TestAnInvalidGpuHostIsSkippedNotTheWholeFleet(t *testing.T) {
	misnamed := gpuHostObject(first, 4)
	misnamed.SetName("gpu-other")
	unknown := gpuHostObject(first, 4)
	unknown.Object["spec"].(map[string]any)["provider"].(map[string]any)["name"] = "elsewhere"
	for name, object := range map[string]*unstructured.Unstructured{
		"misnamed":         misnamed,
		"too many GPU":     gpuHostObject(first, 9),
		"no GPUs":          gpuHostObject(first, 0),
		"unknown provider": unknown,
	} {
		hosts, err := listHosts(context.Background(), fleetClient(object, gpuHostObject(second, 8)))
		if err != nil || len(hosts) != 1 || hosts[0].InstanceID != second {
			t.Fatalf("%s: hosts = %+v, err %v", name, hosts, err)
		}
	}
}

func TestAFleetThatCannotBeListedIsAnErrorNotAnEmptyFleet(t *testing.T) {
	client := fleetClient(gpuHostObject(first, 4))
	client.PrependReactor("list", "gpuhosts", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, errors.New("the API server is unavailable")
	})
	hosts, err := listHosts(context.Background(), client)
	if err == nil || hosts != nil {
		t.Fatalf("hosts = %+v, err %v; a list error must not read as an empty fleet", hosts, err)
	}
}

func TestLeaderStepsDownOnlyWhenTheFleetChanges(t *testing.T) {
	client := fleetClient(gpuHostObject(first, 4))
	current, _ := listHosts(context.Background(), client)
	ctx, stop := context.WithCancel(context.Background())
	defer stop()
	var changed atomic.Int32
	done := make(chan struct{})
	go func() {
		watchHosts(ctx, client, current, 5*time.Millisecond, func() { changed.Add(1) })
		close(done)
	}()
	time.Sleep(50 * time.Millisecond)
	if changed.Load() != 0 {
		t.Fatal("the leader stepped down without a fleet change")
	}
	if _, err := client.Resource(gpuHosts).Update(ctx, gpuHostObject(first, 2), metav1.UpdateOptions{}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("the leader did not step down after a GpuHost changed")
	}
	if changed.Load() != 1 {
		t.Fatalf("changed called %d times", changed.Load())
	}
}

func TestALeaderWithAnEmptyFleetStepsDownWhenHostsAppear(t *testing.T) {
	client := fleetClient()
	hosts, err := listHosts(context.Background(), client)
	if err != nil || len(hosts) != 0 {
		t.Fatalf("hosts = %+v, err %v", hosts, err)
	}
	ctx, stop := context.WithCancel(context.Background())
	defer stop()
	done := make(chan struct{})
	go func() {
		watchHosts(ctx, client, hosts, 5*time.Millisecond, func() {})
		close(done)
	}()
	if _, err := client.Resource(gpuHosts).Create(ctx, gpuHostObject(first, 4), metav1.CreateOptions{}); err != nil {
		t.Fatal(err)
	}
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("the leader kept an empty fleet after GpuHosts appeared")
	}
}

func TestInventoryAndFaultDomainLabelsFollowTheGpuHostOnAnExistingNode(t *testing.T) {
	name := "gpu-" + first
	client := fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: name, Labels: map[string]string{
		"type": "virtual-kubelet", "nvidia.com/gpu.product": "RTX-PRO-6000", "nvidia.com/gpu.count": "1"}}})
	ctx := context.Background()
	h := host{InstanceID: first, GPUProduct: "B300", GPUCount: 4, FaultDomain: "uyx8qy1ypzwg"}
	if err := labelNode(ctx, client, h); err != nil {
		t.Fatal(err)
	}
	node, _ := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	want := map[string]string{"type": "virtual-kubelet", "nvidia.com/gpu.product": "B300", "nvidia.com/gpu.count": "4", faultDomainLabel: "uyx8qy1ypzwg"}
	for key, value := range want {
		if node.Labels[key] != value {
			t.Fatalf("labels = %v, want %v", node.Labels, want)
		}
	}
	h.FaultDomain = ""
	if err := labelNode(ctx, client, h); err != nil {
		t.Fatal(err)
	}
	node, _ = client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	if _, present := node.Labels[faultDomainLabel]; present {
		t.Fatalf("labels = %v", node.Labels)
	}
	if err := labelNode(ctx, client, host{InstanceID: second, GPUProduct: "B300", GPUCount: 8}); err != nil {
		t.Fatalf("a node not created yet must not fail: %v", err)
	}
}
