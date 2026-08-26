use chrono::{DateTime, Utc};
use serde::Serialize;

use crate::{
    domain::ModelStatus, GatewayModel, InputTokenPrice, ModelParameterDescriptor,
    ModelQuantization, OutputTokenPrice, SupportedTextInputs, TextInputModality,
    TextOutputModality, TokenMeasure, TokenUnit,
};

const PROVIDER_SCHEMA_VERSION: &str = "2.4";
const NANO_USD_SCALE: u64 = 1_000_000_000;
const PROVIDER_DATACENTER_COUNTRY: &str = "US";
const PROVIDER_DATACENTER_REGION: &str = "us-east-1";
const PROVIDER_DEPLOYMENT_REGION: &str = "US";
const PROVIDER_ZDR: bool = true;
const PROVIDER_HIPAA: bool = false;

#[derive(Debug, Serialize)]
pub struct ModelCatalogResponse<'a> {
    data: Vec<ProviderModel<'a>>,
}

impl<'a> ModelCatalogResponse<'a> {
    pub fn from_models(models: &'a [GatewayModel]) -> Self {
        Self {
            data: models
                .iter()
                .filter_map(ProviderModel::from_model)
                .collect(),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderModel<'a> {
    schema_version: &'static str,
    id: &'a str,
    name: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    hugging_face_id: Option<&'a str>,
    created: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    quantization: Option<ModelQuantization>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tokenizer: Option<&'a str>,
    description: &'a str,
    input_modalities: [ProviderTextInput<'a>; 1],
    output_modalities: [ProviderTextOutput; 1],
    #[serde(skip_serializing_if = "std::collections::HashMap::is_empty")]
    passthrough_parameters: &'a std::collections::HashMap<String, ModelParameterDescriptor>,
    #[serde(skip_serializing_if = "Option::is_none")]
    deprecation_date: Option<&'a DateTime<Utc>>,
    is_ready: bool,
    datacenters: [ProviderDatacenter; 1],
    deployment_region: &'static str,
    compliance: ProviderCompliance,
}

impl<'a> ProviderModel<'a> {
    fn from_model(model: &'a GatewayModel) -> Option<Self> {
        let is_ready = match model.status {
            ModelStatus::Available => true,
            ModelStatus::Unavailable => false,
            ModelStatus::Retired => return None,
        };
        if !model
            .deployments
            .iter()
            .any(|deployment| deployment.validate().is_ok())
        {
            return None;
        }
        if is_ready && model.first_available_deployment().ok().flatten().is_none() {
            return None;
        }

        let released_at = model.properties.released_at.as_ref()?;
        let input = model.properties.text_input();
        let output = model.properties.text_output();
        Some(Self {
            schema_version: PROVIDER_SCHEMA_VERSION,
            id: &model.id,
            name: &model.name,
            hugging_face_id: model.properties.hugging_face_id.as_deref(),
            created: released_at.timestamp(),
            quantization: model.properties.quantization,
            tokenizer: model.properties.tokenizer.as_deref(),
            description: &model.properties.description,
            input_modalities: [ProviderTextInput::from_model(input)],
            output_modalities: [ProviderTextOutput::from_model(output)],
            passthrough_parameters: &model.properties.passthrough_parameters,
            deprecation_date: model.properties.deprecation_date.as_ref(),
            is_ready,
            datacenters: [ProviderDatacenter {
                country_code: PROVIDER_DATACENTER_COUNTRY,
                region: PROVIDER_DATACENTER_REGION,
            }],
            deployment_region: PROVIDER_DEPLOYMENT_REGION,
            compliance: ProviderCompliance {
                zdr: PROVIDER_ZDR,
                hipaa: PROVIDER_HIPAA,
            },
        })
    }
}

#[derive(Debug, Serialize)]
struct ProviderCompliance {
    zdr: bool,
    hipaa: bool,
}

#[derive(Debug, Serialize)]
struct ProviderTextInput<'a> {
    #[serde(rename = "type")]
    kind: &'static str,
    supported_inputs: &'a SupportedTextInputs,
    pricing: Vec<ProviderInputPrice>,
}

impl<'a> ProviderTextInput<'a> {
    fn from_model(input: &'a TextInputModality) -> Self {
        Self {
            kind: "text",
            supported_inputs: &input.supported_inputs,
            pricing: input.pricing.iter().map(ProviderInputPrice::from).collect(),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderTextOutput {
    #[serde(rename = "type")]
    kind: &'static str,
    max_length: TokenMeasure,
    streaming: bool,
    supported_parameters: std::collections::HashMap<String, ModelParameterDescriptor>,
    pricing: Vec<ProviderOutputPrice>,
}

impl ProviderTextOutput {
    fn from_model(output: &TextOutputModality) -> Self {
        let mut supported_parameters = output.supported_parameters.clone();
        supported_parameters.insert(
            "max_tokens".to_owned(),
            ModelParameterDescriptor::Integer {
                min: 1,
                max: output.max_length.value as i64,
                unit: Some(TokenUnit::Token),
            },
        );
        Self {
            kind: "text",
            max_length: output.max_length.clone(),
            streaming: output.streaming,
            supported_parameters,
            pricing: output
                .pricing
                .iter()
                .map(ProviderOutputPrice::from)
                .collect(),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderInputPrice {
    #[serde(rename = "type")]
    kind: &'static str,
    unit: &'static str,
    cost_usd: String,
}

impl From<&InputTokenPrice> for ProviderInputPrice {
    fn from(price: &InputTokenPrice) -> Self {
        let kind = match price {
            InputTokenPrice::Prompt { .. } => "prompt",
            InputTokenPrice::CachedPrompt { .. } => "cached_prompt",
            InputTokenPrice::CacheWrite { .. } => "cache_write",
        };
        Self {
            kind,
            unit: "token",
            cost_usd: nano_usd(price.cost()),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderOutputPrice {
    #[serde(rename = "type")]
    kind: &'static str,
    unit: &'static str,
    cost_usd: String,
}

impl From<&OutputTokenPrice> for ProviderOutputPrice {
    fn from(price: &OutputTokenPrice) -> Self {
        let kind = match price {
            OutputTokenPrice::Completion { .. } => "completion",
            OutputTokenPrice::InternalReasoning { .. } => "internal_reasoning",
        };
        Self {
            kind,
            unit: "token",
            cost_usd: nano_usd(price.cost()),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderDatacenter {
    country_code: &'static str,
    region: &'static str,
}

fn nano_usd(value: u64) -> String {
    let whole = value / NANO_USD_SCALE;
    let fractional = value % NANO_USD_SCALE;
    if fractional == 0 {
        return whole.to_string();
    }
    let fractional = format!("{fractional:09}").trim_end_matches('0').to_owned();
    format!("{whole}.{fractional}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn model() -> GatewayModel {
        serde_json::from_value(serde_json::json!({
            "id": "provider/model-a",
            "name": "Model A",
            "status": "available",
            "properties": {
                "schema_version": 1,
                "description": "Model A",
                "released_at": "2026-01-02T03:04:05Z",
                "hugging_face_id": "provider/model-a",
                "quantization": "fp8",
                "tokenizer": "ModelA",
                "input_modalities": [{
                    "type": "text",
                    "supported_inputs": {
                        "max_context_length": {"value": 8192, "unit": "token"},
                        "max_prompt_length": {"value": 7168, "unit": "token"}
                    },
                    "pricing": [
                        {"type": "prompt", "unit": "token", "cost": 1000},
                        {"type": "cached_prompt", "unit": "token", "cost": 500}
                    ]
                }],
                "output_modalities": [{
                    "type": "text",
                    "max_length": {"value": 1024, "unit": "token"},
                    "default_length": {"value": 512, "unit": "token"},
                    "streaming": true,
                    "supported_parameters": {
                        "temperature": {"type": "range", "min": 0, "max": 2}
                    },
                    "pricing": [
                        {"type": "completion", "unit": "token", "cost": 2000}
                    ]
                }],
                "passthrough_parameters": {
                    "response_format": {"type": "unknown"}
                },
                "deprecation_date": null
            },
            "deployments": [{
                "id": "0198c36f-9b6a-7000-8000-000000000005",
                "status": "available",
                "service_url": "http://private-sglang:30000",
                "release": {
                    "schema_version": 1,
                    "runtime_revision": "runtime",
                    "model_path": "model",
                    "model_revision": "model-revision",
                    "tokenizer_path": "tokenizer",
                    "tokenizer_revision": "tokenizer-revision"
                }
            }]
        }))
        .unwrap()
    }

    #[test]
    fn converts_nano_usd_without_floating_point() {
        assert_eq!(nano_usd(0), "0");
        assert_eq!(nano_usd(1), "0.000000001");
        assert_eq!(nano_usd(1_000), "0.000001");
        assert_eq!(nano_usd(1_500_000_000), "1.5");
    }

    #[test]
    fn publishes_only_customer_visible_provider_fields() {
        let models = [model()];
        let response = serde_json::to_value(ModelCatalogResponse::from_models(&models)).unwrap();
        let published = &response["data"][0];

        assert_eq!(published["id"], "provider/model-a");
        assert_eq!(published["input_modalities"][0]["type"], "text");
        assert_eq!(
            published["input_modalities"][0]["supported_inputs"]["max_context_length"]["value"],
            8192
        );
        assert_eq!(
            published["input_modalities"][0]["pricing"][0]["cost_usd"],
            "0.000001"
        );
        assert_eq!(
            published["output_modalities"][0]["pricing"][0]["cost_usd"],
            "0.000002"
        );
        assert_eq!(
            published["output_modalities"][0]["supported_parameters"]["max_tokens"]["max"],
            1024
        );
        assert_eq!(
            published["datacenters"],
            serde_json::json!([{ "country_code": "US", "region": "us-east-1" }])
        );
        assert_eq!(published["deployment_region"], "US");
        assert_eq!(
            published["compliance"],
            serde_json::json!({ "zdr": true, "hipaa": false })
        );
        assert_eq!(published["is_ready"], true);
        assert_eq!(published["schema_version"], "2.4");
        assert!(published.get("capacity").is_none());
        assert!(published.get("deployments").is_none());
        assert!(published.get("service_url").is_none());
    }

    #[test]
    fn excludes_models_that_cannot_be_advertised() {
        let mut retired = model();
        retired.status = ModelStatus::Retired;
        let mut missing_release = model();
        missing_release.properties.released_at = None;
        let mut missing_deployment = model();
        missing_deployment.deployments.clear();

        for model in [retired, missing_release, missing_deployment] {
            let models = [model];
            let response =
                serde_json::to_value(ModelCatalogResponse::from_models(&models)).unwrap();
            assert_eq!(response["data"].as_array().unwrap().len(), 0);
        }
    }
}
