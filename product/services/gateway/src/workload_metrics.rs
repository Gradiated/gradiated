use prometheus_client::{
    encoding::EncodeLabelSet,
    metrics::{counter::Counter, family::Family, histogram::Histogram},
    registry::Registry,
};

use crate::{request_telemetry::RequestTelemetry, NormalizedUsage};

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct WorkloadLabels {
    model: String,
    traffic: &'static str,
    kind: &'static str,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct RequestLabels {
    #[prometheus(flatten)]
    workload: WorkloadLabels,
    protocol: &'static str,
    task_type: &'static str,
    task_source: &'static str,
    status: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct ObservationLabels {
    #[prometheus(flatten)]
    workload: WorkloadLabels,
    quantity: &'static str,
}

type Histograms = Family<ObservationLabels, Histogram>;

pub(crate) struct WorkloadMetrics {
    qualified: Family<RequestLabels, Counter>,
    requests: Family<RequestLabels, Counter>,
    tokens: Family<ObservationLabels, Counter>,
    token_lengths: Histograms,
    structures: Histograms,
    bytes: Histograms,
    fractions: Histograms,
    truncated: Family<ObservationLabels, Counter>,
}

impl WorkloadMetrics {
    pub(crate) fn register(registry: &mut Registry) -> Self {
        let result = Self {
            qualified: Family::default(),
            truncated: Family::default(),
            requests: Family::default(),
            tokens: Family::default(),
            token_lengths: Family::new_with_constructor(|| {
                Histogram::new([
                    0.0, 128.0, 512.0, 2048.0, 8192.0, 32768.0, 131072.0, 524288.0, 1048576.0,
                ])
            }),
            structures: Family::new_with_constructor(|| {
                Histogram::new([
                    0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 512.0, 2048.0, 8192.0,
                ])
            }),
            bytes: Family::new_with_constructor(|| {
                Histogram::new([
                    0.0, 128.0, 512.0, 2048.0, 8192.0, 32768.0, 131072.0, 524288.0, 2097152.0,
                    8388608.0, 32000000.0,
                ])
            }),
            fractions: Family::new_with_constructor(|| {
                Histogram::new([
                    0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0, 2.0, 4.0, 16.0,
                ])
            }),
        };
        registry.register("workload_requests", "Terminal generations with bounded request categories; heuristic task labels are uncertain.", result.requests.clone());
        registry.register("workload_qualified_requests", "Validated generation requests before token bounds, routing and admission; not terminal outcomes.", result.qualified.clone());
        registry.register(
            "workload_tokens",
            "Reported token totals by structural request kind; reasoning is a subset of output.",
            result.tokens.clone(),
        );
        registry.register("workload_token_lengths", "Reported token-count distributions by structural request kind, including interrupted generations.", result.token_lengths.clone());
        registry.register(
            "workload_structure",
            "Request structural-count distributions, bounded by extraction budgets.",
            result.structures.clone(),
        );
        registry.register(
            "workload_bytes",
            "UTF-8 request and text byte distributions; not token estimates.",
            result.bytes.clone(),
        );
        registry.register("workload_fractions", "Per-request token and scanned-text ratio distributions; zero denominators are omitted.", result.fractions.clone());
        registry.register(
            "workload_truncated",
            "Terminal request metadata that reached an extraction budget, by component.",
            result.truncated.clone(),
        );

        result
    }

    pub(crate) fn qualified(&self, model: &str, request: &RequestTelemetry) {
        self.qualified
            .get_or_create(&RequestLabels {
                workload: WorkloadLabels {
                    model: model.to_owned(),
                    traffic: request.traffic,
                    kind: request.kind,
                },
                protocol: request.protocol,
                task_type: request.task_type,
                task_source: request.task_source,
                status: "qualified".to_owned(),
            })
            .inc();
    }

    pub(crate) fn observe(
        &self,
        model: &str,
        request: &RequestTelemetry,
        usage: NormalizedUsage,
        status: &str,
    ) {
        let workload = WorkloadLabels {
            model: model.to_owned(),
            traffic: request.traffic,
            kind: request.kind,
        };
        self.requests
            .get_or_create(&RequestLabels {
                workload: workload.clone(),
                protocol: request.protocol,
                task_type: request.task_type,
                task_source: request.task_source,
                status: status.to_owned(),
            })
            .inc();
        let labels = |quantity| ObservationLabels {
            workload: workload.clone(),
            quantity,
        };
        for (quantity, truncated) in [
            ("structure", request.truncated),
            ("text", request.text_shape.truncated),
            ("tool_schema", request.tool_schema.truncated),
            ("response_schema", request.response_schema.truncated),
        ] {
            if truncated {
                self.truncated.get_or_create(&labels(quantity)).inc();
            }
        }
        for (quantity, value) in [
            ("input", usage.input_tokens()),
            (
                "uncached_input",
                usage.input_tokens() - usage.cached_input_tokens(),
            ),
            ("cached_input", usage.cached_input_tokens()),
            ("cache_write", usage.cache_write_tokens()),
            ("output", usage.output_tokens()),
            ("reasoning", usage.reasoning_tokens()),
        ] {
            self.tokens.get_or_create(&labels(quantity)).inc_by(value);
            self.token_lengths
                .get_or_create(&labels(quantity))
                .observe(value as f64);
        }
        for (quantity, value) in [
            ("messages", request.messages),
            ("role_transitions", request.role_transitions),
            ("system_messages", request.roles.system),
            ("developer_messages", request.roles.developer),
            ("user_messages", request.roles.user),
            ("assistant_messages", request.roles.assistant),
            ("tool_messages", request.roles.tool),
            ("tool_definitions", request.tool_definitions),
            ("strict_tools", request.strict_tools),
            ("tool_calls", request.tool_calls),
            ("tool_results", request.tool_results),
            ("tool_schema_nodes", request.tool_schema.nodes),
            ("tool_schema_properties", request.tool_schema.properties),
            ("tool_schema_depth", request.tool_schema.max_depth),
            ("tool_schema_enum_values", request.tool_schema.enum_values),
            ("response_schema_nodes", request.response_schema.nodes),
            ("response_schema_depth", request.response_schema.max_depth),
            ("images", request.content_parts.image),
            ("audio", request.content_parts.audio),
            ("video", request.content_parts.video),
            ("files", request.content_parts.file),
            ("line_breaks", request.text_shape.line_breaks),
            ("code_fences", request.text_shape.code_fences),
        ] {
            self.structures
                .get_or_create(&labels(quantity))
                .observe(value as f64);
        }
        for (quantity, value) in [
            ("request", request.request_bytes),
            ("system_text", request.text_bytes.system),
            ("developer_text", request.text_bytes.developer),
            ("user_text", request.text_bytes.user),
            ("assistant_text", request.text_bytes.assistant),
            ("tool_text", request.text_bytes.tool),
            ("instructions", request.instruction_text_bytes),
            ("last_user_text", request.last_user_text_bytes),
            ("max_message_text", request.max_message_text_bytes),
            ("tool_arguments_text", request.tool_argument_text_bytes),
            ("max_scanned_line", request.text_shape.max_line_bytes),
        ] {
            self.bytes
                .get_or_create(&labels(quantity))
                .observe(value as f64);
        }
        for (quantity, numerator, denominator) in [
            ("cache", usage.cached_input_tokens(), usage.input_tokens()),
            ("output_input", usage.output_tokens(), usage.input_tokens()),
            ("reasoning", usage.reasoning_tokens(), usage.output_tokens()),
            (
                "text_whitespace",
                request.text_shape.whitespace_bytes,
                request.text_shape.scanned_bytes,
            ),
            (
                "text_digits",
                request.text_shape.digit_bytes,
                request.text_shape.scanned_bytes,
            ),
            (
                "text_non_ascii",
                request.text_shape.non_ascii_bytes,
                request.text_shape.scanned_bytes,
            ),
        ] {
            if denominator > 0 {
                self.fractions
                    .get_or_create(&labels(quantity))
                    .observe(numerator as f64 / denominator as f64);
            }
        }
    }
}
