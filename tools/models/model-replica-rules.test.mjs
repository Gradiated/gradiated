import {test} from "node:test";import assert from "node:assert/strict";
import {modelReplicaRules} from "./model-replica-rules.mjs";
const rollout=(model,count)=>({kind:"Rollout",metadata:{name:"test"},spec:{replicas:count,template:{metadata:{annotations:{"gradiated.com/model-id":model}}}}});
test("desired counts come from Kubernetes Rollouts, including scale to zero",()=>{const result=modelReplicaRules([rollout("a/b",2),rollout("a/c",0),{kind:"Deployment"}]);assert.deepEqual(result.spec.groups[0].rules.map(r=>r.expr),["vector(2)","vector(0)"]);});
test("invalid or duplicate desired state cannot erase or overwrite monitoring",()=>{for(const input of [[],[rollout("a/b",-1)],[rollout("a/b",1),rollout("a/b",2)],[rollout(undefined,1)]])assert.throws(()=>modelReplicaRules(input));});

test("autoscaled model monitoring follows the HPA instead of the bootstrap count",()=>{
 const scaler={kind:"ScaledObject",metadata:{name:"test",namespace:"gpu-inference"},spec:{scaleTargetRef:{kind:"Rollout",name:"test"}}};
 const result=modelReplicaRules([rollout("a/b",1),scaler]);
 assert.equal(result.spec.groups[0].rules[0].expr,'max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="gpu-inference",horizontalpodautoscaler="keda-hpa-test"}) or vector(1)');
});
