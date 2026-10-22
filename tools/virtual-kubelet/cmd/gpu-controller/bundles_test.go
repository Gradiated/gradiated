package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
)

func withBundle(id string, bundle map[string]any) *unstructured.Unstructured {
	object := gpuHostObject(id, 4)
	object.Object["status"] = map[string]any{"rollout": map[string]any{"bundle": bundle}}
	return object
}

// configured runs configureHost against a host agent that records the request.
func configured(t *testing.T, objects ...runtime.Object) map[string]any {
	t.Helper()
	var body map[string]any
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		_, _ = w.Write([]byte(`{}`))
	})
	p.host.InstanceID = first
	p.host.Runtimes = json.RawMessage(`{"kev":{}}`)
	p.term = "term"
	if err := configureHost(context.Background(), fleetClient(objects...), p); err != nil {
		t.Fatal(err)
	}
	return body
}

func TestConfigureAppliesTheBundleTheOperatorChose(t *testing.T) {
	body := configured(t, withBundle(first, map[string]any{"sha256": strings.Repeat("b", 64), "baseId": "ubuntu24-cuda13-amd64-v3"}))
	if body["operation"] != "configure" || body["epoch"] != float64(7) || body["term"] != "term" {
		t.Fatalf("body = %+v", body)
	}
	bundle, _ := body["host_bundle"].(map[string]any)
	if bundle["sha256"] != strings.Repeat("b", 64) || bundle["base_id"] != "ubuntu24-cuda13-amd64-v3" {
		t.Fatalf("host_bundle = %+v", body["host_bundle"])
	}
	if _, ok := body["runtimes"].(map[string]any)["kev"]; !ok {
		t.Fatalf("runtimes = %+v", body["runtimes"])
	}
}

func TestConfigureKeepsTheRunningBundleWithoutAValidTarget(t *testing.T) {
	for name, objects := range map[string][]runtime.Object{
		"no rollout":     {gpuHostObject(first, 4)},
		"invalid bundle": {withBundle(first, map[string]any{"sha256": "../x", "baseId": "v3"})},
		"no GpuHost":     nil,
	} {
		t.Run(name, func(t *testing.T) {
			body := configured(t, objects...)
			if _, sent := body["host_bundle"]; sent || body["operation"] != "configure" {
				t.Fatalf("body = %+v", body)
			}
		})
	}
}
