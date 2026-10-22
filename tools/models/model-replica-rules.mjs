import {existsSync,readFileSync,readdirSync,writeFileSync} from "node:fs";
import {createRequire} from "node:module";
import {dirname,resolve} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=resolve(dirname(fileURLToPath(import.meta.url)),"../..");

const target=resolve(root,"infra/environments/prod/us-east-1/kubernetes/workloads/observability/model-replica-rules.yaml");
export const modelReplicaRules=(resources)=>{
 const rules=[];const models=new Set();
 const autoscalers=new Map(resources.filter(resource=>resource?.kind==="ScaledObject"&&resource.spec?.scaleTargetRef?.kind==="Rollout").map(resource=>[resource.spec.scaleTargetRef.name,resource]));
 for(const resource of resources){
  if(resource?.kind!=="Rollout")continue;
  const model=resource.spec?.template?.metadata?.annotations?.["gradiated.com/model-id"];
  const count=resource.spec?.replicas;
  if(typeof model!=="string"||!model||models.has(model)||!Number.isSafeInteger(count)||count<0)throw new Error("Rollout has invalid or duplicate model identity or replica count");
  const scaler=autoscalers.get(resource.metadata.name);
  const expr=scaler ? `max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="${scaler.metadata.namespace}",horizontalpodautoscaler="keda-hpa-${scaler.metadata.name}"}) or vector(${count})` : `vector(${count})`;
  models.add(model);rules.push({record:"gradiated_model_desired_replicas",expr,labels:{model,rollout:resource.metadata.name}},
  {record:"gradiated_model_minimum_replicas",expr:`vector(${count})`,labels:{model,rollout:resource.metadata.name}});
 }
 if(!rules.length)throw new Error("No model Rollouts found; refusing to erase desired replicas");
 return {apiVersion:"monitoring.coreos.com/v1",kind:"PrometheusRule",metadata:{name:"gradiated-model-replicas",labels:{release:"observability"},annotations:{"gradiated.com/generated-by":"node tools/models/model-replica-rules.mjs"}},spec:{groups:[{name:"gradiated.models.desired",rules}]}};
};
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
 const {parseAllDocuments}=createRequire(resolve(root,"product/package.json"))("yaml");
 // Each model is rendered into gpu-inference/models/<model>/<model>.yaml.
 const directory=resolve(root,"infra/environments/prod/us-east-1/kubernetes/gpu-inference/models");
 const resources=readdirSync(directory).sort().map(model=>resolve(directory,model,`${model}.yaml`)).filter(existsSync).flatMap(file=>parseAllDocuments(readFileSync(file,"utf8")).map(doc=>doc.toJS()));
 const content=JSON.stringify(modelReplicaRules(resources),null,2)+"\n";
 if(process.argv.includes("--check")){if(readFileSync(target,"utf8")!==content)throw new Error("Model replica rules are stale; run node tools/models/model-replica-rules.mjs");}
 else writeFileSync(target,content);
}
