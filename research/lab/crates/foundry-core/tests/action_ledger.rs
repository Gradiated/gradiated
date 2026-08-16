use foundry_core::action_ledger::*;

const GLM_FIXTURE: &str = include_str!("fixtures/glm-5.2-decode-ledger-v1.json");

fn glm_fixture() -> ActionLedger {
    ActionLedger::from_json(GLM_FIXTURE).expect("GLM fixture must be valid")
}

fn measurement_source() -> MeasurementProvenance {
    MeasurementProvenance {
        adapter_id: "mock-calibrated-adapter".into(),
        adapter_version: "1.0.0".into(),
        calibration_artifact_id: "calibration:mock-v1".into(),
        run_id: "run:mock-v1".into(),
    }
}

#[test]
fn glm_decode_fixture_covers_every_action_type_and_accounts_units() {
    let ledger = glm_fixture();
    let accounting = ledger.accounting().expect("accounting must be checked");

    assert_eq!(ledger.provenance.model.model_id, "zai-org/GLM-5.2");
    assert_eq!(ledger.provenance.phase.phase, InferencePhase::Decode);
    assert!(
        ledger
            .actions
            .iter()
            .all(|action| !action.evidence.source_artifact_id.is_empty())
    );
    assert!(ledger.actions.iter().any(Action::is_compute));
    assert!(ledger.actions.iter().any(Action::is_memory));
    assert!(ledger.actions.iter().any(Action::is_cache));
    assert!(ledger.actions.iter().any(Action::is_network));
    assert!(ledger.actions.iter().any(Action::is_synchronization));
    assert!(ledger.actions.iter().any(Action::is_scheduler));
    assert_eq!(accounting.flops, Flops::new(222_298_112));
    assert_eq!(accounting.non_flop_operations, Operations::new(8_192));
    assert_eq!(accounting.memory_bytes, Bytes::new(5_275_648));
    assert_eq!(accounting.cache_bytes, Bytes::new(32_768));
    assert_eq!(accounting.network_bytes, Bytes::new(24_576));
    assert_eq!(accounting.messages, Messages::new(56));
    assert_eq!(accounting.compute_actions, 6);
    assert_eq!(accounting.memory_actions, 4);
    assert_eq!(accounting.cache_actions, 2);
    assert_eq!(accounting.network_actions, 1);
    assert_eq!(accounting.synchronization_actions, 2);
    assert_eq!(accounting.scheduler_actions, 4);
}

#[test]
fn fixture_has_a_checked_canonical_json_round_trip() {
    let ledger = glm_fixture();
    let canonical = ledger
        .to_canonical_json()
        .expect("canonical serialization must succeed");
    let round_trip = ActionLedger::from_json(&canonical).expect("round trip must validate");

    assert_eq!(round_trip, ledger.canonicalized());
    assert_eq!(
        round_trip.content_id().unwrap(),
        ledger.content_id().unwrap()
    );
    assert_eq!(round_trip.to_canonical_json().unwrap(), canonical);
}

#[test]
fn content_identity_is_order_independent_and_excludes_adapter_results() {
    let ledger = glm_fixture();
    let expected = ledger.content_id().unwrap();
    assert_eq!(expected.as_str().len(), 64);
    assert!(
        expected
            .as_str()
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    );
    let mut reordered = ledger.clone();
    reordered.actions.reverse();
    for action in &mut reordered.actions {
        action.dependencies.reverse();
    }

    assert_eq!(reordered.content_id().unwrap(), expected);

    let first = reordered.actions[0].id.clone();
    reordered
        .attach_measurements(
            &first,
            AdapterMeasurements {
                provenance: measurement_source(),
                latency: Some(Seconds::new(0.001)),
                energy: Some(Joules::new(0.25)),
                cost: Some(Usd::new(0.000_001)),
            },
        )
        .unwrap();

    assert_eq!(reordered.content_id().unwrap(), expected);

    let ActionWork::Compute(compute) = &mut reordered
        .actions
        .iter_mut()
        .find(|action| action.is_compute())
        .unwrap()
        .work
    else {
        unreachable!()
    };
    compute.flops = Flops::new(compute.flops.get() + 1);
    assert_ne!(reordered.content_id().unwrap(), expected);
}

#[test]
fn validation_rejects_duplicate_unknown_and_cyclic_dependencies() {
    let ledger = glm_fixture();

    let mut duplicate = ledger.clone();
    duplicate.actions.push(duplicate.actions[0].clone());
    assert!(matches!(
        duplicate.validate(),
        Err(LedgerError::DuplicateActionId(_))
    ));

    let mut unknown = ledger.clone();
    unknown.actions[0]
        .dependencies
        .push(ActionId::from("missing_action"));
    assert!(matches!(
        unknown.validate(),
        Err(LedgerError::UnknownDependency { .. })
    ));

    let mut cyclic = ledger;
    cyclic.actions[0]
        .dependencies
        .push(ActionId::from("token_commit"));
    assert!(matches!(
        cyclic.validate(),
        Err(LedgerError::DependencyCycle)
    ));
}

#[test]
fn topological_order_is_deterministic_and_respects_dependencies() {
    let ledger = glm_fixture();
    let first = ledger.topological_action_ids().unwrap();
    let second = ledger.topological_action_ids().unwrap();

    assert_eq!(first, second);
    for action in &ledger.actions {
        let action_position = first.iter().position(|id| id == &action.id).unwrap();
        for dependency in &action.dependencies {
            let dependency_position = first.iter().position(|id| id == dependency).unwrap();
            assert!(dependency_position < action_position);
        }
    }
}

#[test]
fn latency_energy_and_cost_fail_closed_until_every_action_is_calibrated() {
    let fixture = glm_fixture();
    let mut ledger = ActionLedger {
        actions: vec![Action {
            dependencies: Vec::new(),
            ..fixture.actions[0].clone()
        }],
        ..fixture
    };
    let content_id = ledger.content_id().unwrap();

    assert!(matches!(
        ledger.total_latency(),
        Err(LedgerError::MissingMeasurement {
            metric: MeasurementMetric::Latency,
            ..
        })
    ));
    assert!(matches!(
        ledger.total_energy(),
        Err(LedgerError::MissingMeasurement {
            metric: MeasurementMetric::Energy,
            ..
        })
    ));
    assert!(matches!(
        ledger.total_cost(),
        Err(LedgerError::MissingMeasurement {
            metric: MeasurementMetric::Cost,
            ..
        })
    ));

    let action_id = ledger.actions[0].id.clone();
    ledger
        .attach_measurements(
            &action_id,
            AdapterMeasurements {
                provenance: measurement_source(),
                latency: Some(Seconds::new(0.002)),
                energy: Some(Joules::new(0.4)),
                cost: Some(Usd::new(0.000_002)),
            },
        )
        .unwrap();

    assert_eq!(ledger.total_latency().unwrap(), Seconds::new(0.002));
    assert_eq!(ledger.total_energy().unwrap(), Joules::new(0.4));
    assert_eq!(ledger.total_cost().unwrap(), Usd::new(0.000_002));
    assert_eq!(ledger.content_id().unwrap(), content_id);
    assert!(matches!(
        ledger.attach_measurements(
            &action_id,
            AdapterMeasurements {
                provenance: measurement_source(),
                latency: Some(Seconds::new(0.003)),
                energy: None,
                cost: None,
            }
        ),
        Err(LedgerError::MeasurementsAlreadyAttached(_))
    ));
}

#[test]
fn uncalibrated_or_invalid_adapter_measurements_are_rejected_without_mutation() {
    let fixture = glm_fixture();
    let mut ledger = ActionLedger {
        actions: vec![Action {
            dependencies: Vec::new(),
            ..fixture.actions[0].clone()
        }],
        ..fixture
    };
    let action_id = ledger.actions[0].id.clone();
    let mut source = measurement_source();
    source.calibration_artifact_id.clear();

    assert!(matches!(
        ledger.attach_measurements(
            &action_id,
            AdapterMeasurements {
                provenance: source,
                latency: Some(Seconds::new(0.001)),
                energy: None,
                cost: None,
            }
        ),
        Err(LedgerError::InvalidField(_))
    ));
    assert!(ledger.actions[0].measurements.is_none());

    assert!(matches!(
        ledger.attach_measurements(
            &action_id,
            AdapterMeasurements {
                provenance: measurement_source(),
                latency: Some(Seconds::new(f64::NAN)),
                energy: None,
                cost: None,
            }
        ),
        Err(LedgerError::InvalidMeasurement { .. })
    ));
    assert!(ledger.actions[0].measurements.is_none());
}

#[test]
fn checked_accounting_rejects_overflow() {
    let fixture = glm_fixture();
    let mut first = fixture
        .actions
        .iter()
        .find(|action| action.is_memory())
        .unwrap()
        .clone();
    first.dependencies.clear();
    let ActionWork::Memory(memory) = &mut first.work else {
        unreachable!()
    };
    memory.bytes = Bytes::new(u64::MAX);
    let mut second = first.clone();
    second.id = ActionId::from("overflow_second");

    let ledger = ActionLedger {
        actions: vec![first, second],
        ..fixture
    };

    assert!(matches!(
        ledger.accounting(),
        Err(LedgerError::AccountingOverflow(AccountingUnit::Bytes))
    ));
}

#[test]
fn unknown_json_fields_fail_instead_of_being_ignored() {
    let mut json: serde_json::Value = serde_json::from_str(GLM_FIXTURE).unwrap();
    json["unexpected"] = serde_json::json!(true);

    assert!(matches!(
        ActionLedger::from_json(&serde_json::to_string(&json).unwrap()),
        Err(LedgerError::Serialization(_))
    ));
}
