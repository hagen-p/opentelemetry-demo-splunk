# Manifest File Locations

## Current Release

The latest promoted manifests are available as assets on the corresponding GitHub Release tag.

To find the current promoted version:

```bash
cat kubernetes/PROMOTED-VERSION
```

Then download manifests from:

```
https://github.com/splunk/opentelemetry-demo/releases/tag/v<VERSION>
```

Release assets include:
- `splunk-astronomy-shop-<VERSION>.yaml` - Core services
- `splunk-astronomy-shop-<VERSION>-diab.yaml` - DIAB (includes Traefik ingress)
- `splunk-astronomy-shop-<VERSION>-lambda.yaml` - Lambda/planning services
- `splunk-astronomy-shop-<VERSION>-dc-shim.yaml` - Datacenter shim + db + loadgen
- `splunk-astronomy-shop-<VERSION>-values.yaml` - Helm values

## How versions get promoted

The `PROMOTED-VERSION` file is updated by the **Astronomy Shop - Promote** GitHub Action
when manifests are successfully pushed to `splunk/o11y-field-demos`.

## Old versions

Previously committed manifests have been moved to `kubernetes/old-versions/` for reference.
New releases no longer commit stitched manifests to git -- they are attached to GitHub Releases instead.
