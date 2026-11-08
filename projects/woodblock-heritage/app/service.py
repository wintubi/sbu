"""Business rules for source intake, candidate import, review and publication."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from typing import Any

from .errors import ApiError
from .images import decode_source
from .models import (
    PREDICATES,
    SCHEMA_VERSION,
    ReviewCreate,
    SourceCreate,
    WorkCreate,
)
from .store import Store, dumps, utc_now


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _hash(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def _require_key(key: str | None) -> str:
    text = (key or "").strip()
    if not text or len(text) > 200:
        raise ApiError(422, "IDEMPOTENCY_KEY_REQUIRED", "缺少或非法 Idempotency-Key",
                       cause="写请求必须带 1–200 字符的幂等键",
                       fix="为本次操作生成一个新的幂等键；重试时复用同一个键")
    return text


def _replay(store: Store, conn, scope: str, key: str, request_hash: str) -> tuple[dict | None, bool]:
    prior = store.get_idempotency(conn, scope, key)
    if prior is None:
        return None, False
    if prior["request_hash"] != request_hash:
        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键对应不同请求",
                       cause="键已用于另一份请求体",
                       fix="重试原请求，或为新请求使用新键")
    return json.loads(prior["response_json"]), True


def _source_view(row: dict[str, Any]) -> dict[str, Any]:
    meta = json.loads(row["metadata_json"])
    return {
        "source_id": row["id"],
        "content_hash": row["content_hash"],
        "media_type": row["media_type"],
        "width": row["width"],
        "height": row["height"],
        "created_at": row["created_at"],
        **meta,
    }


def _event_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row["id"],
        "work_id": row["work_id"],
        "from_version": row["from_version"],
        "to_version": row["to_version"],
        "reviewer": row["reviewer"],
        "reason": row["reason"],
        "payload": row["payload"],
        "created_at": row["created_at"],
    }


def _work_view(store: Store, work: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_id": work["id"],
        "version": payload["_version"],
        "current_version": work["current_version"],
        "historical": payload["_version"] != work["current_version"],
        "payload": {key: value for key, value in payload.items() if not key.startswith("_")},
        "events": [_event_view(item) for item in store.get_events(work["id"])],
    }


def _claim_issues(claim: dict[str, Any], region_ids: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    predicate = claim.get("predicate")
    if predicate not in PREDICATES:
        issues.append(_issue("UNKNOWN_PREDICATE", f"不支持的谓词 {predicate!r}",
                             affected_claim_id=claim["id"], blocking=True))
    refs = claim.get("evidence_refs") or []
    missing = [ref for ref in refs if ref not in region_ids]
    if not refs:
        issues.append(_issue("MISSING_EVIDENCE", "断言没有证据引用",
                             affected_claim_id=claim["id"], blocking=True))
    elif missing:
        issues.append(_issue("MISSING_EVIDENCE", "断言引用了不存在的区域：" + ", ".join(missing),
                             evidence_refs=missing, affected_claim_id=claim["id"], blocking=True))
    value = (claim.get("object") or {}).get("value")
    if value is None or not str(value).strip():
        issues.append(_issue("EMPTY_VALUE", "断言值为空，不能批准",
                             affected_claim_id=claim["id"], blocking=True))
    return issues


def _issue(code: str, message: str, *, affected_claim_id: str | None = None,
           evidence_refs: list[str] | None = None, blocking: bool = True,
           source: str = "server", issue_id: str | None = None) -> dict[str, Any]:
    return {
        "id": issue_id or new_id("iss"),
        "code": code,
        "message": message,
        "evidence_refs": evidence_refs or [],
        "status": "open",
        "blocking": blocking,
        "affected_claim_id": affected_claim_id,
        "source": source,
    }


def _literal_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(422, "INVALID_OBJECT", "断言对象必须是对象",
                       cause="object 不是 JSON 对象", fix="使用 {kind:'literal', value:'...'}")
    if value.get("kind") != "literal":
        raise ApiError(422, "UNSUPPORTED_OBJECT", "本切片只支持字面量断言",
                       cause=f"object.kind={value.get('kind')!r}",
                       fix="本切片不支持的实体关系需另立变更，不要强转成字符串")
    literal = value.get("value")
    if literal is not None and not isinstance(literal, str):
        raise ApiError(422, "INVALID_LITERAL", "字面量值必须是字符串或 null",
                       fix="改为字符串或 null")
    return {"kind": "literal", "value": literal}


def _normalize_regions(body: WorkCreate, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for region in body.regions:
        if region.id in ids:
            raise ApiError(422, "DUPLICATE_ID", f"区域 ID 重复：{region.id}",
                           fix="每个区域 ID 在作品内必须唯一")
        ids.add(region.id)
        if region.source_id not in sources:
            raise ApiError(422, "UNKNOWN_SOURCE", f"区域引用了未声明的来源：{region.source_id}",
                           fix="先把来源加入 source_ids 并登记")
        source = sources[region.source_id]
        x0, y0, x1, y1 = region.bbox
        if region.coordinate_system == "normalized":
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ApiError(422, "INVALID_BBOX", "归一化坐标必须满足 0≤x0<x1≤1、0≤y0<y1≤1",
                               cause=f"bbox={region.bbox}", fix="检查坐标顺序和范围")
            box = [x0, y0, x1, y1]
        else:
            width, height = source["width"], source["height"]
            if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                raise ApiError(422, "INVALID_BBOX", "像素坐标越界或零面积",
                               cause=f"bbox={region.bbox}, source={width}x{height}",
                               fix="检查坐标顺序和原图尺寸")
            box = [x0 / width, y0 / height, x1 / width, y1 / height]
        if any(not math.isfinite(v) for v in box):
            raise ApiError(422, "INVALID_BBOX", "坐标必须是有限数")
        item = {
            "id": region.id,
            "source_id": region.source_id,
            "kind": region.kind,
            "bbox": [round(v, 8) for v in box],
            "coordinate_system": "normalized",
            "input_bbox": region.bbox,
            "input_coordinate_system": region.coordinate_system,
            "source_width": source["width"],
            "source_height": source["height"],
        }
        if region.text is not None:
            item["text"] = region.text
            item["text_kind"] = region.text_kind or "summary"
        normalized.append(item)
    return normalized


def create_source(store: Store, body: SourceCreate) -> tuple[dict[str, Any], int]:
    decoded = decode_source(body.image_base64)
    metadata = {
        "filename": body.filename,
        "source_note": body.source_note,
        "access_policy": body.access_policy,
        "physical_index": body.physical_index,
        "printed_label": body.printed_label,
    }
    with store.transaction() as conn:
        existing = conn.execute("SELECT * FROM sources WHERE content_hash=?",
                                (decoded.content_hash,)).fetchone()
        if existing is not None:
            if json.loads(existing["metadata_json"]) != metadata:
                raise ApiError(409, "SOURCE_METADATA_CONFLICT", "同一内容已登记，但来源元数据不同",
                               cause="内容哈希相同、元数据不一致",
                               fix="使用原来源记录，或明确更正来源归属（需另立流程）")
            return _source_view(dict(existing)), 200
        source_id = new_id("src")
        created = utc_now()
        store.insert_source(conn, source_id=source_id, content_hash=decoded.content_hash,
                            media_type=decoded.media_type, width=decoded.width,
                            height=decoded.height, content=decoded.content,
                            metadata=metadata, created_at=created)
        return _source_view(store.get_source(source_id) or {}), 201


def create_work(store: Store, body: WorkCreate, key: str | None) -> tuple[dict[str, Any], int]:
    key = _require_key(key)
    if body.schema_version != SCHEMA_VERSION:
        raise ApiError(422, "UNSUPPORTED_SCHEMA", "不支持的 schema_version",
                       cause=body.schema_version, fix=f"使用 {SCHEMA_VERSION}")
    request_hash = _hash(body.model_dump(mode="json"))
    with store.transaction() as conn:
        prior, replayed = _replay(store, conn, "work:create", key, request_hash)
        if prior is not None:
            return prior, 200
        sources: dict[str, dict[str, Any]] = {}
        for source_id in body.source_ids:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
            if row is None:
                raise ApiError(422, "UNKNOWN_SOURCE", f"来源不存在：{source_id}",
                               fix="先登记来源，再导入作品")
            sources[source_id] = dict(row)
        regions = _normalize_regions(body, sources)
        region_ids = {region["id"] for region in regions}
        claim_ids: set[str] = set()
        claims: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for claim_in in body.claims:
            if claim_in.id in claim_ids:
                raise ApiError(422, "DUPLICATE_ID", f"断言 ID 重复：{claim_in.id}",
                               fix="每个断言 ID 在作品内必须唯一")
            claim_ids.add(claim_in.id)
            claim = {
                "id": claim_in.id,
                "predicate": claim_in.predicate,
                "object": _literal_object(claim_in.object),
                "evidence_refs": list(claim_in.evidence_refs),
                "support_status": "insufficient",
                "validation_status": "valid",
                "review_status": "unreviewed",
            }
            claim_issues = _claim_issues(claim, region_ids)
            if any(item["blocking"] for item in claim_issues):
                claim["validation_status"] = "invalid"
            issues.extend(claim_issues)
            claims.append(claim)
        issue_ids: set[str] = set()
        for issue_in in body.issues:
            if issue_in.id is not None:
                if issue_in.id in issue_ids:
                    raise ApiError(422, "DUPLICATE_ID", f"问题 ID 重复：{issue_in.id}")
                issue_ids.add(issue_in.id)
            missing = [ref for ref in issue_in.evidence_refs if ref not in region_ids]
            if missing:
                raise ApiError(422, "UNKNOWN_EVIDENCE", "人工问题引用了不存在的区域",
                               cause=", ".join(missing), fix="先补充区域，或移除无效引用")
            if issue_in.affected_claim_id and issue_in.affected_claim_id not in claim_ids:
                raise ApiError(422, "UNKNOWN_CLAIM", "人工问题关联了不存在的断言")
            issues.append(_issue(issue_in.code, issue_in.message,
                                 affected_claim_id=issue_in.affected_claim_id,
                                 evidence_refs=list(issue_in.evidence_refs),
                                 blocking=True, source="user", issue_id=issue_in.id))
        work_id = new_id("work")
        created = utc_now()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "source_ids": list(body.source_ids),
            "regions": regions,
            "claims": claims,
            "issues": issues,
            "import_version": 1,
            "raw_import": body.model_dump(mode="json"),
        }
        store.insert_work(conn, work_id=work_id, created_at=created)
        store.insert_version(conn, work_id=work_id, version=1, payload=payload, created_at=created)
        work = store.get_work(work_id)
        response = _work_view(store, work or {}, {**payload, "_version": 1})
        store.put_idempotency(conn, scope="work:create", key=key, request_hash=request_hash,
                              response=response, created_at=created)
        return response, 201


def get_work(store: Store, work_id: str, version: int | None = None) -> dict[str, Any]:
    work = store.get_work(work_id)
    if work is None:
        raise ApiError(404, "WORK_NOT_FOUND", f"作品不存在：{work_id}")
    target = version or work["current_version"]
    if target < 1:
        raise ApiError(422, "INVALID_VERSION", "版本必须 ≥ 1")
    payload = store.read_version(work_id, target)
    if payload is None:
        raise ApiError(404, "VERSION_NOT_FOUND", f"作品版本不存在：{work_id} v{target}")
    payload["_version"] = target
    return _work_view(store, work, payload)


def review_work(store: Store, work_id: str, body: ReviewCreate,
                key: str | None) -> tuple[dict[str, Any], int]:
    key = _require_key(key)
    request_hash = _hash(body.model_dump(mode="json"))
    with store.transaction() as conn:
        prior, replayed = _replay(store, conn, f"work:review:{work_id}", key, request_hash)
        if prior is not None:
            return prior, 200
        work = conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        if work is None:
            raise ApiError(404, "WORK_NOT_FOUND", f"作品不存在：{work_id}")
        current = work["current_version"]
        if body.expected_version != current:
            raise ApiError(409, "VERSION_CONFLICT", "审核版本已过期",
                           cause=f"expected {body.expected_version}, current {current}",
                           fix="重新载入当前版本后核对再提交", retryable=False)
        stored = store.get_version(conn, work_id, current)
        if stored is None:
            raise ApiError(500, "CORRUPT_STATE", "当前版本缺失")
        payload = {key: value for key, value in stored.items() if key != "_created_at"}
        payload.pop("raw_import", None)
        claims = {claim["id"]: claim for claim in payload["claims"]}
        issues = payload["issues"]
        seen: set[str] = set()
        for decision in body.decisions:
            if decision.claim_id in seen:
                raise ApiError(422, "DUPLICATE_DECISION", f"断言被重复裁决：{decision.claim_id}")
            seen.add(decision.claim_id)
            claim = claims.get(decision.claim_id)
            if claim is None:
                raise ApiError(422, "UNKNOWN_CLAIM", f"断言不存在：{decision.claim_id}")
            if decision.action == "approve":
                value = (claim.get("object") or {}).get("value")
                if decision.support_status != "supported":
                    raise ApiError(422, "INVALID_REVIEW", "批准必须明确 support_status=supported")
                if claim["validation_status"] != "valid":
                    raise ApiError(422, "INVALID_REVIEW", "结构无效的断言不能批准",
                                   cause=f"{decision.claim_id} validation_status=invalid",
                                   fix="先修正谓词/证据并重新校验")
                if value is None or not str(value).strip() or not claim["evidence_refs"]:
                    raise ApiError(422, "INVALID_REVIEW", "空值或空证据的断言不能批准")
                claim["support_status"] = "supported"
                claim["review_status"] = "approved"
            elif decision.action == "reject":
                claim["review_status"] = "rejected"
            else:
                changed = (decision.predicate is not None or decision.object is not None
                           or decision.evidence_refs is not None)
                if not changed:
                    raise ApiError(422, "INVALID_REVIEW", "revise 至少修改谓词、值或证据之一")
                if decision.predicate is not None:
                    if decision.predicate not in PREDICATES:
                        raise ApiError(422, "UNKNOWN_PREDICATE", "revise 使用了不支持的谓词")
                    claim["predicate"] = decision.predicate
                if decision.object is not None:
                    claim["object"] = _literal_object(decision.object)
                if decision.evidence_refs is not None:
                    claim["evidence_refs"] = list(decision.evidence_refs)
                claim["support_status"] = "insufficient"
                claim["review_status"] = "unreviewed"
                issues = [item for item in issues if not (
                    item.get("source") == "server" and item.get("affected_claim_id") == decision.claim_id
                )]
                new_issues = _claim_issues(claim, {region["id"] for region in payload["regions"]})
                claim["validation_status"] = "invalid" if any(
                    item["blocking"] for item in new_issues
                ) else "valid"
                issues.extend(new_issues)
        issue_map = {item["id"]: item for item in issues}
        for resolution in body.issue_resolutions:
            target = issue_map.get(resolution.issue_id)
            if target is None:
                raise ApiError(422, "UNKNOWN_ISSUE", f"问题不存在：{resolution.issue_id}")
            affected = claims.get(target.get("affected_claim_id") or "")
            if (target.get("source") == "server" and affected is not None
                    and affected["validation_status"] == "invalid"
                    and affected["review_status"] != "rejected"):
                raise ApiError(422, "INVALID_ISSUE_RESOLUTION",
                               "结构问题不能只靠理由关闭；先修正断言并重新校验",
                               cause=f"{resolution.issue_id} 关联断言仍为 invalid")
            target["status"] = "resolved"
            target["reason"] = resolution.reason
            target["resolved_by"] = body.reviewer
            target["resolved_at"] = utc_now()
        payload["issues"] = issues
        payload["claims"] = list(claims.values())
        next_version = current + 1
        created = utc_now()
        store.insert_version(conn, work_id=work_id, version=next_version,
                             payload=payload, created_at=created)
        event_payload = {
            "decisions": [decision.model_dump(mode="json") for decision in body.decisions],
            "issue_resolutions": [item.model_dump(mode="json") for item in body.issue_resolutions],
            "before_version": current,
            "after_version": next_version,
        }
        event_id = new_id("evt")
        store.insert_event(conn, event_id=event_id, work_id=work_id, from_version=current,
                           to_version=next_version, reviewer=body.reviewer, reason=body.reason,
                           payload=event_payload, created_at=created)
        store.set_current_version(conn, work_id, next_version)
        new_work = store.get_work(work_id) or {}
        stored_new = store.get_version(conn, work_id, next_version) or {}
        stored_new["_version"] = next_version
        response = {"work": _work_view(store, new_work, stored_new),
                    "event": _event_view({
                        "id": event_id, "work_id": work_id, "from_version": current,
                        "to_version": next_version, "reviewer": body.reviewer,
                        "reason": body.reason, "payload": event_payload, "created_at": created,
                    })}
        store.put_idempotency(conn, scope=f"work:review:{work_id}", key=key,
                              request_hash=request_hash, response=response, created_at=created)
        return response, 200


def _publication_view(store: Store, row: dict[str, Any]) -> dict[str, Any]:
    work = store.get_work(row["work_id"]) or {}
    current = work.get("current_version")
    return {
        "publication_id": row["id"],
        "work_id": row["work_id"],
        "version": row["version"],
        "claims": row["payload"].get("claims", []),
        "source_ids": row["payload"].get("source_ids", []),
        "created_at": row["created_at"],
        "current_version": current,
        "historical": row["version"] != current,
    }


def _eligible(claim: dict[str, Any]) -> bool:
    value = (claim.get("object") or {}).get("value")
    return (
        claim.get("review_status") == "approved"
        and claim.get("support_status") == "supported"
        and claim.get("validation_status") == "valid"
        and value is not None and bool(str(value).strip())
        and bool(claim.get("evidence_refs"))
    )


def publish_work(store: Store, work_id: str, expected_version: int,
                 key: str | None) -> tuple[dict[str, Any], int]:
    key = _require_key(key)
    request_hash = _hash({"work_id": work_id, "expected_version": expected_version})
    with store.transaction() as conn:
        prior, replayed = _replay(store, conn, f"work:publish:{work_id}", key, request_hash)
        if prior is not None:
            return prior, 200
        work = conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        if work is None:
            raise ApiError(404, "WORK_NOT_FOUND", f"作品不存在：{work_id}")
        current = work["current_version"]
        if expected_version != current:
            raise ApiError(409, "VERSION_CONFLICT", "发布版本已过期",
                           cause=f"expected {expected_version}, current {current}",
                           fix="重新载入当前版本", retryable=False)
        stored = store.get_version(conn, work_id, current)
        if stored is None:
            raise ApiError(500, "CORRUPT_STATE", "当前版本缺失")
        restricted = []
        for source_id in stored["source_ids"]:
            row = conn.execute("SELECT metadata_json FROM sources WHERE id=?", (source_id,)).fetchone()
            if row is None:
                continue
            policy = str(json.loads(row["metadata_json"]).get("access_policy", "")).strip()
            if policy not in {"synthetic-only", "cleared-for-publication"}:
                restricted.append({"source_id": source_id, "access_policy": policy})
        if restricted:
            raise ApiError(409, "PUBLICATION_POLICY_BLOCKED", "来源许可策略禁止发布",
                           cause="来源 access_policy 标记为本地/不可发布",
                           fix="完成权利人许可确认并更新来源策略后再发布",
                           details={"restricted_sources": restricted})
        claims = stored["claims"]
        unreviewed = [claim["id"] for claim in claims if claim["review_status"] == "unreviewed"]
        eligible = [claim for claim in claims if _eligible(claim)]
        blocking = []
        for issue in stored["issues"]:
            if issue["status"] != "open" or not issue["blocking"]:
                continue
            affected = next((claim for claim in claims
                             if claim["id"] == issue.get("affected_claim_id")), None)
            if affected is not None and affected["review_status"] == "rejected":
                continue
            blocking.append(issue)
        if unreviewed or blocking or not eligible:
            raise ApiError(409, "PUBLICATION_BLOCKED", "当前版本不满足发布条件",
                           cause=(f"unreviewed={len(unreviewed)}, blocking_issues={len(blocking)}, "
                                  f"eligible_claims={len(eligible)}"),
                           fix="完成所有裁决、处置阻断问题，并至少保留一条合格断言",
                           details={"unreviewed_claim_ids": unreviewed,
                                    "blocking_issue_ids": [issue["id"] for issue in blocking]})
        existing = conn.execute(
            "SELECT * FROM publications WHERE work_id=? AND version=?", (work_id, current)
        ).fetchone()
        if existing is not None:
            response = _publication_view(store, store._publication_row(existing))
            store.put_idempotency(conn, scope=f"work:publish:{work_id}", key=key,
                                  request_hash=request_hash, response=response,
                                  created_at=utc_now())
            return response, 200
        publication_id = new_id("pub")
        created = utc_now()
        snapshot = {"work_id": work_id, "version": current,
                    "claims": eligible, "source_ids": stored["source_ids"],
                    "created_at": created}
        store.insert_publication(conn, publication_id=publication_id, work_id=work_id,
                                 version=current, payload=snapshot, created_at=created)
        row = store.get_publication(work_id, current) or {}
        response = _publication_view(store, row)
        store.put_idempotency(conn, scope=f"work:publish:{work_id}", key=key,
                              request_hash=request_hash, response=response, created_at=created)
        return response, 201


def get_publication(store: Store, publication_id: str) -> dict[str, Any]:
    row = store.get_publication_by_id(publication_id)
    if row is None:
        raise ApiError(404, "PUBLICATION_NOT_FOUND", f"发布快照不存在：{publication_id}")
    return _publication_view(store, row)


def publications_for_work(store: Store, work_id: str) -> dict[str, Any]:
    if store.get_work(work_id) is None:
        raise ApiError(404, "WORK_NOT_FOUND", f"作品不存在：{work_id}")
    items = [_publication_view(store, row) for row in store.list_publications(work_id)]
    return {"items": items, "count": len(items)}


def knowledge(store: Store, title: str | None = None, limit: int = 20,
              offset: int = 0) -> dict[str, Any]:
    rows = store.list_current_publications()
    filtered = []
    for row in rows:
        view = _publication_view(store, row)
        if title:
            values = [str((claim.get("object") or {}).get("value", ""))
                      for claim in view["claims"] if claim.get("predicate") == "source_title"]
            if not any(title in value for value in values):
                continue
        filtered.append(view)
    total = len(filtered)
    page = filtered[offset:offset + limit]
    return {"items": page, "count": len(page), "total": total,
            "limit": limit, "offset": offset, "has_more": offset + limit < total}
