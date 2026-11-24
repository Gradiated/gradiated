# Live-tuning policies

A file named after a hardware profile, such as `b300-pcp2.json`, is the
livetune policy the service's controller runs on that profile when
`LIVETUNE_MODE` is `observe` or `act`. A profile without a file records traffic
and runs no controller.

A policy is a reviewed bundle release. Produce one with `livetune tune` or
`livetune improve` on a canary with this bundle's scope, then commit it here.
The controller refuses a policy whose recorded scope differs from the live
server. See `product/inference/livetune/README.md`.
