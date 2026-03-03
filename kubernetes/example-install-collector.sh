#!/bin/bash
helm repo add splunk-otel-collector-chart https://signalfx.github.io/splunk-otel-collector-chart && helm repo update
helm upgrade --install splunk-otel-collector --version $HELM_VERSION \
--set="splunkObservability.realm=$REALM" \
--set="splunkObservability.accessToken=$ACCESS_TOKEN" \
--set="clusterName=$INSTANCE-k3s-cluster" \
--set="splunkObservability.profilingEnabled=true" \
--set="splunkObservability.secureAppEnabled=true" \
--set="agent.service.enabled=true"  \
--set="environment=$INSTANCE" \
--set="splunkPlatform.endpoint=$HEC_URL" \
--set="splunkPlatform.token=$HEC_TOKEN" \
--set="splunkPlatform.index=o11y-demo-eu" \
splunk-otel-collector-chart/splunk-otel-collector \
-f /home/ubuntu/splunk-astronomy-shop-$ASTRONOMY_VERSION-values.yaml
