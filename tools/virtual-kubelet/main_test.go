package main

import (
	"context"
	"testing"

	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

func smokePod() *v1.Pod {
	return &v1.Pod{ObjectMeta: metav1.ObjectMeta{Namespace: "vk-trial", Name: "smoke"}, Spec: v1.PodSpec{Containers: []v1.Container{{Name: "smoke", Image: "gradiated/vk-smoke:process-v1"}}}}
}

func TestRejectUnsupportedExecution(t *testing.T) {
	tests := map[string]func(*v1.Pod){
		"production namespace": func(p *v1.Pod) { p.Namespace = "gradiated" },
		"arbitrary image":      func(p *v1.Pod) { p.Spec.Containers[0].Image = "python:latest" },
		"arbitrary command":    func(p *v1.Pod) { p.Spec.Containers[0].Command = []string{"bash"} },
		"secret environment": func(p *v1.Pod) {
			p.Spec.Containers[0].EnvFrom = []v1.EnvFromSource{{SecretRef: &v1.SecretEnvSource{LocalObjectReference: v1.LocalObjectReference{Name: "secret"}}}}
		},
		"host networking": func(p *v1.Pod) { p.Spec.HostNetwork = true },
		"host storage":    func(p *v1.Pod) { p.Spec.Volumes = []v1.Volume{{Name: "host"}} },
		"GPU execution": func(p *v1.Pod) {
			p.Spec.Containers[0].Resources.Limits = v1.ResourceList{"nvidia.com/gpu": resource.MustParse("1")}
		},
	}
	if err := validate(smokePod()); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			p := smokePod()
			mutate(p)
			if validate(p) == nil {
				t.Fatal("unsupported workload accepted")
			}
		})
	}
}

func TestProviderReturnsIndependentPod(t *testing.T) {
	p := &provider{pods: map[string]*v1.Pod{"vk-trial/smoke": smokePod()}}
	pod, err := p.GetPod(context.Background(), "vk-trial", "smoke")
	if err != nil {
		t.Fatal(err)
	}
	pod.Spec.Containers[0].Image = "changed"
	original, _ := p.GetPod(context.Background(), "vk-trial", "smoke")
	if original.Spec.Containers[0].Image != "gradiated/vk-smoke:process-v1" {
		t.Fatal("caller mutated provider state")
	}
}

func TestGPUDiscoveryRequiresWholeMatchingResources(t *testing.T) {
	for _, count := range []string{"0", "1.5", "5"} {
		p := smokePod()
		p.Spec.Containers[0].Image = "gradiated/vk-gpu-smoke:process-v1"
		p.Spec.Containers[0].Resources = v1.ResourceRequirements{
			Limits:   v1.ResourceList{"nvidia.com/gpu": resource.MustParse(count)},
			Requests: v1.ResourceList{"nvidia.com/gpu": resource.MustParse(count)},
		}
		if validate(p) == nil {
			t.Fatalf("accepted invalid GPU count %s", count)
		}
	}
	p := smokePod()
	p.Spec.SecurityContext = &v1.PodSecurityContext{}
	p.Spec.Containers[0].Image = "gradiated/vk-gpu-smoke:process-v1"
	p.Spec.Containers[0].Resources = v1.ResourceRequirements{
		Limits:   v1.ResourceList{"nvidia.com/gpu": resource.MustParse("2")},
		Requests: v1.ResourceList{"nvidia.com/gpu": resource.MustParse("2")},
	}
	if err := validate(p); err != nil {
		t.Fatal(err)
	}
	p.Spec.Containers[0].Resources.Requests["nvidia.com/gpu"] = resource.MustParse("1")
	if validate(p) == nil {
		t.Fatal("accepted mismatched GPU resources")
	}
}
