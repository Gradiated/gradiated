use std::collections::HashMap;

use chrono::{DateTime, Utc};
use serde::Serialize;

use crate::{
    model::{ModelStatus, TextModalityKind},
    DeploymentStatus, GatewayModel, InputPriceType, ModelParameterDescriptor, ModelQuantization,
    OutputPriceType, SupportedTextInputs, TextInputModality, TextOutputModality, TokenMeasure,
    TokenUnit,
};

const PROVIDER_SCHEMA_VERSION: &str = "2.4";
const NANO_USD_SCALE: u64 = 1_000_000_000;

#[derive(Debug)]
pub struct CatalogModel {
    pub model: GatewayModel,
    pub healthy_deployments: u64,
    pub external_capacity: bool,
}

#[derive(Debug, Serialize)]
pub struct ModelCatalogResponse<'a> {
    data: Vec<ProviderModel<'a>>,
    models: Vec<TypeSafeModelCard<'a>>,
}

impl<'a> ModelCatalogResponse<'a> {
    pub fn from_models(models: &'a [CatalogModel], compliance: ProviderCompliance) -> Self {
        let data = models
            .iter()
            .filter_map(|model| ProviderModel::from_model(model, compliance))
            .collect::<Vec<_>>();
        let models = data.iter().map(TypeSafeModelCard::from_listed).collect();

        Self { data, models }
    }
}

/// `name` is the model ID a request sends, not the display name.
#[derive(Debug, Serialize)]
struct TypeSafeModelCard<'a> {
    name: &'a str,
    description: &'a str,
    release_date: String,
}

impl<'a> TypeSafeModelCard<'a> {
    fn from_listed(model: &ProviderModel<'a>) -> Self {
        Self {
            name: model.id,
            description: model.description,
            release_date: model.released_at.format("%Y-%m-%d").to_string(),
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
    #[serde(skip)]
    released_at: &'a DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    quantization: Option<ModelQuantization>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tokenizer: Option<&'a str>,
    description: &'a str,
    input_modalities: [ProviderTextInput<'a>; 1],
    output_modalities: [ProviderTextOutput; 1],
    #[serde(skip_serializing_if = "HashMap::is_empty")]
    passthrough_parameters: &'a HashMap<String, ModelParameterDescriptor>,
    #[serde(skip_serializing_if = "Option::is_none")]
    deprecation_date: Option<&'a DateTime<Utc>>,
    is_ready: bool,
    datacenters: Vec<ProviderDatacenter<'a>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    deployment_region: Option<&'static str>,
    compliance: ProviderCompliance,
}

impl<'a> ProviderModel<'a> {
    fn from_model(catalog: &'a CatalogModel, compliance: ProviderCompliance) -> Option<Self> {
        let model = &catalog.model;
        let properties = &model.properties;
        let released_at = properties.released_at.as_ref()?;
        let is_ready = match model.status {
            ModelStatus::Available => catalog.healthy_deployments > 0 || catalog.external_capacity,
            ModelStatus::Unavailable => false,
            ModelStatus::Retired => return None,
        };

        let valid_deployments = model
            .deployments
            .iter()
            .filter(|deployment| deployment.validate().is_ok())
            .collect::<Vec<_>>();

        if valid_deployments.is_empty() && !catalog.external_capacity {
            return None;
        }

        let mut regions = valid_deployments
            .into_iter()
            .filter(|deployment| deployment.status == DeploymentStatus::Available)
            .map(|deployment| deployment.region.as_str())
            .collect::<Vec<_>>();
        regions.sort_unstable();
        regions.dedup();
        let datacenters = regions
            .into_iter()
            .map(|region| ProviderDatacenter {
                country_code: country_code(region),
                region,
            })
            .collect::<Vec<_>>();
        // Another provider may serve the request, so no residency can be promised.
        let deployment_region = if catalog.external_capacity {
            None
        } else {
            single_country(&datacenters)
        };

        Some(Self {
            schema_version: PROVIDER_SCHEMA_VERSION,
            id: &model.id,
            name: &model.name,
            hugging_face_id: properties.hugging_face_id.as_deref(),
            created: released_at.timestamp(),
            released_at,
            quantization: properties.quantization,
            tokenizer: properties.tokenizer.as_deref(),
            description: &properties.description,
            input_modalities: [ProviderTextInput::from_model(properties.text_input())],
            output_modalities: [ProviderTextOutput::from_model(properties.text_output())?],
            passthrough_parameters: &properties.passthrough_parameters,
            deprecation_date: properties.deprecation_date.as_ref(),
            is_ready,
            datacenters,
            deployment_region,
            compliance,
        })
    }
}

/// What the gateway publishes about itself. These are claims customers encode into
/// their own compliance decisions, so they are configuration rather than constants
/// compiled into the binary, and they are not per-model facts today.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub struct ProviderCompliance {
    pub zdr: bool,
    pub hipaa: bool,
}

#[derive(Debug, Serialize)]
struct ProviderTextInput<'a> {
    #[serde(rename = "type")]
    kind: TextModalityKind,
    supported_inputs: &'a SupportedTextInputs,
    pricing: Vec<ProviderPrice<InputPriceType>>,
}

impl<'a> ProviderTextInput<'a> {
    fn from_model(input: &'a TextInputModality) -> Self {
        Self {
            kind: input.kind,
            supported_inputs: &input.supported_inputs,
            pricing: input
                .pricing
                .iter()
                .map(|price| ProviderPrice::per_token(price.kind(), price.cost()))
                .collect(),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderTextOutput {
    #[serde(rename = "type")]
    kind: TextModalityKind,
    max_length: TokenMeasure,
    streaming: bool,
    supported_parameters: HashMap<String, ModelParameterDescriptor>,
    pricing: Vec<ProviderPrice<OutputPriceType>>,
}

impl ProviderTextOutput {
    fn from_model(output: &TextOutputModality) -> Option<Self> {
        let max_tokens = i64::try_from(output.max_length.value).ok()?;

        let mut supported_parameters = output.supported_parameters.clone();
        supported_parameters.insert(
            "max_tokens".to_owned(),
            ModelParameterDescriptor::Integer {
                min: 1,
                max: max_tokens,
                unit: Some(TokenUnit::Token),
            },
        );

        Some(Self {
            kind: output.kind,
            max_length: output.max_length.clone(),
            streaming: output.streaming,
            supported_parameters,
            pricing: output
                .pricing
                .iter()
                .map(|price| ProviderPrice::per_token(price.kind(), price.cost()))
                .collect(),
        })
    }
}

#[derive(Debug, Serialize)]
struct ProviderPrice<K> {
    #[serde(rename = "type")]
    kind: K,
    unit: TokenUnit,
    cost_usd: String,
}

impl<K> ProviderPrice<K> {
    fn per_token(kind: K, cost: u64) -> Self {
        Self {
            kind,
            unit: TokenUnit::Token,
            cost_usd: nano_usd(cost),
        }
    }
}

#[derive(Debug, Serialize)]
struct ProviderDatacenter<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    country_code: Option<&'static str>,
    region: &'a str,
}

/// Region to ISO 3166-1 alpha-2 country. A region this does not name has its
/// country omitted rather than guessed: publishing the wrong data residency is
/// worse than publishing none, and customers encode this field into their own
/// compliance logic.
fn country_code(region: &str) -> Option<&'static str> {
    let country = match region {
        "af-south-1" => "ZA",
        "ap-northeast-1" => "JP",
        "ap-northeast-2" => "KR",
        "ap-south-1" => "IN",
        "ap-southeast-1" | "sg" => "SG",
        "ap-southeast-2" => "AU",
        "ca-central-1" | "ca" => "CA",
        "eu-central-1" => "DE",
        "eu-north-1" => "SE",
        "eu-west-1" => "IE",
        "eu-west-2" => "GB",
        "eu-west-3" => "FR",
        "sa-east-1" => "BR",
        "us-east-1" | "us-east-2" | "us-west-1" | "us-west-2" | "us" => "US",
        _ => return None,
    };

    Some(country)
}

/// A model is published as resident in a country only when every datacenter that
/// can serve it is known to be in that country.
fn single_country(datacenters: &[ProviderDatacenter<'_>]) -> Option<&'static str> {
    let (first, rest) = datacenters.split_first()?;
    let country = first.country_code?;

    rest.iter()
        .all(|entry| entry.country_code == Some(country))
        .then_some(country)
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
    use chrono::TimeZone;
    use serde_json::{json, Value};

    use super::*;
    use crate::{test_support, GatewayModelDeployment, InputTokenPrice, OutputTokenPrice};

    fn model() -> GatewayModel {
        let mut model = test_support::model(true);
        model.properties.released_at = Some(Utc.with_ymd_and_hms(2026, 1, 2, 3, 4, 5).unwrap());
        model.deployments[0].region = "us-east-1".to_owned();

        model
    }

    fn with_deployments(regions: &[(&str, DeploymentStatus)]) -> GatewayModel {
        let mut model = model();
        let template = model.deployments[0].clone();
        model.deployments = regions
            .iter()
            .map(|(region, status)| GatewayModelDeployment {
                region: (*region).to_owned(),
                status: *status,
                ..template.clone()
            })
            .collect();

        model
    }

    fn publish(model: GatewayModel, healthy_deployments: u64) -> Option<Value> {
        let models = [CatalogModel {
            model,
            healthy_deployments,
            external_capacity: false,
        }];
        let compliance = ProviderCompliance {
            zdr: true,
            hipaa: false,
        };
        let response =
            serde_json::to_value(ModelCatalogResponse::from_models(&models, compliance)).unwrap();
        let ids = |list: &str, field: &str| {
            response[list]
                .as_array()
                .unwrap()
                .iter()
                .map(|model| model[field].clone())
                .collect::<Vec<_>>()
        };
        assert_eq!(ids("models", "name"), ids("data", "id"));

        response["data"].as_array().unwrap().first().cloned()
    }

    #[test]
    fn publishes_a_typesafe_model_card_beside_the_provider_catalog() {
        let models = [CatalogModel {
            model: model(),
            healthy_deployments: 1,
            external_capacity: false,
        }];
        let compliance = ProviderCompliance {
            zdr: true,
            hipaa: false,
        };
        let response =
            serde_json::to_value(ModelCatalogResponse::from_models(&models, compliance)).unwrap();

        assert_eq!(
            response["models"],
            json!([{
                "name": "model-a",
                "description": models[0].model.properties.description,
                "release_date": "2026-01-02"
            }])
        );
        assert_eq!(response.as_object().unwrap().len(), 2);
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
        let published = publish(model(), 2).expect("the model is published");

        assert_eq!(published["id"], "model-a");
        assert_eq!(published["created"], 1_767_323_045);
        assert_eq!(published["input_modalities"][0]["type"], "text");
        assert_eq!(
            published["input_modalities"][0]["supported_inputs"]["max_context_length"]["value"],
            8192
        );
        assert_eq!(
            published["input_modalities"][0]["pricing"],
            json!([
                { "type": "prompt", "unit": "token", "cost_usd": "0.0000001" },
                { "type": "cached_prompt", "unit": "token", "cost_usd": "0.00000005" }
            ])
        );
        assert_eq!(
            published["output_modalities"][0]["pricing"],
            json!([{ "type": "completion", "unit": "token", "cost_usd": "0.0000002" }])
        );
        assert_eq!(
            published["output_modalities"][0]["supported_parameters"]["max_tokens"],
            json!({ "type": "integer", "min": 1, "max": 4096, "unit": "token" })
        );
        assert_eq!(
            published["datacenters"],
            json!([{ "country_code": "US", "region": "us-east-1" }])
        );
        assert_eq!(published["deployment_region"], "US");
        assert_eq!(
            published["compliance"],
            json!({ "zdr": true, "hipaa": false })
        );
        assert_eq!(published["is_ready"], true);
        assert!(published.get("capacity").is_none());
        assert_eq!(published["schema_version"], "2.4");
        assert!(published.get("deployments").is_none());
        assert!(published.get("service_url").is_none());
    }

    #[test]
    fn optional_fields_without_a_value_are_left_out() {
        let mut model = model();
        model.properties.passthrough_parameters.clear();
        let published = publish(model, 1).expect("the model is published");

        for field in [
            "hugging_face_id",
            "quantization",
            "tokenizer",
            "deprecation_date",
            "passthrough_parameters",
        ] {
            assert!(published.get(field).is_none(), "{field}");
        }
    }

    #[test]
    fn a_declared_max_tokens_parameter_is_replaced_with_the_model_maximum() {
        let mut model = model();
        model.properties.output_modalities[0]
            .supported_parameters
            .insert("max_tokens".to_owned(), ModelParameterDescriptor::Boolean);
        let published = publish(model, 1).expect("the model is published");

        assert_eq!(
            published["output_modalities"][0]["supported_parameters"]["max_tokens"]["max"],
            4096
        );
    }

    #[test]
    fn optional_prices_are_published() {
        let mut model = model();
        let properties = &mut model.properties;
        properties.input_modalities[0]
            .pricing
            .push(InputTokenPrice::CacheWrite {
                unit: TokenUnit::Token,
                cost: 125,
            });
        properties.output_modalities[0]
            .pricing
            .push(OutputTokenPrice::InternalReasoning {
                unit: TokenUnit::Token,
                cost: 1_500_000_000,
            });
        let published = publish(model, 1).expect("the model is published");

        assert_eq!(
            published["input_modalities"][0]["pricing"][2],
            json!({ "type": "cache_write", "unit": "token", "cost_usd": "0.000000125" })
        );
        assert_eq!(
            published["output_modalities"][0]["pricing"][1],
            json!({ "type": "internal_reasoning", "unit": "token", "cost_usd": "1.5" })
        );
    }

    #[test]
    fn datacenters_list_each_available_region_once_in_order() {
        let model = with_deployments(&[
            ("us-east-1", DeploymentStatus::Available),
            ("eu-west-1", DeploymentStatus::Draining),
            ("sg", DeploymentStatus::Available),
            ("ca", DeploymentStatus::Unavailable),
            ("sg", DeploymentStatus::Available),
        ]);
        let published = publish(model, 2).expect("the model is published");

        assert_eq!(
            published["datacenters"],
            json!([
                { "country_code": "SG", "region": "sg" },
                { "country_code": "US", "region": "us-east-1" }
            ])
        );
    }

    #[test]
    fn the_deployment_region_is_published_only_for_a_single_known_country() {
        for (regions, expected) in [
            (&["us-east-1", "us-west-2"][..], Some("US")),
            (&["sg", "us-east-1"][..], None),
            (&["local", "us-east-1"][..], None),
            (&["us-east-1", "moon-base-1"][..], None),
        ] {
            let deployments = regions
                .iter()
                .map(|region| (*region, DeploymentStatus::Available))
                .collect::<Vec<_>>();
            let published =
                publish(with_deployments(&deployments), 1).expect("the model is published");

            assert_eq!(
                published.get("deployment_region").and_then(Value::as_str),
                expected,
                "{regions:?}"
            );
        }
    }

    /// Guessing a country from the region's first segment would publish `EU` and
    /// `AP`, which are not countries.
    #[test]
    fn an_unknown_region_publishes_no_country() {
        let mut unknown = model();
        unknown.deployments[0].region = "moon-base-1".to_owned();
        let published = publish(unknown, 1).expect("the model is published");

        assert_eq!(
            published["datacenters"],
            json!([{ "region": "moon-base-1" }])
        );
        assert!(published.get("deployment_region").is_none());
    }

    #[test]
    fn excludes_models_that_cannot_be_advertised() {
        let mut retired = model();
        retired.status = ModelStatus::Retired;
        let mut missing_release = model();
        missing_release.properties.released_at = None;
        let mut missing_deployment = model();
        missing_deployment.deployments.clear();
        let mut invalid_deployments = with_deployments(&[
            ("us-east-1", DeploymentStatus::Available),
            ("us-west-2", DeploymentStatus::Draining),
        ]);
        for deployment in &mut invalid_deployments.deployments {
            deployment.service_url = "ftp://runtime.internal".to_owned();
        }
        let mut unrepresentable_maximum = model();
        unrepresentable_maximum.properties.output_modalities[0]
            .max_length
            .value = u64::MAX;

        for (name, model) in [
            ("retired", retired),
            ("missing release", missing_release),
            ("missing deployment", missing_deployment),
            ("invalid deployments", invalid_deployments),
            ("unrepresentable maximum", unrepresentable_maximum),
        ] {
            assert!(publish(model, 1).is_none(), "{name}");
        }
    }

    #[test]
    fn readiness_follows_the_status_and_the_healthy_deployment_count() {
        for (status, healthy_deployments, expected) in [
            (ModelStatus::Available, 0_u64, false),
            (ModelStatus::Available, 1, true),
            (ModelStatus::Available, 3, true),
            (ModelStatus::Unavailable, 1, false),
        ] {
            let mut model = model();
            model.status = status;
            let published = publish(model, healthy_deployments).expect("the model is published");

            assert_eq!(
                published["is_ready"], expected,
                "{status:?} with {healthy_deployments} healthy deployments"
            );
        }
    }
}
