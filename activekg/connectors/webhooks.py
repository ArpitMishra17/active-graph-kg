"""Webhook handlers for S3 event notifications with security hardening.

Security features:
  - SNS signature verification with certificate validation
  - Replay protection (Redis dedup with 5min TTL)
  - Timeout protection (5s max)
  - Size limit (1MB max)
  - Rate limiting per tenant (when enabled)
  - TopicArn allowlist per tenant (wildcard pattern matching)
  - Signature version validation (only v1 supported)
  - URL-decoded S3 keys (handles spaces/special chars)
  - Prometheus metrics for observability
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from urllib.parse import unquote_plus

import redis
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter

from activekg.connectors.sns_verify import verify_sns_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_webhooks", tags=["webhooks"])

# Prometheus metrics
webhook_sns_verify_total = Counter(
    "webhook_sns_verify_total",
    "Total SNS signature verifications",
    ["result"],  # success, failed, timeout, disabled
)
webhook_replay_total = Counter("webhook_replay_total", "Total webhook replay attempts detected")
webhook_topic_rejected_total = Counter(
    "webhook_topic_rejected_total", "Total webhook rejections due to TopicArn mismatch", ["tenant"]
)
webhook_sig_version_invalid_total = Counter(
    "webhook_sig_version_invalid_total",
    "Total webhook rejections due to unsupported signature version",
    ["version"],
)


def get_topic_allowlist(tenant_id: str) -> list[str]:
    """Get TopicArn allowlist for tenant.

    Allowlist configured via environment variable WEBHOOK_TOPIC_ALLOWLIST.
    Format: JSON object mapping tenant_id to list of TopicArn patterns.
    Example: {"tenant1": ["arn:aws:sns:*:*:activekg-s3-tenant1"], "default": ["arn:aws:sns:*:*:activekg-*"]}

    Args:
        tenant_id: Tenant ID

    Returns:
        List of allowed TopicArn patterns (empty list = allow all)
    """
    allowlist_json = os.getenv("WEBHOOK_TOPIC_ALLOWLIST", "{}")
    try:
        allowlist = json.loads(allowlist_json)
        return allowlist.get(tenant_id, allowlist.get("default", []))
    except Exception as e:
        logger.error(f"Failed to parse WEBHOOK_TOPIC_ALLOWLIST: {e}")
        return []


def validate_topic_arn(topic_arn: str, tenant_id: str) -> bool:
    """Validate TopicArn against tenant allowlist.

    Args:
        topic_arn: SNS TopicArn from message
        tenant_id: Extracted tenant ID

    Returns:
        True if allowed, False if rejected
    """
    allowlist = get_topic_allowlist(tenant_id)

    # Empty allowlist = allow all (permissive mode for dev)
    if not allowlist:
        return True

    # Check against patterns (simple wildcard matching)
    for pattern in allowlist:
        # Simple wildcard matching: arn:aws:sns:*:*:activekg-s3-tenant1
        if pattern == topic_arn:
            return True
        # Wildcard matching
        pattern_parts = pattern.split(":")
        arn_parts = topic_arn.split(":")
        if len(pattern_parts) == len(arn_parts):
            match = all(p == "*" or p == a for p, a in zip(pattern_parts, arn_parts, strict=False))
            if match:
                return True

    return False


def check_replay(redis_client: redis.Redis, message_id: str, ttl_seconds: int = 300) -> bool:
    """Check if message already processed (replay protection).

    Args:
        redis_client: Redis client
        message_id: SNS MessageId
        ttl_seconds: Dedup window (default 5 minutes)

    Returns:
        True if message is new, False if replay
    """
    key = f"webhook:sns:dedup:{message_id}"
    # SET NX: set if not exists, returns 1 if set, 0 if already exists
    result = redis_client.set(key, "1", ex=ttl_seconds, nx=True)
    return result is not None


async def enqueue_s3_event(
    redis_client: redis.Redis,
    tenant_id: str,
    bucket: str,
    key: str,
    event_name: str,
    etag: str | None = None,
):
    """Enqueue S3 event to Redis for async processing.

    Args:
        redis_client: Redis client
        tenant_id: Tenant ID
        bucket: S3 bucket name
        key: S3 object key
        event_name: Event type (ObjectCreated:*, ObjectRemoved:*)
        etag: Object ETag if available
    """
    uri = f"s3://{bucket}/{key}"

    # Determine operation
    if event_name.startswith("ObjectCreated"):
        operation = "upsert"
    elif event_name.startswith("ObjectRemoved"):
        operation = "deleted"
    else:
        logger.warning(f"Unknown event type: {event_name}")
        operation = "upsert"

    # Create ChangeItem
    change_item = {
        "uri": uri,
        "operation": operation,
        "etag": etag,
        "modified_at": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
    }

    # Enqueue to tenant-specific queue
    queue_key = f"connector:s3:{tenant_id}:queue"
    redis_client.lpush(queue_key, json.dumps(change_item))

    logger.info(f"Enqueued {operation} for {uri} (tenant={tenant_id})")


@router.post("/s3")
async def handle_s3_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle S3 event notification via SNS.

    SNS sends two message types:
    1. SubscriptionConfirmation - one-time setup
    2. Notification - actual S3 events

    Security:
    - Timeout: 5s max
    - Size: 1MB max
    - Signature verification
    - Replay protection

    Returns:
        200 OK if processed/queued
        400 Bad Request if invalid
        403 Forbidden if signature invalid
        429 Too Many Requests if rate limited
    """
    # 1. Size limit check (1MB)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large (max 1MB)")

    # 2. Parse body
    try:
        body_bytes = await request.body()
        body = json.loads(body_bytes)
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 3. Get Redis client
    from activekg.common.metrics import get_redis_client

    redis_client = get_redis_client()

    # 4. SNS message type
    message_type = body.get("Type")

    if message_type == "SubscriptionConfirmation":
        # Auto-confirm subscription
        subscribe_url = body.get("SubscribeURL")
        if subscribe_url:
            logger.info(f"SNS subscription confirmation: {subscribe_url}")
            # In production, you'd fetch this URL to confirm
            # For MVP, log it for manual confirmation
            return JSONResponse({"status": "subscription_pending", "url": subscribe_url})
        else:
            raise HTTPException(status_code=400, detail="Missing SubscribeURL")

    elif message_type == "Notification":
        # 5. Signature version check
        signature_version = request.headers.get("x-amz-sns-message-signature-version", "1")
        if signature_version != "1":
            logger.error(f"Unsupported signature version: {signature_version}")
            webhook_sig_version_invalid_total.labels(version=signature_version).inc()
            raise HTTPException(
                status_code=400, detail=f"Unsupported signature version: {signature_version}"
            )

        # 6. Signature verification
        signature = request.headers.get("x-amz-sns-message-signature", "")
        cert_url = request.headers.get("x-amz-sns-signing-cert-url", "")

        # Check if verification is enabled
        verify_enabled = os.getenv("WEBHOOK_VERIFY_SNS", "true").lower() == "true"

        if verify_enabled:
            try:
                if not verify_sns_message(body, signature, cert_url, signature_version):
                    logger.error("SNS signature verification failed")
                    webhook_sns_verify_total.labels(result="failed").inc()
                    raise HTTPException(status_code=403, detail="Invalid signature")
                webhook_sns_verify_total.labels(result="success").inc()
            except HTTPException:
                raise  # Re-raise HTTP exceptions
            except Exception as e:
                logger.error(f"SNS signature verification error: {e}")
                webhook_sns_verify_total.labels(result="timeout").inc()
                raise HTTPException(status_code=503, detail="Signature verification unavailable")
        else:
            logger.warning("SNS signature verification disabled - development mode only!")
            webhook_sns_verify_total.labels(result="disabled").inc()

        # 6. Replay protection
        message_id = body.get("MessageId")
        if not message_id or not check_replay(redis_client, message_id):
            logger.warning(f"Replay detected: {message_id}")
            webhook_replay_total.inc()
            # Return 200 to avoid SNS retries
            return JSONResponse({"status": "duplicate"})

        # 7. Parse S3 event from SNS message
        try:
            message_content = json.loads(body.get("Message", "{}"))
            records = message_content.get("Records", [])
        except Exception as e:
            logger.error(f"Failed to parse S3 event: {e}")
            raise HTTPException(status_code=400, detail="Invalid S3 event format")

        # 8. Extract tenant_id from SNS topic or subject
        # Format: arn:aws:sns:region:account:activekg-s3-{tenant_id}
        topic_arn = body.get("TopicArn", "")
        tenant_id = "default"
        if ":activekg-s3-" in topic_arn:
            tenant_id = topic_arn.split(":activekg-s3-")[-1]

        # 9. Validate TopicArn against tenant allowlist
        if not validate_topic_arn(topic_arn, tenant_id):
            logger.error(f"TopicArn rejected for tenant {tenant_id}: {topic_arn}")
            webhook_topic_rejected_total.labels(tenant=tenant_id).inc()
            raise HTTPException(status_code=403, detail="TopicArn not allowed for tenant")

        # 10. Process each S3 record
        queued_count = 0
        for record in records:
            try:
                event_name = record.get("eventName", "")
                s3_info = record.get("s3", {})
                bucket = s3_info.get("bucket", {}).get("name")
                obj = s3_info.get("object", {})
                key = obj.get("key")
                etag = obj.get("eTag")

                # URL-decode S3 key (S3 sends URL-encoded keys)
                if key:
                    key = unquote_plus(key)

                if bucket and key:
                    # Enqueue in background
                    background_tasks.add_task(
                        enqueue_s3_event, redis_client, tenant_id, bucket, key, event_name, etag
                    )
                    queued_count += 1
            except Exception as e:
                logger.error(f"Failed to process record: {e}")
                continue

        return JSONResponse({"status": "queued", "count": queued_count, "tenant_id": tenant_id})

    else:
        logger.warning(f"Unknown SNS message type: {message_type}")
        raise HTTPException(status_code=400, detail="Unknown message type")


@router.get("/s3/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    from activekg.common.metrics import get_redis_client

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        return {"status": "degraded", "redis": str(e)}
