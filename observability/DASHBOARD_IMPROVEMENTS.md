# Grafana Dashboard Improvements Guide

Suggested enhancements to the provided Grafana dashboards for better incident triage, portability, and operational visibility.

---

## Connector Overview Dashboard

### Current State
The overview dashboard provides high-level metrics across all providers and tenants:
- Webhook verification rates
- Queue depth aggregates
- Ingestion rates and error rates
- Worker latency, purger activity, reconnects
- Key rotation and decryption failures

### Recommended Improvements

#### 1. Add Provider/Tenant Template Variables

**Why**: Currently the overview shows aggregate metrics. Adding filters allows scoping to specific provider/tenant during incidents.

**How**: Add to `templating.list` in `connector_overview.json`:

```json
{
  "templating": {
    "list": [
      {
        "name": "datasource",
        "type": "datasource",
        "query": "prometheus",
        "current": {
          "text": "Prometheus",
          "value": "Prometheus"
        }
      },
      {
        "name": "provider",
        "type": "query",
        "datasource": "${datasource}",
        "query": "label_values(connector_ingest_total, provider)",
        "current": {
          "text": "All",
          "value": "$__all"
        },
        "includeAll": true,
        "multi": true,
        "refresh": 1
      },
      {
        "name": "tenant",
        "type": "query",
        "datasource": "${datasource}",
        "query": "label_values(connector_worker_queue_depth{provider=~\"$provider\"}, tenant)",
        "current": {
          "text": "All",
          "value": "$__all"
        },
        "includeAll": true,
        "multi": true,
        "refresh": 1
      }
    ]
  }
}
```

**Then update key panel queries**:
- Ingestion rate: `rate(connector_ingest_total{provider=~"$provider", tenant=~"$tenant"}[5m])`
- Queue depth: `connector_worker_queue_depth{provider=~"$provider", tenant=~"$tenant"}`
- Error rate: `rate(connector_ingest_errors_total{provider=~"$provider", tenant=~"$tenant"}[5m])`

#### 2. Verify Worker Latency Metric Name

**Issue**: Dashboard references `connector_worker_process_duration_bucket`.

**Action**: Verify this metric exists in staging:
```bash
curl -s http://localhost:8000/metrics | grep -E 'worker.*duration'
```

**Alternatives**:
- If you emit `worker_batch_latency_seconds_bucket`, use:
  ```promql
  histogram_quantile(0.95, sum(rate(worker_batch_latency_seconds_bucket[5m])) by (le))
  ```
- If you emit `connector_worker_process_duration_bucket`, keep as-is.

#### 3. Use `$__rate_interval` Instead of Hardcoded `[5m]`

**Why**: Adapts rate window to dashboard time range for better accuracy.

**Change**:
```promql
# Before
rate(connector_ingest_total[5m])

# After
rate(connector_ingest_total[$__rate_interval])
```

**Apply to all rate/irate queries** in ingestion rate, error rate, webhook verification panels.

#### 4. Add Datasource Variable for Portability

See template variables above. This allows importing the dashboard across Grafana instances without editing hardcoded datasource references.

#### 5. Improve Legend Formatting

**Current**: Basic metric names
**Better**: Include key labels in legend

**Example** (Ingestion Rate panel):
```json
{
  "legendFormat": "{{provider}}/{{tenant}}"
}
```

**Example** (Webhook Verification panel):
```json
{
  "legendFormat": "{{result}}"
}
```

---

## Connector Queue Details Dashboard

### Current State
The queues dashboard provides deep-dive views:
- Queue depth over time with provider/tenant filtering
- Current queue depth table with color coding
- Worker processing rate, ingestion errors by provider
- Processing latency heatmap
- Recent webhook events

### Recommended Improvements

#### 1. Verify Heatmap Bucket Metric

**Issue**: Dashboard uses `connector_worker_process_duration_bucket` in heatmap panel.

**Action**: Ensure this matches actual emitted metric:
```bash
curl -s http://localhost:8000/metrics | grep -E '_bucket.*le='
```

**If using different bucket name**, update heatmap query:
```promql
sum(rate(worker_batch_latency_seconds_bucket{provider=~"$provider", tenant=~"$tenant"}[$__rate_interval])) by (le)
```

#### 2. Enable "All Series" Tooltips

**Why**: Multi-line timeseries panels benefit from seeing all series values on hover.

**How**: In each timeseries panel's `options.tooltip`:
```json
{
  "options": {
    "tooltip": {
      "mode": "multi",
      "sort": "desc"
    }
  }
}
```

#### 3. Add Deployment Annotations

**Why**: Correlate queue depth spikes with deployments.

**How**: Add to `annotations.list`:
```json
{
  "name": "Deployments",
  "datasource": "${datasource}",
  "enable": true,
  "expr": "changes(up{job=\"activekg\"}[1m]) > 0",
  "iconColor": "blue",
  "tagKeys": "instance",
  "titleFormat": "Deployment"
}
```

Or use external annotation source (e.g., GitHub deployments API).

#### 4. Add Time Range Display

**Why**: Helps NOC operators understand what window they're viewing on large screens.

**How**: Add text panel at top:
```json
{
  "id": 100,
  "type": "text",
  "gridPos": {"x": 0, "y": 0, "w": 24, "h": 2},
  "options": {
    "content": "**Time Range**: ${__from:date:YYYY-MM-DD HH:mm} to ${__to:date:YYYY-MM-DD HH:mm}",
    "mode": "markdown"
  }
}
```

#### 5. Add Provider Comparison Panel

**Why**: Quickly identify which provider has highest queue depth or error rate.

**Example panel** (add to dashboard):
```json
{
  "id": 101,
  "title": "Queue Depth by Provider (Current)",
  "type": "bargauge",
  "gridPos": {"x": 0, "y": 40, "w": 12, "h": 8},
  "targets": [{
    "expr": "sum by (provider) (connector_worker_queue_depth{provider=~\"$provider\", tenant=~\"$tenant\"})",
    "legendFormat": "{{provider}}",
    "instant": true
  }],
  "options": {
    "orientation": "horizontal",
    "displayMode": "gradient",
    "showUnfilled": true
  },
  "fieldConfig": {
    "defaults": {
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {"value": 0, "color": "green"},
          {"value": 500, "color": "yellow"},
          {"value": 1000, "color": "red"}
        ]
      }
    }
  }
}
```

---

## General Dashboard Best Practices

### 1. Consistent Rate Windows

Use `$__rate_interval` for all rate/irate/increase queries to adapt to time range.

**Before**:
```promql
rate(metric[5m])
increase(metric[10m])
```

**After**:
```promql
rate(metric[$__rate_interval])
increase(metric[$__range])  # For increase over full dashboard range
```

### 2. Unified Color Schemes

**Queue depth thresholds** (use consistently):
- Green: 0-499
- Yellow: 500-999
- Red: ≥1000

**Error rate thresholds**:
- Green: 0-0.5%
- Yellow: 0.5-1%
- Red: >1%

### 3. Panel Descriptions

Add descriptions to complex panels using `description` field:
```json
{
  "description": "Shows p50/p95/p99 latency for worker batch processing. Spikes indicate slow DB queries or external API calls."
}
```

### 4. Links to Runbooks

Add panel links to relevant runbook sections:
```json
{
  "links": [
    {
      "title": "Troubleshooting Guide",
      "url": "https://github.com/yourorg/activekg/blob/main/docs/operations/OPERATIONS.md#queue-depth"
    }
  ]
}
```

### 5. Refresh Intervals

**Overview dashboard**: 30s refresh (high-level monitoring)
**Queue details dashboard**: 10s refresh (incident investigation)

Set in dashboard JSON:
```json
{
  "refresh": "30s"  // or "10s"
}
```

---

## Metric Name Verification Checklist

Before finalizing dashboards, verify these metrics exist in your environment:

```bash
# Core metrics
curl -s http://localhost:8000/metrics | grep -E '^connector_worker_queue_depth'
curl -s http://localhost:8000/metrics | grep -E '^connector_ingest_total'
curl -s http://localhost:8000/metrics | grep -E '^connector_ingest_errors_total'

# Latency metric (verify exact name)
curl -s http://localhost:8000/metrics | grep -E 'duration|latency' | grep bucket

# Webhook metrics
curl -s http://localhost:8000/metrics | grep -E '^webhook_pubsub_verify_total'
curl -s http://localhost:8000/metrics | grep -E '^webhook_sns_verify_total'

# DLQ metrics
curl -s http://localhost:8000/metrics | grep -E '^connector_dlq'
```

**If metric names differ**, update dashboard queries accordingly.

---

## Testing Dashboard Changes

### 1. Import Modified Dashboard
```bash
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @observability/dashboards/connector_overview.json
```

### 2. Verify Template Variables Populate
- Navigate to dashboard settings → Variables
- Check that `$provider` and `$tenant` show actual values from Prometheus

### 3. Test Filtering
- Select specific provider (e.g., "gcs")
- Select specific tenant (e.g., "default")
- Verify all panels update to show filtered data

### 4. Check Panel Queries
- Click "Edit" on any panel
- Click "Query Inspector" → "Refresh"
- Verify query returns data

---

## Dashboard Export/Import Best Practices

### Before Export
1. Set all template variables to "All"
2. Set time range to "Last 6 hours"
3. Remove any instance-specific panel links

### After Import
1. Update datasource to match new Grafana instance
2. Verify template variables query correctly
3. Test all panel queries against new Prometheus

### Version Control
- Store dashboard JSON in `observability/dashboards/`
- Include version number in dashboard title (e.g., "Connector Overview v2.0")
- Document changes in git commit messages

---

## Next Steps

1. **Verify metric names** in your staging environment
2. **Add template variables** to overview dashboard for provider/tenant filtering
3. **Update rate queries** to use `$__rate_interval`
4. **Test imports** in staging Grafana before production rollout
5. **Add deployment annotations** for correlation analysis

For questions or issues, reference the operations guide at `docs/operations/OPERATIONS.md`.
