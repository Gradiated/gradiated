# Eight lanes for the final token-score projection

The control is the exact previous four-lane circuit. The candidate specialises the same module at eight lanes. It shares each activation across the eight lanes, reads each score row's weight from a separate bank and emits scores in ascending row order.

Run `materialise_eight.py --lanes 4|8 --output /path/to/fresh/rtl` for either source closure. Run `test_model.py --help` for the signed component and seven exact model checks. The [experiment protocol](../../../../experiments/kv260-logits-8-lanes-v1.md) defines the physical comparison and its stopping rules.
