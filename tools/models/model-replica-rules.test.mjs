import {test} from "node:test";import assert from "node:assert/strict";
import {modelReplicaRules} from "./model-replica-rules.mjs";
const rollout=(model,count)=>({kind:"Rollout",metadata:{name:"test"},spec:{replicas:count,template:{metadata:{annotations:{"gradiated.com/model-id":model}}}}});
test("desired counts come from Kubernetes Rollouts, including scale to zero",()=>{const result=modelReplicaRules([rollout("a/b",2),rollout("a/c",0),{kind:"Deployment"}]);assert.deepEqual(result.spec.groups[0].rules.filter(r=>r.record==="gradiated_model_desired_replicas").map(r=>r.expr),["vector(2)","vector(0)"]);});
test("invalid or duplicate desired state cannot erase or overwrite monitoring",()=>{for(const input of [[],[rollout("a/b",-1)],[rollout("a/b",1),rollout("a/b",2)],[rollout(undefined,1)]])assert.throws(()=>modelReplicaRules(input));});

test("autoscaled model monitoring follows the HPA instead of the bootstrap count",()=>{
 const scaler={kind:"ScaledObject",metadata:{name:"test",namespace:"gpu-inference"},spec:{scaleTargetRef:{kind:"Rollout",name:"test"}}};
 const result=modelReplicaRules([rollout("a/b",1),scaler]);
 assert.equal(result.spec.groups[0].rules.find(r=>r.record==="gradiated_model_minimum_replicas").expr,"vector(1)");
 assert.equal(result.spec.groups[0].rules[0].expr,'max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="gpu-inference",horizontalpodautoscaler="keda-hpa-test"}) or vector(1)');
});

test("paused KEDA replicas override bootstrap and HPA counts",()=>{
 const scaler={kind:"ScaledObject",metadata:{name:"test",namespace:"gpu-inference",annotations:{"autoscaling.keda.sh/paused-replicas":"0"}},spec:{scaleTargetRef:{kind:"Rollout",name:"test"}}};
 const rules=modelReplicaRules([rollout("a/b",2),scaler]).spec.groups[0].rules;
 assert.deepEqual(rules.map(rule=>rule.expr),["vector(0)","vector(0)"]);
 for(const paused of ["-1","1.5","NaN","",0,"9007199254740992"]){
  scaler.metadata.annotations["autoscaling.keda.sh/paused-replicas"]=paused;
  assert.throws(()=>modelReplicaRules([rollout("a/b",2),scaler]),/Invalid paused/);
 }
});
